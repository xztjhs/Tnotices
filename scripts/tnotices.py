#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tnotices - 标讯跟进平台
- data/projects.json 为唯一数据源
- 生成 README.md（Gitea 仓库首页）与 index.html（可交互看板）
- 通过 Gitea API 建库 / git push 同步

凭据：优先读取环境变量 GITEA_TOKEN；否则调用本机 git credential fill，
不在任何输出、文件、日志中打印凭据。
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "projects.json"
EVENTS = ROOT / "data" / "events.jsonl"
SETTINGS = ROOT / "config" / "settings.json"
README = ROOT / "README.md"
INDEX = ROOT / "index.html"

STATUS_LABELS = {
    "new": "新发现",
    "watching": "观察中",
    "evaluating": "评估中",
    "preparing": "投标准备",
    "submitted": "已投标",
    "result_pending": "结果待出",
    "won": "已中标",
    "lost": "未中标",
    "failed": "流标/废标",
    "cancelled": "已终止",
    "closed": "已完结",
}
ACTIVE_STATUSES = {"new", "watching", "evaluating", "preparing", "submitted", "result_pending", "won", "lost", "failed", "cancelled"}


def load_settings() -> dict:
    return json.loads(SETTINGS.read_text(encoding="utf-8"))


def load_projects() -> list[dict]:
    if not DATA.exists():
        return []
    return json.loads(DATA.read_text(encoding="utf-8"))


def save_projects(projects: list[dict]) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(projects, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_day(value: str | None) -> date | None:
    if not value:
        return None
    s = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def append_event(project: dict, etype: str, title: str, detail: str = "", edate: str | None = None, source: str = "") -> None:
    e = {
        "date": edate or date.today().isoformat(),
        "type": etype,
        "title": title,
        "detail": detail,
        "source": source,
    }
    project.setdefault("timeline", []).append(e)
    project["timeline"] = project["timeline"][-80:]
    project["last_checked"] = now_str()
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    with EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"id": project.get("id"), **e}, ensure_ascii=False) + "\n")


def find(projects: list[dict], pid: str) -> dict:
    for p in projects:
        if p.get("id") == pid:
            return p
    raise SystemExit(f"project not found: {pid}")


def recompute(projects: list[dict]) -> list[dict]:
    s = load_settings()
    close_days = int(s.get("close_after_days", 30))
    urgent_days = int(s.get("urgent_days", 7))
    today = date.today()
    for p in projects:
        if p.get("status") == "closed":
            continue
        award = parse_day(p.get("award_date"))
        if award and (today - award).days >= close_days:
            p["status"] = "closed"
            p["closed_at"] = today.isoformat()
            p["closed_reason"] = f"中标公示满{close_days}天"
            append_event(p, "closed", "自动完结", f"中标公示于 {award.isoformat()} 发布，已满 {close_days} 天")
            continue
        deadline = parse_day(p.get("bid_deadline"))
        if deadline and deadline < today and p.get("status") in ("new", "watching", "evaluating", "preparing", "submitted"):
            p["status"] = "result_pending"
            append_event(p, "status", "状态更新", f"投标截止 {deadline.isoformat()} 已过，转为结果待出")
        p["urgent"] = bool(deadline and 0 <= (deadline - today).days <= urgent_days and p.get("status") not in ("won", "lost", "closed", "failed", "cancelled"))
    return projects


def fmt_money(v) -> str:
    if v is None or v == "":
        return "未披露"
    try:
        f = float(v)
        return f"{f:,.1f}".rstrip("0").rstrip(".")
    except Exception:
        return str(v)


def short(s: str, n: int = 46) -> str:
    s = (s or "").replace("|", "/").replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def latest_event(p: dict) -> str:
    tl = p.get("timeline") or []
    if not tl:
        return ""
    e = tl[-1]
    return f"{e.get('date','')} {e.get('title','')}"


def render_readme(projects: list[dict]) -> str:
    today = date.today()
    region_text = " / ".join(load_settings().get("region", [])) or "目标区域"
    active = [p for p in projects if p.get("status") != "closed"]
    closed = [p for p in projects if p.get("status") == "closed"]
    urgent = [p for p in active if p.get("urgent")]
    total_budget = sum(float(p.get("budget_wan") or 0) for p in active)
    won = [p for p in active if p.get("status") == "won"]
    changed = [p for p in active if (p.get("timeline") or []) and (p["timeline"][-1].get("date") or "") >= (today - timedelta(days=3)).isoformat()]

    def sort_key(p):
        return (p.get("bid_deadline") or "9999-12-31", p.get("priority") or "Z")

    active.sort(key=sort_key)
    changed.sort(key=lambda p: (p.get("timeline") or [{}])[-1].get("date", ""), reverse=True)

    lines = [
        "# Tnotices · 标讯跟进平台",
        "",
        f"> 自动生成：{now_str()}｜数据源：剑鱼标讯 + Gitea｜地区：{region_text}",
        "",
        f"**在跟项目 {len(active)} 个** ｜ **7 天内截止 {len(urgent)} 个** ｜ **合计预算 {fmt_money(total_budget)} 万** ｜ **已中标 {len(won)} 个** ｜ **已完结 {len(closed)} 个**",
        "",
        "> 交互看板：本地运行 `start_dashboard.bat` 后访问 `http://127.0.0.1:8088/index.html`（Gitea 里直接点 index.html 只显示源码）。",
        "",
        "[今日变更](#今日变更) ｜ [已完结项目](#已完结项目)",
        "",
        "## 在跟项目",
        "",
        "| # | 项目 | 业主单位 | 预算(万) | 投标截止 | 状态 | 中标公司 | 负责人 | 最新动态 |",
        "|---|---|---|---:|---|---|---|---|---|",
    ]
    for i, p in enumerate(active, 1):
        lines.append(
            "| {i} | [{name}]({url}) | {buyer} | {budget} | {deadline} | {status} | {winner} | {owner} | {latest} |".format(
                i=i,
                name=short(p.get("project_name", ""), 60),
                url=p.get("source_url") or p.get("jianyu_url") or "#",
                buyer=short(p.get("buyer", ""), 28),
                budget=fmt_money(p.get("budget_wan")),
                deadline=p.get("bid_deadline") or "",
                status=STATUS_LABELS.get(p.get("status", ""), p.get("status", "")),
                winner=short(p.get("winner", ""), 24),
                owner=p.get("owner", ""),
                latest=short(latest_event(p), 40),
            )
        )
    if not active:
        lines.append("| - | 暂无在跟项目 | - | - | - | - | - | - | - |")

    lines += ["", "## 今日变更", ""]
    if changed:
        for p in changed[:20]:
            e = (p.get("timeline") or [{}])[-1]
            lines.append(f"- **{p.get('project_name','')}**：{e.get('date','')} {e.get('title','')} {('- ' + e.get('detail','')) if e.get('detail') else ''}")
    else:
        lines.append("- 近 3 天暂无变更。")

    lines += ["", "## 已完结项目", "", "| 项目 | 业主单位 | 中标公司 | 中标金额(万) | 完结原因 |", "|---|---|---|---:|---|"]
    for p in sorted(closed, key=lambda x: x.get("closed_at", ""), reverse=True)[:30]:
        lines.append(
            "| {name} | {buyer} | {winner} | {amount} | {reason} |".format(
                name=short(p.get("project_name", ""), 55),
                buyer=short(p.get("buyer", ""), 24),
                winner=short(p.get("winner", ""), 22),
                amount=fmt_money(p.get("win_amount_wan")),
                reason=p.get("closed_reason", ""),
            )
        )
    if not closed:
        lines.append("| 暂无 | - | - | - | - |")

    lines += [
        "",
        "---",
        "",
        "### 状态说明",
        "",
        "`新发现 → 观察中 → 评估中 → 投标准备 → 已投标 → 结果待出 → 已中标/未中标/流标`；中标公示满 30 天自动转 `已完结`，不再跟进。",
        "",
        "### 数据与脚本",
        "",
        "- `data/projects.json`：项目主数据",
        "- `data/events.jsonl`：变更事件流水",
        "- `reports/`：每日扫描报告",
        "- `scripts/tnotices.py`：更新、渲染、同步",
        "- `config/daily_prompt.md`：每日智能体任务说明",
        "- `docs/搭建与使用指南.md`：从零复现与日常使用",
        "- `docs/值班手册_一页纸.md`：每日值班 5 分钟检查清单",
        "- `docs/Tnotices_完整文档_20261020.md`：指南+值班手册+附录合集",
        "",
    ]
    return "\n".join(lines)


def render_index(projects: list[dict]) -> str:
    payload = json.dumps(projects, ensure_ascii=False)
    region_text = " / ".join(load_settings().get("region", [])) or "目标区域"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tnotices · 标讯跟进看板</title>
<style>
:root{{--bg:#0b1020;--panel:#121a33;--line:#243052;--text:#e8eefc;--muted:#8fa0c4;--accent:#4f8cff;--warn:#ffb020;--ok:#2ecc71;--bad:#ff5c6c}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 "Segoe UI","Microsoft YaHei",sans-serif}}
header{{padding:24px 28px;border-bottom:1px solid var(--line);display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}}
h1{{margin:0;font-size:24px}}h1 span{{color:var(--accent)}}
.sub{{color:var(--muted);font-size:13px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;padding:18px 28px}}
.card{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 16px}}
.card b{{display:block;font-size:22px;margin-top:4px}}.card small{{color:var(--muted)}}
.toolbar{{display:flex;gap:10px;flex-wrap:wrap;padding:0 28px 14px}}
input,select{{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font-size:13px}}
input{{min-width:260px;flex:1}}
table{{width:calc(100% - 56px);margin:0 28px 40px;border-collapse:collapse;background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{position:sticky;top:0;background:#162040;color:var(--muted);font-weight:600;font-size:12px;letter-spacing:.04em}}
tr:hover td{{background:#162040}}
a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
.tag{{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;border:1px solid var(--line)}}
.s-won{{color:var(--ok);border-color:#1f6b45}}.s-submitted,.s-preparing{{color:var(--accent);border-color:#2c4f9e}}
.s-result_pending{{color:var(--warn);border-color:#7a5a12}}.s-failed,.s-cancelled,.s-lost{{color:var(--bad);border-color:#7a2630}}
.s-closed{{color:var(--muted)}}.urgent{{color:var(--warn);font-weight:700}}
.empty{{padding:40px;text-align:center;color:var(--muted)}}
@media(max-width:900px){{table{{display:block;overflow-x:auto}}}}
</style>
</head>
<body>
<header>
  <div><h1>Tnotices <span>标讯跟进看板</span></h1><div class="sub">{region_text} · 数据源 剑鱼标讯 · 每日自动更新</div></div>
  <div class="sub" id="generated"></div>
</header>
<div class="cards" id="cards"></div>
<div class="toolbar">
  <input id="q" placeholder="搜索项目 / 业主 / 代理 / 中标公司">
  <select id="region"><option value="">全部地区</option></select>
  <select id="status"><option value="">全部状态</option></select>
  <select id="priority"><option value="">全部优先级</option></select>
</div>
<table>
<thead><tr><th>#</th><th>项目</th><th>业主单位</th><th>预算(万)</th><th>投标截止</th><th>状态</th><th>中标公司</th><th>负责人</th><th>最新动态</th></tr></thead>
<tbody id="rows"></tbody>
</table>
<div class="empty" id="empty" style="display:none">没有匹配的项目</div>
<script>
const DATA = {payload};
const LABEL = {{new:"新发现",watching:"观察中",evaluating:"评估中",preparing:"投标准备",submitted:"已投标",result_pending:"结果待出",won:"已中标",lost:"未中标",failed:"流标/废标",cancelled:"已终止",closed:"已完结"}};
const money = v => (v===null||v===undefined||v==="")?"未披露":Number(v).toLocaleString("zh-CN",{{maximumFractionDigits:1}});
const latest = p => (p.timeline && p.timeline.length) ? (p.timeline[p.timeline.length-1].date+" "+p.timeline[p.timeline.length-1].title) : "";
const active = DATA.filter(p=>p.status!=="closed");
const urgent = active.filter(p=>p.urgent);
const budget = active.reduce((s,p)=>s+(Number(p.budget_wan)||0),0);
const won = active.filter(p=>p.status==="won").length;
document.getElementById("generated").textContent = "生成时间：" + new Date().toLocaleString("zh-CN");
document.getElementById("cards").innerHTML = [
 ["在跟项目",active.length],["7天内截止",urgent.length],["合计预算(万)",money(budget)],["已中标",won],["已完结",DATA.length-active.length]
].map(([k,v])=>`<div class="card"><small>${{k}}</small><b>${{v}}</b></div>`).join("");
const regions=[...new Set(DATA.map(p=>p.region).filter(Boolean))].sort();
document.getElementById("region").innerHTML += regions.map(r=>`<option>${{r}}</option>`).join("");
document.getElementById("status").innerHTML += Object.entries(LABEL).map(([k,v])=>`<option value="${{k}}">${{v}}</option>`).join("");
document.getElementById("priority").innerHTML += [...new Set(DATA.map(p=>p.priority).filter(Boolean))].sort().map(r=>`<option>${{r}}</option>`).join("");
function render(){{
  const q=document.getElementById("q").value.trim().toLowerCase();
  const r=document.getElementById("region").value, s=document.getElementById("status").value, pr=document.getElementById("priority").value;
  const rows=DATA.filter(p=>(!r||p.region===r)&&(!s||p.status===s)&&(!pr||p.priority===pr)&&(!q||[p.project_name,p.buyer,p.agency,p.winner].join(" ").toLowerCase().includes(q))).sort((a,b)=>(a.bid_deadline||"9999").localeCompare(b.bid_deadline||"9999"));
  document.getElementById("rows").innerHTML=rows.map((p,i)=>{{
    const url=p.source_url||p.jianyu_url||"#";
    return `<tr><td>${{i+1}}</td><td><a href="${{url}}" target="_blank">${{p.project_name||""}}</a></td><td>${{p.buyer||""}}</td><td>${{money(p.budget_wan)}}</td><td class="${{p.urgent?"urgent":""}}">${{p.bid_deadline||""}}</td><td><span class="tag s-${{p.status}}">${{LABEL[p.status]||p.status}}</span></td><td>${{p.winner||""}}</td><td>${{p.owner||""}}</td><td>${{latest(p)}}</td></tr>`;
  }}).join("");
  document.getElementById("empty").style.display=rows.length?"none":"block";
}}
["q","region","status","priority"].forEach(id=>document.getElementById(id).addEventListener("input",render));
render();
</script>
</body>
</html>"""


def get_auth_header(settings: dict) -> str:
    token = os.environ.get("GITEA_TOKEN")
    if token:
        raw = f"{token}:"
    else:
        host = settings["gitea"]["base_url"].split("://", 1)[-1]
        inp = f"protocol=http\nhost={host}\n\n"
        r = subprocess.run(["git", "credential", "fill"], input=inp, text=True, capture_output=True)
        if r.returncode != 0:
            raise SystemExit("无法读取 Gitea 凭据，请设置 GITEA_TOKEN 或配置 git credential")
        user = pwd = ""
        for line in r.stdout.splitlines():
            if line.startswith("username="):
                user = line[len("username="):]
            elif line.startswith("password="):
                pwd = line[len("password="):]
        if not user or not pwd:
            raise SystemExit("Gitea 凭据为空，请设置 GITEA_TOKEN")
        raw = f"{user}:{pwd}"
    return "Basic " + base64.b64encode(raw.encode("utf-8")).decode("ascii")


def api(settings: dict, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    base = settings["gitea"]["base_url"].rstrip("/")
    url = base + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", get_auth_header(settings))
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, (json.loads(body) if body else {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            obj = json.loads(body)
        except Exception:
            obj = {"message": body[:300]}
        return e.code, obj


def ensure_repo(settings: dict) -> None:
    g = settings["gitea"]
    region_text = " / ".join(settings.get("region", [])) or "目标区域"
    status, obj = api(settings, "GET", f"/api/v1/repos/{g['owner']}/{g['repo']}")
    if status == 200:
        print(f"repo exists: {g['owner']}/{g['repo']}")
        return
    status, obj = api(settings, "POST", "/api/v1/user/repos", {
        "name": g["repo"],
        "description": f"Tnotices 标讯跟进平台（{region_text}）",
        "private": bool(g.get("private", True)),
        "auto_init": False,
        "default_branch": g.get("branch", "main"),
    })
    if status in (201, 409):
        print(f"repo ready: {g['owner']}/{g['repo']}")
    else:
        raise SystemExit(f"create repo failed: HTTP {status} {obj.get('message','')}")


def git_push(settings: dict, message: str) -> None:
    g = settings["gitea"]
    remote = f"{g['base_url'].rstrip('/')}/{g['owner']}/{g['repo']}.git"
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    token = os.environ.get("GITEA_TOKEN")
    if token:
        auth = base64.b64encode(f"{token}:".encode("utf-8")).decode("ascii")
        env["GIT_CONFIG_COUNT"] = "1"
        env["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {auth}"
    if not (ROOT / ".git").exists():
        subprocess.run(["git", "init", "-b", g.get("branch", "main")], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.name", "Tnotices Bot"], cwd=ROOT, check=True)
    subprocess.run(["git", "config", "user.email", "tnotices@local"], cwd=ROOT, check=True)
    subprocess.run(["git", "add", "-A"], cwd=ROOT, check=True)
    diff = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT)
    if diff.returncode != 0:
        subprocess.run(["git", "commit", "-m", message], cwd=ROOT, check=True)
    remotes = subprocess.run(["git", "remote"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    if "origin" in remotes:
        subprocess.run(["git", "remote", "set-url", "origin", remote], cwd=ROOT, check=True)
    else:
        subprocess.run(["git", "remote", "add", "origin", remote], cwd=ROOT, check=True)
    r = subprocess.run(["git", "push", "-u", "origin", g.get("branch", "main")], cwd=ROOT, env=env)
    if r.returncode != 0:
        raise SystemExit("git push 失败：请确认 git credential 已保存 Gitea 账号，或设置 GITEA_TOKEN")
    print("pushed")


def cmd_import_csv(args) -> None:
    src = Path(args.path)
    rows = list(csv.DictReader(src.open(encoding="utf-8-sig")))
    projects = []
    for i, r in enumerate(rows, 1):
        pid = f"T{date.today().strftime('%Y%m%d')}-{i:03d}"
        p = {
            "id": pid,
            "jianyu_id": (r.get("详情页URL", "") or "").split("/content/")[-1].replace(".html", ""),
            "project_name": r.get("项目名称", ""),
            "project_no": r.get("项目编号", ""),
            "buyer": r.get("采购人", ""),
            "agency": r.get("代理机构", ""),
            "region": r.get("地区", ""),
            "industry": r.get("产品线匹配", ""),
            "budget_wan": float(r["预算(万元)"]) if r.get("预算(万元)", "").replace(".", "", 1).isdigit() else None,
            "publish_date": r.get("发布时间", ""),
            "sign_deadline": r.get("报名截止", ""),
            "bid_deadline": r.get("投标截止", ""),
            "bid_open_time": "",
            "status": "watching",
            "priority": r.get("优先级", ""),
            "winner": "",
            "win_amount_wan": None,
            "award_date": "",
            "source_url": r.get("原文链接", ""),
            "jianyu_url": r.get("详情页URL", ""),
            "contacts": {"buyer": r.get("采购人联系人/电话", ""), "agency": r.get("代理联系人/电话", "")},
            "products": r.get("产品线匹配", ""),
            "owner": "",
            "next_action": "",
            "next_action_date": "",
            "created_at": date.today().isoformat(),
            "updated_at": now_str(),
            "last_checked": now_str(),
            "closed_at": "",
            "closed_reason": "",
            "tags": [],
            "timeline": [{"date": date.today().isoformat(), "type": "created", "title": "录入平台", "detail": "来自剑鱼标讯检索", "source": r.get("原文链接", "")}],
        }
        projects.append(p)
    save_projects(projects)
    print(f"imported {len(projects)} projects")


def cmd_update(args) -> None:
    projects = load_projects()
    p = find(projects, args.id)
    for pair in args.set or []:
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        if k in ("budget_wan", "win_amount_wan"):
            try:
                v = float(v)
            except ValueError:
                v = None
        if v == "":
            v = None
        p[k] = v
    p["updated_at"] = now_str()
    save_projects(projects)
    print(json.dumps(p, ensure_ascii=False, indent=2))


def cmd_event(args) -> None:
    projects = load_projects()
    p = find(projects, args.id)
    append_event(p, args.type, args.title, args.detail or "", args.date, args.source or "")
    p["updated_at"] = now_str()
    save_projects(projects)
    print("event added")


def cmd_add(args) -> None:
    projects = load_projects()
    p = json.loads(Path(args.json).read_text(encoding="utf-8")) if args.json else json.loads(sys.stdin.read())
    if not p.get("id"):
        p["id"] = f"T{date.today().strftime('%Y%m%d')}-{len(projects)+1:03d}"
    p.setdefault("status", "new")
    p.setdefault("timeline", [])
    p.setdefault("created_at", date.today().isoformat())
    p["updated_at"] = now_str()
    projects.append(p)
    save_projects(projects)
    print(p["id"])


def cmd_recompute(args) -> None:
    projects = recompute(load_projects())
    save_projects(projects)
    closed = len([p for p in projects if p.get("status") == "closed"])
    print(f"recomputed: {len(projects)} projects, {closed} closed")


def cmd_batch(args) -> None:
    projects = recompute(load_projects())
    save_projects(projects)
    today = date.today()

    def rank(p):
        st = p.get("status", "")
        dl = parse_day(p.get("bid_deadline"))
        days = (dl - today).days if dl else 999
        score = 0
        if st in ("submitted", "result_pending"):
            score -= 100
        if st in ("won", "lost", "failed", "cancelled"):
            score -= 50
        if 0 <= days <= 7:
            score -= 40
        if -30 <= days < 0:
            score -= 30
        return (score, p.get("bid_deadline") or "9999-12-31", p.get("last_checked") or "")

    active = [p for p in projects if p.get("status") != "closed"]
    active.sort(key=rank)
    batch = active[: args.limit]
    out = [
        {
            "id": p.get("id"),
            "project_name": p.get("project_name"),
            "project_no": p.get("project_no"),
            "buyer": p.get("buyer"),
            "bid_deadline": p.get("bid_deadline"),
            "status": p.get("status"),
            "last_checked": p.get("last_checked"),
            "source_url": p.get("source_url") or p.get("jianyu_url"),
        }
        for p in batch
    ]
    text = json.dumps(out, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"batch {len(out)} -> {args.out}")
    else:
        print(text)


def cmd_render(args) -> None:
    projects = recompute(load_projects())
    save_projects(projects)
    README.write_text(render_readme(projects), encoding="utf-8")
    INDEX.write_text(render_index(projects), encoding="utf-8")
    print(f"rendered README.md and index.html ({len(projects)} projects)")


def cmd_push(args) -> None:
    settings = load_settings()
    ensure_repo(settings)
    git_push(settings, args.message or f"Tnotices update {now_str()}")
    print("done")


def cmd_init_repo(args) -> None:
    settings = load_settings()
    ensure_repo(settings)
    print("repo ready")


def main() -> None:
    ap = argparse.ArgumentParser(description="Tnotices CLI")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import-csv")
    p.add_argument("--path", required=True)
    p.set_defaults(func=cmd_import_csv)

    p = sub.add_parser("update")
    p.add_argument("--id", required=True)
    p.add_argument("--set", action="append", help="field=value，可多次")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("event")
    p.add_argument("--id", required=True)
    p.add_argument("--type", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--detail", default="")
    p.add_argument("--date", default="")
    p.add_argument("--source", default="")
    p.set_defaults(func=cmd_event)

    p = sub.add_parser("add")
    p.add_argument("--json", default="")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("recompute")
    p.set_defaults(func=cmd_recompute)

    p = sub.add_parser("batch")
    p.add_argument("--limit", type=int, default=30)
    p.add_argument("--out", default="")
    p.set_defaults(func=cmd_batch)

    p = sub.add_parser("render")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("init-repo")
    p.set_defaults(func=cmd_init_repo)

    p = sub.add_parser("push")
    p.add_argument("--message", default="")
    p.set_defaults(func=cmd_push)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
