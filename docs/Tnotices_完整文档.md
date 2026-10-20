# Tnotices 本地标讯助手 · 完整文档（脱敏版）

> 版本：2026-10-20｜适用：智能体 + 标讯网站 + 本地 Gitea
>
> 本版本已移除内网地址、公司名、区域名、客户与联系人信息；示例均为占位符。

## 目录

1. 搭建与使用指南
2. 值班手册（一页纸）
3. 附录 A：核心脚本
4. 附录 B：每日任务提示词
5. 附录 C：关键词矩阵

---

# Tnotices 本地标讯助手 · 搭建与使用指南

> 适用对象：需要在本地/内网复现「智能体 + 剑鱼标讯 + Gitea」标讯跟进平台的销售、售前、投标管理人员。
>
> 本文不含 Cherry Studio 安装、不含本地 Gitea 搭建；默认两者已可用。
>
> 参考实现：`http://<gitea-host>:3000/<owner>/Tnotices`（私有仓库）

---

## 0. 这套系统能做什么

| 能力 | 说明 |
|---|---|
| 每日自动抓取 | 智能体按关键词矩阵抓取<区域1>/<区域2>标讯，去重后入库 |
| 变更跟踪 | 自动识别更正、补遗、延期、答疑、质疑 |
| 中标跟踪 | 抓取中标/成交公告，回填中标单位、金额、公示日期 |
| 异常识别 | 废标、流标、终止自动转异常状态 |
| 自动完结 | 中标公示满 30 天自动标记“已完结”，不再巡检 |
| Gitea 首页看板 | 仓库首页 README 直接显示项目清单 |
| 交互看板 | `index.html` 支持搜索、筛选、排序 |
| 事件审计 | 每次变更写入 `data/events.jsonl`，可回溯 |

**核心原则**：Gitea 是唯一可信归档，`data/projects.json` 是唯一数据源，脚本只做确定性处理，智能体只做“检索 + 判断 + 录入”。

### 30 分钟快速复现

| 步骤 | 动作 | 对应章节 |
|---|---|---|
| 1 | 配置 icompify 模型并测试工具调用 | Step 1 |
| 2 | 创建标讯助手 Agent，粘贴系统提示词 | Step 2 |
| 3 | 解压模板包到 `D:\Tnotices` | Step 3–5 |
| 4 | 改 `config/settings.json` 的 Gitea 地址/owner/repo | Step 4 |
| 5 | 导入初始 CSV，`recompute` + `render` | Step 6–7 |
| 6 | 打开本地看板验收 | Step 7 |
| 7 | 配 `GITEA_TOKEN`，`init-repo` + `push` | Step 8 |
| 8 | 建每天 08:30 的定时任务，手动跑 5 个项目验证 | Step 9–10 |

---

## 1. 架构

```
┌─────────────────────────────────────────────────────────────┐
│ Cherry Studio                                                │
│  ├─ 模型服务：icompify / deepseek-v4.1-flash-1017            │
│  ├─ 智能体：标讯跟进助手（浏览器 + 文件 + Shell + 定时）      │
│  └─ 定时任务：每天 08:30                                     │
└───────────────┬─────────────────────────────────────────────┘
                │ 浏览器检索 / CLI 更新
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 本地工作目录 D:\Tnotices                                     │
│  ├─ data/projects.json     项目主数据（唯一数据源）           │
│  ├─ data/events.jsonl      事件流水（只追加）                 │
│  ├─ scripts/tnotices.py    更新/渲染/推送                     │
│  ├─ README.md              自动生成，Gitea 首页展示           │
│  ├─ index.html             自动生成，交互看板                 │
│  └─ reports/YYYY-MM-DD.md  每日日报                           │
└───────────────┬─────────────────────────────────────────────┘
                │ git push
                ▼
┌─────────────────────────────────────────────────────────────┐
│ 本地 Gitea：<owner>/Tnotices（私有）                            │
│  ├─ 首页 README 项目清单                                      │
│  ├─ 代码/脚本/配置                                            │
│  └─ 提交历史 = 每日快照                                       │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 前置条件

| 项 | 要求 | 检查命令 |
|---|---|---|
| 操作系统 | Windows 10/11，PowerShell 5.1+ | `$PSVersionTable.PSVersion` |
| Cherry Studio | 已安装，可创建智能体、可开浏览器 | 打开应用 |
| 本地 Gitea | 已运行，能创建私有仓库 | 浏览器打开 Gitea |
| 剑鱼标讯 | 有账号，可登录 | 浏览器打开 jianyu360.cn |
| icompify 算力 | 有 API Key，模型支持工具调用 | 见 Step 1 |
| Git | 2.40+ | `git --version` |
| uv | Cherry 自带或单独安装 | `uv --version` |
| Python | 3.11+（由 uv 管理，无需单独装） | `uv run python --version` |

> **重要**：智能体要操作浏览器、执行 Shell，模型必须支持 **Function Calling / Tool Use**。如果 icompify 该模型不支持工具调用，智能体只能聊天，无法完成抓取。Step 1 会做一次工具调用测试。

---

## 3. Step 1：在 Cherry Studio 配置 icompify 模型

### 3.1 添加提供商

1. 打开 Cherry Studio → **设置 → 模型服务**。
2. 点击 **添加提供商**，选择 **OpenAI 兼容 / 自定义**。
3. 填写：
   - 名称：`icompify`
   - API 地址：以 icompify 控制台的「API Base URL」为准，通常以 `/v1` 结尾
   - API Key：icompify 控制台创建
4. 保存。

> 不同 icompify 账号的 Base URL 可能不同，本文不写死地址；以控制台显示为准。

### 3.2 添加模型

在 icompify 提供商下点击 **添加模型**：

| 字段 | 值 |
|---|---|
| 模型 ID | `deepseek-v4.1-flash-1017`（以控制台模型列表为准） |
| 显示名称 | `DeepSeek V4.1 Flash 1017` |
| 模型类型 | 对话 / Chat |
| 上下文长度 | 按控制台标称填写（建议 ≥64K） |
| 最大输出 | 8192 或更高 |
| 工具调用 | 必须开启（若提供商有该开关） |

> 如果控制台只给 `deepseek-v4.1-flash`，就填这个；`1017` 可能是批次/版本号。**以控制台模型列表的精确 ID 为准**，不要凭记忆猜。

保存后点击 **检查连接**，确认返回正常。

### 3.3 设为默认模型

设置 → 默认模型 → 助手模型选择 `DeepSeek V4.1 Flash 1017`。

### 3.4 工具调用冒烟测试

新建一个临时对话，发送：

```
请调用浏览器工具打开 https://example.com ，然后告诉我页面标题。
```

- 如果模型正确发起工具调用并返回标题 → 通过。
- 如果只回复文字、不调用工具 → 该模型/提供商未开启 Tool Use，需要换模型或联系 icompify 开通。

---

## 4. Step 2：创建标讯助手智能体

### 4.1 新建智能体

Cherry Studio → **智能体 → 新建智能体**：

| 项 | 建议值 |
|---|---|
| 名称 | `标讯助手（<区域1>/<区域2>）` |
| 模型 | `DeepSeek V4.1 Flash 1017` |
| 温度 | 0.2–0.3（结构化任务，低温度更稳） |
| 最大输出 | 8192 |
| 工具 | 浏览器、文件读写、Shell/终端、定时任务、记忆、网页搜索 |

> 不同 Cherry 版本的工具有无差异；至少要保证 **浏览器** 和 **文件/终端** 可用。若没有 Shell 工具，可安装 filesystem + shell 类 MCP 服务器替代；完全不装 Shell 时，智能体只负责浏览器检索并输出结构化 JSON，CLI 更新/推送由人工在 PowerShell 执行。

### 4.2 系统提示词（直接复制）

> 非<公司>或其他区域，替换提示词首段的公司、区域、产品线即可；其余规则通用。

```text
# 角色
你是「招投标与客户情报专员」，为<公司><区域>区域提供标讯检索、情报整理与跟进管理服务。
业务领域：服务器、存储、AI/算力、HPC、云、数据中心、信创、行业信息化。
重点区域：<区域1>、<区域2>。客户类型：政府、央国企、医疗、教育、金融、能源、企业。

# 第一优先级原则
1. 真实优先：未从页面/工具实际读取的信息，不得补全、猜测或“合理推断”为事实。缺数据写“未披露”，推断值加 [推测]。
2. 凭据安全：账号密码只在登录步骤内部使用，永不在回复、表格、文件名、知识库、脚本、日志中回显或复述，包括部分打码。
3. 授权边界：只使用用户明确提供的账号做只读浏览与导出。不注册新账号、不改密码/资料、不购买会员、不点击付费升级、不群发、不提交表单或报价。
4. 最小动作：能用一次请求拿到的，不做十次；复用已保存登录态；不遍历全站、不高频刷新、不做压力式抓取。
5. 不越权决策：投标/报价/放弃只给建议与依据，最终由人决定。

# 浏览器任务协议
1. 先访问目标站点确认是否已登录；已登录直接检索，不重复登录。
2. 需要登录时从配置读取账号密码，在页面输入框填写并提交；回复中只描述“已使用账号 A 登录 X 站点”。
3. 遇到图形验证码、短信/邮箱验证码、扫码、滑块、人机校验：立即暂停，提示用户在浏览器中手动完成，不得识别、绕过、猜解或反复提交。
4. 登录成功后确认并持久化登录态，用一次轻量校验确认有效。
5. 连续登录失败 2 次即停止并上报，避免账号被风控锁定。
6. 浏览器操作频率不超过 3 次/秒。

# 检索策略
- 关键词用组合维度：产品词 × 同义词/俗称 × 行业词 × 采购环节词。
- 明确筛选条件后再翻页：发布时间、区域、采购人类型、金额、采购方式、公告类型。
- 翻页到“结果明显无关”或“已覆盖时间窗”即停止。
- 记录本次检索参数（站点/关键词/筛选/页数/时间）。
- 站点不可访问、需付费或仅会员可见：标注“受限”，不尝试技术规避。

# 信息提取字段
项目名称｜项目编号｜公告类型｜采购人｜代理机构｜预算/控制价/中标金额（注明币种与含税口径）｜采购方式｜标段/包组｜发布媒体｜发布时间｜报名截止｜投标截止/开标｜交付期｜资格与资质要求｜评分办法要点｜联系人/电话/地址（仅公开展示的）｜来源 URL｜抓取时间｜信息完整度。
规范化：日期 YYYY-MM-DD HH:mm；金额注明单位与是否含税；多站点冲突以采购人官方平台为准。

# 去重与变更
- 去重键：采购人 + 项目编号（或规范化项目名称） + 公告类型 + 发布日期。
- 与上次快照比对，输出增量：新增 / 关键字段变更 / 截止临近（≤3天）/ 已截止 / 已出结果 / 流标废标。

# 输出风格
- 中文，先结论后依据；能表格不写段落；金额、日期、比例给具体数字。
- 每个事实后跟来源与时间；没有来源的话不说。
- 不用“据了解”“业内普遍认为”等无源表述。
- 长任务分阶段汇报：检索完成 → 抽取完成 → 整理完成。

# 红线
- 禁止暴露、暗示或部分展示账号密码、Cookie、Token。
- 禁止编造项目、金额、联系人、中标单位、工商数据。
- 禁止绕过验证码、反爬机制、付费墙，或使用他人账号。
- 禁止替用户做投标承诺、报价、签署、对外发送任何消息。
- 禁止把个人隐私（身份证、私人手机号、住址）写入长期档案。
```

保存。

### 4.3 浏览器设置

- Cherry Studio → 设置 → 浏览器：开启 **允许智能体控制浏览器**。
- 首次使用在智能体浏览器中手动登录剑鱼，登录态会保存在浏览器 profile。
- 不要在同一浏览器里登录多个剑鱼账号，避免串号。

---

## 5. Step 3：准备目录与依赖

### 5.1 建目录

```powershell
$root = "D:\Tnotices"
New-Item -ItemType Directory -Force -Path $root | Out-Null
@("scripts","data","config","reports","docs") | ForEach-Object {
  New-Item -ItemType Directory -Force -Path (Join-Path $root $_) | Out-Null
}
```

> 路径可自定，但后文命令以 `D:\Tnotices` 为例。

### 5.2 检查依赖

```powershell
git --version
uv --version
uv run python --version
```

`uv` 通常在 `C:\Users\<用户名>\.cherrystudio\bin\uv.exe`。如果命令找不到，用完整路径或在系统 PATH 中加入该目录。

---

## 6. Step 4：写入配置与看板文件

在 `D:\Tnotices` 下创建以下文件。

### 6.1 `config/settings.json`

```json
{
  "gitea": {
    "base_url": "http://<gitea-host>:3000",
    "owner": "admin",
    "repo": "Tnotices",
    "branch": "main",
    "private": true
  },
  "region": ["<区域1>", "<区域2>"],
  "close_after_days": 30,
  "urgent_days": 7,
  "keywords": [
    "服务器", "存储", "算力", "智算", "人工智能", "大模型",
    "高性能计算", "超算", "数据中心", "云计算", "云平台",
    "信创", "国产化", "网络安全", "网络设备", "机房",
    "信息化", "智慧城市", "智慧医院", "智慧校园",
    "容灾", "备份", "云桌面", "视频监控", "系统集成"
  ]
}
```

把 `base_url`、`owner`、`repo` 改成你的 Gitea 地址和账号。

### 6.2 `.gitignore`

```gitignore
.gitea_token
__pycache__/
*.pyc
.venv/
*.log
.DS_Store
```

### 6.3 `start_dashboard.bat`

```bat
@echo off
cd /d %~dp0
uv run python scripts\serve.py 8088
pause
```

### 6.4 `scripts/serve.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地预览 Tnotices 看板：uv run python scripts/serve.py [port]"""
import http.server
import socketserver
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8088


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


with socketserver.TCPServer(("0.0.0.0", PORT), Handler) as httpd:
    print(f"Tnotices dashboard: http://127.0.0.1:{PORT}/index.html")
    print(f"LAN: http://<本机IP>:{PORT}/index.html")
    httpd.serve_forever()
```

---

## 7. Step 5：部署核心脚本

核心脚本 `scripts/tnotices.py` 负责：导入、批次、更新、事件、状态重算、README/看板渲染、Gitea 建库与推送。

**获取方式（三选一）**：

0. **下载模板包**：仓库 `dist/Tnotices_template_20261020.zip`，解压到 `D:\Tnotices`（已含 scripts/config/docs/start_dashboard.bat，data 为空目录）。
1. **从参考仓库复制**：把 `scripts/tnotices.py` 原样复制到 `D:\Tnotices\scripts\`。
2. **按附录 A 手工创建**：见 `docs/附录A-核心脚本.md`。

创建后验证：

```powershell
cd D:\Tnotices
uv run python scripts\tnotices.py --help
```

应看到 `import-csv / update / event / add / recompute / batch / render / init-repo / push` 子命令。

> 关键设计：`data/projects.json` 是唯一数据源；`README.md`、`index.html` 都由脚本生成，**不要手改**，否则下次渲染会被覆盖。

---

## 8. Step 6：导入初始商机

### 8.1 CSV 模板

至少包含以下列（UTF-8 BOM，Excel 用“CSV UTF-8”保存）：

```csv
序号,地区,项目名称,采购人,公告类型,预算(万元),发布时间,投标截止,产品线匹配,优先级,项目编号,采购人联系人/电话,代理机构,代理联系人/电话,报名截止,详情页URL,原文链接
1,<区域1>-<城市>,示例AI算力服务器采购,某银行,招标,390,2026-10-12,2026-10-23 14:00,AI服务器/算力,A,EXAMPLE-001,联系人A / 028-00000000,某招标代理,联系人B / 028-11111111,2026-10-20,https://www.jianyu360.cn/nologin/content/xxx.html,https://example.com/notice/1
```

### 8.2 导入

```powershell
cd D:\Tnotices
uv run python scripts\tnotices.py import-csv --path "D:\path\to\your.csv"
```

说明：

- 导入后所有项目状态为 `watching`，`owner` 为空，需要人工分配。
- 预算列填纯数字，不要带千分位逗号（如 `1150` 而不是 `1,150`）；“未披露”会转为空值。
- 详情页 URL 用于生成 `jianyu_id`；原文链接用于首页跳转。

### 8.3 从零开始（可选）

不导入 CSV，直接让智能体按 `config/daily_prompt.md` 抓取新商机，用 `add` 子命令逐条新增。

---

## 9. Step 7：本地渲染与看板验收

```powershell
cd D:\Tnotices
uv run python scripts\tnotices.py recompute
uv run python scripts\tnotices.py render
```

生成：

- `README.md`：项目清单、统计、今日变更、已完结
- `index.html`：交互看板（数据已内嵌，可离线打开）

启动看板：

```powershell
.\start_dashboard.bat
```

浏览器访问 `http://127.0.0.1:8088/index.html`；局域网访问 `http://<本机IP>:8088/index.html`。也可以直接双击 `index.html`（数据已内嵌，无需服务）。

验收点：

- 统计卡片数字与 `data/projects.json` 条数一致
- 搜索、地区、状态、优先级筛选可用
- 点击项目名能跳原文/剑鱼详情
- 7 天内截止的行显示为橙色

---

## 10. Step 8：配置 Gitea 并推送

### 10.1 创建专用 Token（推荐）

Gitea → 右上角头像 → **设置 → 应用 → 生成令牌**：

- 令牌名称：`tnotices-bot`
- 权限范围：`write:repository`、`write:user`（至少这两个；按 Gitea 版本可能叫 `repo`、`user`）

生成后只显示一次。**不要写入仓库、不要发到聊天里。**

### 10.2 配置环境变量

当前用户级（新开终端生效）：

```powershell
[Environment]::SetEnvironmentVariable("GITEA_TOKEN", "你的令牌", "User")
```

当前会话临时生效：

```powershell
$env:GITEA_TOKEN = "你的令牌"
```

测试：

```powershell
$h = @{ Authorization = "token $env:GITEA_TOKEN" }
Invoke-RestMethod -Uri "http://<gitea-host>:3000/api/v1/user" -Headers $h | Select-Object login
```

返回你的 login 即成功。

### 10.3 备选：使用 Windows 凭据管理器

如果不想用 Token：

```powershell
git config --global credential.helper manager
```

第一次 `git push` 时输入 Gitea 用户名/密码，Windows 会保存；后续脚本自动使用。**不要把密码写进脚本或 URL。**

### 10.4 建库与首次推送

```powershell
cd D:\Tnotices
uv run python scripts\tnotices.py init-repo
uv run python scripts\tnotices.py push --message "init: Tnotices"
```

脚本会：

1. 调 Gitea API 检查/创建仓库（默认私有）
2. `git init`（如未初始化）
3. 设置本地提交身份 `Tnotices Bot <tnotices@local>`
4. `git add/commit/push`

验收：

- 打开 `http://<gitea>/<owner>/Tnotices`，首页显示 README 项目清单
- 仓库为私有
- 提交历史有 `init: Tnotices`

> 如果 owner 是组织而不是个人，脚本的 `/api/v1/user/repos` 不适用；请先在 Gitea 手动建组织仓库，把 `settings.json` 的 `owner` 改成组织名，再执行 `push`。

---

## 11. Step 9：配置每日定时任务

### 11.1 准备每日提示词

把 `config/daily_prompt.md` 放到项目里（完整内容见 `docs/附录B-每日任务提示词.md`）。模板中的 `D:\Tnotices`、`<owner>`、`<gitea>` 请按实际环境替换。它定义了：

- 滚动批次：每天最多 30 个项目
- 变更/中标/异常/质疑四类判断
- 新增商机的关键词与去重规则
- `recompute → render → push` 收尾
- 验证码/登录失效即停

### 11.2 在 Cherry Studio 建定时任务

Cherry Studio → **定时任务 → 新建**：

| 项 | 值 |
|---|---|
| 名称 | `Tnotices 每日标讯跟进` |
| 时间 | 每天 08:30（cron `30 8 * * *`） |
| 智能体 | 标讯助手（<区域1>/<区域2>） |
| 会话 | 每次新建会话（避免上下文膨胀） |
| 超时 | 30 分钟 |

提示词：

```text
执行 Tnotices 每日标讯跟进任务：

1. 读取并严格执行 D:\Tnotices\config\daily_prompt.md
2. 工作目录：D:\Tnotices
3. 检查 data/projects.json 中所有 status != closed 的项目，识别：更正/变更、中标/成交、废标/流标/终止、答疑/质疑
4. 抓取<区域1>/<区域2>最近 1-3 天新商机，去重后新增
5. 执行 recompute → render → push
6. 在 reports/YYYY-MM-DD.md 写日报

硬性要求：
- 浏览器操作 ≤3 次/秒
- 遇到验证码/登录失效立即停止，不识别、不绕过、不反复提交
- 不编造数据，未披露字段写“未披露”
- 不打印账号密码或 Token
- 完成后回复：新增/更新/中标/异常数量 + 7 天内截止项目 + 需人工确认事项
```

### 11.3 首次手动跑一遍

不要等第二天。先在智能体对话里发：

```text
现在按 D:\Tnotices\config\daily_prompt.md 跑一次，限制检查 5 个项目，验证流程。
```

检查：

- 是否生成 `data/today_batch.json`
- 是否更新 `reports/2026-10-20.md`
- 是否 push 成功
- Gitea 首页是否有变化

### 11.4 时区说明

Cherry 的 cron 按本地时区执行；如果界面显示 UTC 时间，`08:30` 可能显示为 `00:30Z`。以实际下一次运行时间为准。

---

## 12. Step 10：每日巡检规则

### 12.1 状态机

| 状态 | 含义 | 进入条件 |
|---|---|---|
| `new` | 新发现 | 刚入库 |
| `watching` | 观察中 | 初始/待评估 |
| `evaluating` | 评估中 | 销售开始评估 |
| `preparing` | 投标准备 | 决定投，准备材料 |
| `submitted` | 已投标 | 已递交 |
| `result_pending` | 结果待出 | 投标截止已过 |
| `won` | 已中标 | 中标/成交公告 |
| `lost` | 未中标 | 结果公告未中标 |
| `failed` | 流标/废标 | 废标/流标 |
| `cancelled` | 已终止 | 终止公告 |
| `closed` | 已完结 | 中标公示满 30 天 |

### 12.2 事件类型

| 类型 | 触发 | 写入字段 |
|---|---|---|
| `created` | 新增项目 | timeline |
| `change` | 更正/变更/补遗/延期 | bid_deadline、budget 等 |
| `question` | 答疑/澄清/质疑/投诉 | next_action |
| `award` | 中标/成交 | winner、win_amount、award_date |
| `anomaly` | 废标/流标/终止 | status、原因 |
| `pipeline` | 采购意向/预告 | 不改变主状态 |
| `status` | 状态自动变更 | status |
| `closed` | 满 30 天自动完结 | closed_at、closed_reason |

### 12.3 检索优先级

1. 项目编号（最精确）
2. 项目名称全文（标题检索）
3. 采购人 + 关键词（名称被截断时）

### 12.4 完结规则

`recompute` 每次执行：

- 有 `award_date` 且 `today - award_date >= 30` → `closed`
- 投标截止已过且状态为 `new/watching/evaluating/preparing/submitted` → `result_pending`
- 7 天内截止 → `urgent=true`

**已完结项目不再进入每日批次**，只在 README“已完结项目”里保留。

---

## 13. 日常使用

### 13.1 查看

- Gitea 仓库首页：项目清单、统计、今日变更、已完结
- 本地看板：`start_dashboard.bat` → `http://127.0.0.1:8088/index.html`
- 日报：`reports/YYYY-MM-DD.md`

### 13.2 更新项目

```powershell
cd D:\Tnotices

# 改状态/负责人/优先级
uv run python scripts\tnotices.py update --id T20261020-001 --set status=preparing --set owner="张三" --set priority=A

# 回填中标
uv run python scripts\tnotices.py update --id T20261020-001 --set status=won --set winner="某某公司" --set win_amount_wan=390 --set award_date=2026-10-23

# 记录事件
uv run python scripts\tnotices.py event --id T20261020-001 --type change --title "更正公告" --detail "投标截止延至 2026-10-30" --date 2026-10-25 --source "https://..."
```

### 13.3 新增项目

准备 `new.json`：

```json
{
  "project_name": "某某医院智算中心服务器采购",
  "project_no": "SC-2026-001",
  "buyer": "某某医院",
  "agency": "某某招标代理",
  "region": "<区域1>-<城市>",
  "industry": "医疗信息化",
  "budget_wan": 500,
  "publish_date": "2026-10-20",
  "bid_deadline": "2026-11-05 10:00",
  "status": "watching",
  "priority": "A",
  "source_url": "https://...",
  "jianyu_url": "https://...",
  "products": "AI服务器/存储",
  "owner": ""
}
```

```powershell
uv run python scripts\tnotices.py add --json new.json
```

### 13.4 每日收尾

```powershell
uv run python scripts\tnotices.py recompute
uv run python scripts\tnotices.py render
uv run python scripts\tnotices.py push --message "daily: 2026-10-21"
```

---

## 14. 数据规范

### 14.1 `data/projects.json`

数组，每个元素一个项目。关键字段：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| id | string | 是 | `TYYYYMMDD-NNN` |
| project_name | string | 是 | 项目名称 |
| project_no | string | 否 | 项目编号，去重优先 |
| buyer / agency | string | 是/否 | 业主/代理 |
| region | string | 是 | 如 `<区域1>-<城市>` |
| budget_wan | number | 否 | 预算（万元） |
| publish_date | string | 否 | 发布日 |
| sign_deadline | string | 否 | 报名截止 |
| bid_deadline | string | 否 | 投标截止/开标 |
| status | string | 是 | 状态机 |
| priority | string | 否 | A/B/C |
| winner / win_amount_wan / award_date | string/number/string | 否 | 中标信息 |
| source_url / jianyu_url | string | 否 | 原文/剑鱼详情 |
| contacts | object | 否 | `{buyer, agency}` |
| owner | string | 否 | 负责人 |
| timeline | array | 是 | 事件列表 |
| closed_at / closed_reason | string | 否 | 完结信息 |

### 14.2 `data/events.jsonl`

每行一个 JSON，只追加不改写：

```json
{"id":"T20261020-001","date":"2026-10-23","type":"award","title":"中标公告","detail":"中标：某某公司，390万","source":"https://..."}
```

### 14.3 编码

- 所有 JSON/CSV/Markdown 用 **UTF-8**
- Excel 导入的 CSV 用 **CSV UTF-8（带 BOM）**
- PowerShell 5.1 读取 UTF-8 文件时显式加 `-Encoding UTF8`

---

## 15. 关键词矩阵（<区域1>/<区域2>）

### 15.1 算力/AI

`算力`、`智算`、`人工智能`、`AI`、`大模型`、`GPU`、`NPU`、`昇腾`、`鲲鹏`、`海光`、`国产GPU`、`智算中心`、`算力中心`、`算力平台`、`算力租赁`、`高性能计算`、`超算`、`HPC`、`推理`、`训练`、`智能体`、`AIGC`、`多模态`

### 15.2 服务器/存储

`服务器`、`机架式服务器`、`GPU服务器`、`AI服务器`、`推理服务器`、`信创服务器`、`国产服务器`、`C86服务器`、`ARM服务器`、`超融合`、`一体机`、`存储`、`分布式存储`、`全闪存`、`磁盘阵列`、`NAS`、`SAN`、`对象存储`、`存储扩容`、`备份`、`容灾`、`双活`

### 15.3 数据中心/机房

`数据中心`、`IDC`、`机房`、`机房建设`、`机房改造`、`机房租赁`、`模块化机房`、`微模块`、`机柜`、`冷通道`、`液冷`、`精密空调`、`UPS`、`动环监控`

### 15.4 云/平台/信创

`云计算`、`云平台`、`私有云`、`混合云`、`政务云`、`行业云`、`云桌面`、`虚拟化`、`容器`、`云原生`、`大数据平台`、`数据中台`、`数据湖`、`数据库`、`中间件`、`信创`、`国产化`、`自主可控`、`适配改造`、`迁移`

### 15.5 网络/安全

`交换机`、`路由器`、`防火墙`、`负载均衡`、`网络设备`、`校园网`、`园区网`、`SDN`、`网络安全`、`等保`、`密码应用`、`零信任`、`态势感知`、`视频监控`、`存储扩容`

### 15.6 行业场景

- 政府：数字政府、政务云、城市大脑、智慧城市、一网通办、雪亮工程、应急指挥
- 医疗：智慧医院、HIS、PACS、影像云、医疗大数据、AI辅助诊断、医疗大模型
- 教育：智慧校园、教育信息化、校园网、实训室、AI实验室、算力平台
- 金融：信创、核心系统、容灾、双活、分布式存储、云平台、负载均衡
- 能源/制造：工业互联网、智能矿山、数字孪生、边缘计算、工业质检

### 15.7 区域词

- `<区域1>`：`<城市1>`、`<城市2>`、`<城市3>`
- `<区域2>`：`<城市4>`、`<城市5>`、`<城市6>`

> 优先用剑鱼的“地区”筛选，不要把地名写进关键词；地名只用于筛不到的重点城市补充检索。

---

## 16. 故障排查

### 16.1 模型不调用工具

- 确认 icompify 模型支持 Function Calling
- 确认 Cherry 里该模型“工具调用”开关已开
- 换一个支持工具调用的模型测试
- 系统提示词里明确写“请调用浏览器工具打开…”

### 16.2 `uv` 找不到

```powershell
& "$env:USERPROFILE\.cherrystudio\bin\uv.exe" --version
```

把 `C:\Users\<用户名>\.cherrystudio\bin` 加入 PATH，或所有命令用完整路径。

### 16.3 Gitea 401/403

- 401：Token 错误/过期；重新生成，确认 `Authorization: token <TOKEN>`
- 403：Token 权限不足；加 `write:repository`、`write:user`
- 组织仓库：脚本只支持个人 `/user/repos`；先手动建组织仓库，改 `owner` 后 `push`

### 16.4 `git push` 要求输入密码

- 配置 `git config --global credential.helper manager`，首次输入后保存
- 或设置 `GITEA_TOKEN`：脚本的 API 与 `git push` 都会用它（通过 `GIT_CONFIG_COUNT/http.extraHeader` 注入，不写入 remote URL）。设置后无需再配 credential helper
- 不要把 Token 写进 remote URL、脚本或提交文件

### 16.5 中文乱码

- PowerShell 5.1 默认 ANSI：读取 UTF-8 文件用 `Get-Content -Raw -Encoding UTF8`
- CSV 用 Excel 的“CSV UTF-8”保存
- Python 脚本统一 `encoding="utf-8"`

### 16.6 8088 端口被占用

```powershell
netstat -ano | findstr :8088
```

换端口：`uv run python scripts\serve.py 8090`。

### 16.7 README 没更新

```powershell
uv run python scripts\tnotices.py render
uv run python scripts\tnotices.py push --message "render"
```

检查 `data/projects.json` 是否为合法 JSON；脚本渲染前会 `recompute` 并保存。

### 16.8 定时任务没跑

- Cherry Studio 是否保持运行
- 任务是否启用
- cron 时区是否正确（08:30 本地时间）
- 智能体是否还有浏览器/文件权限
- 看任务历史与日志

### 16.9 剑鱼验证码

- 立即停止，不要识别/绕过/反复提交
- 在智能体浏览器中手动完成
- 完成后再让智能体继续
- 若频繁触发，降低频率、减少单日检查数量

### 16.10 详情页无结构化信息

- 采购意向/招标计划常常没有联系人/代理
- 以列表页字段为准，标记“详情页无结构化信息”
- 不要编造联系人

---

## 17. 安全与合规

1. **最小权限 Token**：只给 `write:repository`、`write:user`；不要用 admin 密码。
2. **私有仓库**：`private: true`；不要把客户联系人、报价策略放到公开仓库。
3. **凭据不落盘**：`.gitignore` 排除 `.gitea_token`；不在提示词、日报、日志中打印 Token。
4. **只读浏览**：不提交表单、不报价、不注册、不购买会员、不绕过付费墙。
5. **验证码即停**：不识别、不绕过、不反复提交。
6. **频率控制**：浏览器 ≤3 次/秒；单日最多 30 个项目；不做全站遍历。
7. **隐私**：只记录公告公开的联系人；不写身份证、私人住址。
8. **备份**：Gitea 提交历史即快照；建议每周打 tag 或导出 `data/projects.json`。

---

## 18. 复现验收清单

- [ ] icompify 模型连接成功
- [ ] 模型能调用浏览器工具打开 example.com
- [ ] 智能体已创建，系统提示词已保存
- [ ] 剑鱼已在智能体浏览器中登录
- [ ] `uv run python scripts\tnotices.py --help` 正常
- [ ] CSV 导入成功，`data/projects.json` 条数正确
- [ ] `recompute` + `render` 生成 README/index.html
- [ ] `start_dashboard.bat` 打开看板，筛选可用
- [ ] Gitea Token 测试 `/api/v1/user` 成功
- [ ] `init-repo` + `push` 成功，仓库首页显示 README
- [ ] 定时任务已创建，下一次运行时间正确
- [ ] 手动跑一次 5 个项目的小批次，日报生成、push 成功
- [ ] 验证码/登录失效时智能体能停止并报告

---

## 附录

- [附录 A：核心脚本全文](./附录A-核心脚本.md)
- [附录 B：每日任务提示词全文](./附录B-每日任务提示词.md)
- [附录 C：关键词矩阵完整版](./关键词矩阵.md)
- 参考实现仓库：`http://<gitea-host>:3000/<owner>/Tnotices`

> 建议把本指南与三个附录一起放进 Gitea `docs/` 目录，新同事按本文从 Step 1 走到 Step 10 即可复现。




---

# Tnotices 值班手册（一页纸）

> 适用：每日 08:30 自动任务之后｜值班人 08:35 前完成｜版本 2026-10-20

## 一、每天 6 项检查（5 分钟）

| # | 检查项 | 在哪看 | 通过标准 | 异常动作 |
|---|---|---|---|---|
| 1 | 自动任务是否成功 | Cherry 定时任务历史 | 状态成功、有日报 | 失败→看日志→手动重跑 |
| 2 | 首页统计是否合理 | Gitea 仓库首页 | 在跟/7天内/已中标/已完结有数字 | 为 0 或骤降→检查数据文件 |
| 3 | 今日变更 | 首页“今日变更” | 变更/中标/异常都有记录 | 无记录但已知有公告→手动补 |
| 4 | 7 天内截止 | 首页橙色截止行 | 每条都有 owner | 无 owner→立即分配 |
| 5 | 异常项目 | 状态=流标/废标/终止 | 原因已记录 | 原因缺失→回原站核对 |
| 6 | 满 30 天完结 | 首页“已完结项目” | 中标满 30 天已自动移入 | 未移入→跑 recompute |

## 二、事件处理 SOP

| 事件 | 判断依据 | 必须动作 | 时限 |
|---|---|---|---|
| 更正/变更/补遗/延期 | 标题含“更正/变更/补遗/延期” | 更新投标截止/预算/参数；写 `change` 事件；通知 owner | 2 小时内 |
| 中标/成交 | 标题含“中标/成交结果” | 回填中标单位、金额、公示日期；状态改 `won`；写 `award` 事件 | 当天 |
| 废标/流标/终止 | 标题含“废标/流标/终止” | 状态改 `failed/cancelled`；写 `anomaly` 事件；评估是否重招 | 当天 |
| 答疑/澄清/质疑/投诉 | 标题含“答疑/澄清/质疑/投诉” | 写 `question` 事件；把需澄清事项写入 `next_action` | 2 小时内 |
| 采购意向/招标预告 | 标题含“采购意向/预告” | 写 `pipeline` 事件；不改主状态；安排提前接触 | 3 天内 |

## 三、升级规则（不要自己扛）

| 情况 | 动作 |
|---|---|
| 剑鱼出现图形验证码 | 立即停止自动操作；人工在浏览器完成；不要识别/绕过/反复提交 |
| 剑鱼登录失效 | 停止任务；通知管理员重新登录；不要连续试密码 |
| Gitea push 失败 | 保留本地 commit；检查 `GITEA_TOKEN`/凭据；不要强推 |
| 公告数据矛盾（预算/标段/截止不一致） | 标记“待核实”；以采购人官方平台为准；不要猜 |
| 7 天内截止且无 owner | 立即在群里 @ 区域负责人；当天必须分配 |
| 同一项目出现多条同名公告 | 先核对项目编号；不同标段分别建档，不合并 |

## 四、每周 / 每月

| 周期 | 动作 | 输出 |
|---|---|---|
| 每周一 | 检查 owner 覆盖率、30 天内完结是否正常、关键词命中率 | 周报 3 行 |
| 每周五 | 清理重复项目、补全缺失的联系人/原文链接 | 数据质量清单 |
| 每月 | 更新价格基线、竞品中标地图、调整关键词矩阵 | 月度复盘 |

## 五、命令速查

```powershell
cd D:\Tnotices

# 当日批次
uv run python scripts\tnotices.py batch --limit 30 --out data\today_batch.json

# 改状态/负责人
uv run python scripts\tnotices.py update --id T20261020-001 --set status=preparing --set owner="张三"

# 记事件
uv run python scripts\tnotices.py event --id T20261020-001 --type change --title "更正公告" --detail "截止延至 10-30" --date 2026-10-25 --source "https://..."

# 收尾
uv run python scripts\tnotices.py recompute
uv run python scripts\tnotices.py render
uv run python scripts\tnotices.py push --message "daily: 2026-10-21"
```

## 六、红线

- 不把账号密码、Cookie、Token 发到群里或写进文件。
- 不编造中标单位、金额、联系人；没有就写“未披露”。
- 不绕过验证码、反爬、付费墙。
- 不替销售做投标/报价承诺。
- 不把客户联系人私人手机号写入长期档案。

## 七、今日交接

| 项 | 内容 |
|---|---|
| 值班人 | __________ |
| 待分配 owner | __________ 条 |
| 7 天内截止 | __________ 条 |
| 异常/待核实 | __________ 条 |
| 备注 | __________ |



---

# 附录 A：核心脚本全文

> 文件路径：`scripts/tnotices.py`。直接复制下方代码保存为同名文件即可。

```python
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

```


---

# 附录 B：每日任务提示词全文（通用模板）

> 文件路径：`config/daily_prompt.md`。模板中的 `D:\Tnotices`、`<owner>`、`<gitea>` 请按实际替换。

```markdown
# Tnotices 每日标讯跟进任务（给智能体）

你是<公司><区域>区域的标讯跟进助手。每天执行一次，目标：更新 Gitea 仓库 `<owner>/Tnotices`，保证项目清单、变更、中标结果、异常状态都是最新的。

## 0. 环境与约束

- 工作目录：`D:\Tnotices`
- 数据源：剑鱼标讯（已登录个人版账号，浏览器操作 ≤3 次/秒）
- 仓库：`http://<gitea-host>:3000/<owner>/Tnotices`
- 凭据：本机 git credential 已保存；不要在任何输出、文件、日志中打印账号密码或 Token
- 遇到图形验证码：立即停止，记录“验证码阻断”，不要识别/绕过/反复提交
- 不编造：页面没有的字段写“未披露”，推断值加 `[推测]`

## 1. 读取现有项目（滚动批次）

```powershell
cd D:\Tnotices
uv run python scripts\tnotices.py recompute
uv run python scripts\tnotices.py batch --limit 30 --out data\today_batch.json
```

读取 `data/today_batch.json`。排序规则：已投标/结果待出 → 7 天内截止 → 近 30 天截止 → 其余按 last_checked 最久优先。单日最多检查 30 个项目，保证 60 个项目在 2–3 天内轮检一遍。

对每个项目，用以下顺序检索剑鱼：

1. 项目编号（最精确）
2. 项目名称全文（标题检索）
3. 采购人 + 关键词（项目名称被截断时）

检索时间范围设为“最近 30 天”，信息类型“全部”。

## 2. 判断是否出现新公告

对每个项目，比对 `timeline` 中已有公告标题/日期，识别以下新增：

| 公告类型 | 处理 |
|---|---|
| 更正公告 / 变更公告 / 补遗 / 延期 | 更新 `bid_deadline`、`sign_deadline`、预算等字段；追加 event `change`；重新评估优先级 |
| 答疑 / 澄清 / 质疑 / 投诉 | 追加 event `question`；在 `next_action` 写明需澄清事项 |
| 中标公告 / 成交公告 | 写入 `winner`、`win_amount_wan`、`award_date`；status=`won`；追加 event `award` |
| 废标 / 流标 / 终止 | status=`failed` 或 `cancelled`；追加 event `anomaly`；记录原因 |
| 资格预审 / 招标预告 / 采购意向 | 追加 event `pipeline`；不改变主状态 |

更新命令示例：

```powershell
uv run python scripts\tnotices.py update --id T20261020-001 --set status=won --set winner="xxx公司" --set win_amount_wan=390 --set award_date=2026-10-23
uv run python scripts\tnotices.py event --id T20261020-001 --type award --title "中标公告" --detail "中标：xxx公司，390万" --date 2026-10-23 --source "https://..."
```

注意：
- `award_date` 填中标公告发布日期，不是中标通知书日期。
- 中标公示满 30 天后，`recompute` 会自动把状态改为 `closed`，不需要手动关。
- 如果公告只有 PDF/扫描件，读取标题、项目编号、发布日期即可，正文关键字段标“未披露”。

## 3. 抓取新商机

用 `config/settings.json` 中的 25 个关键词，分别检索<区域1>、<区域2>，发布时间“最近 1 天”（如当天无结果可放宽到 3 天），标题检索。筛选与<公司>产品线相关的项目，新增到平台：

```powershell
uv run python scripts\tnotices.py add --json new_project.json
```

新增字段至少包含：`project_name`、`buyer`、`region`、`budget_wan`、`publish_date`、`bid_deadline`、`source_url`、`jianyu_url`、`priority`、`products`。

去重键：`project_no`（优先）或 `project_name + buyer + publish_date`。已存在则只追加 event，不重复新增。

## 4. 生成与同步

```powershell
uv run python scripts\tnotices.py recompute
uv run python scripts\tnotices.py render
uv run python scripts\tnotices.py push --message "daily: 2026-10-20"
```

`push` 会自动：创建仓库（不存在时）、git add/commit、push 到 Gitea。README.md 会显示在仓库首页。

## 5. 输出日报

在 `reports/YYYY-MM-DD.md` 写当日摘要：

- 新增项目数、更新项目数、中标数、异常数
- 7 天内截止项目（项目名/业主/截止/负责人）
- 需要人工确认的事项
- 验证码/登录/数据受限情况

## 6. 失败处理

- 登录失效：停止，提示用户在浏览器手动登录
- 验证码：停止，提示用户手动完成
- Gitea push 失败：保留本地 commit，输出失败原因，不要强推
- 剑鱼页面结构变化：停止自动解析，保留原始 URL，提示人工核对

```



---

# 标讯关键词矩阵（通用）

> 适用：服务器、存储、AI/算力、HPC、云、数据中心、信创、行业信息化。
> 使用方法：按「产品词 × 同义词 × 行业词 × 采购环节词」组合检索，优先标题检索。

---

## 0. 检索技巧

| 技巧 | 做法 |
|---|---|
| 标题检索 | 搜索范围选「标题」，噪声比全文低一个数量级 |
| 多词 AND | 关键词框用空格分隔，如 `算力 服务器` |
| 采购单位锁定 | 更多筛选 → 采购单位 → 输入单位名 → 添加标签 |
| 地区 | 更多筛选 → 地区；一次一个省，分省跑 |
| 时间 | 「最近30天」做在架标；「最近1年」做价格/竞品基线 |
| 截止 | 更多筛选 → 截止时间 →「投标未截止」，过滤过期信息 |
| 详情 | 列表标题点开；详情页通常有项目编号、代理、联系人、原文链接 |

> 高频访问详情页会触发图形验证码；触发后停止自动访问，人工完成或改用列表摘要。

---

## 1. 算力 / AI

| 层级 | 关键词 |
|---|---|
| 高命中 | 算力、智算、人工智能、AI、大模型、GPU、服务器 |
| 精准 | 智算中心、算力中心、人工智能计算中心、算力平台、算力服务、算力租赁、智能算力、通用算力、异构算力 |
| 技术 | 深度学习、机器学习、推理、训练、模型训练、算法平台、智能体、AIGC、多模态、计算机视觉、自然语言处理 |
| 芯片/生态 | 英伟达、A800、H800、H100、H200、L20、昇腾、鲲鹏、海光、寒武纪、国产GPU、国产算力 |
| 场景 | AI实验室、人工智能实验室、AI创新中心、人工智能产业园、AI中试基地、机器人、智慧医疗AI |

**组合**：`算力 服务器`、`智算中心`、`人工智能 平台`、`大模型 平台`、`GPU 服务器`、`昇腾 服务器`、`算力 租赁`

---

## 2. 服务器 / 存储

| 层级 | 关键词 |
|---|---|
| 服务器 | 服务器、机架式服务器、刀片服务器、塔式服务器、GPU服务器、AI服务器、推理服务器、训练服务器、应用服务器、数据库服务器、存储服务器 |
| 国产化 | 信创服务器、国产服务器、C86服务器、ARM服务器、鲲鹏服务器、昇腾服务器、海光服务器、飞腾服务器、自主可控 |
| 存储 | 存储、分布式存储、集中式存储、全闪存、混闪、磁盘阵列、NAS、SAN、对象存储、块存储、文件存储、存储扩容、存储阵列 |
| 数据保护 | 备份、备份一体机、容灾、双活、两地三中心、数据归档、数据迁移、数据保护 |
| 形态 | 超融合、一体机、云桌面一体机、数据库一体机、信创一体机 |

**组合**：`服务器 采购`、`分布式存储`、`全闪存`、`超融合`、`信创 服务器`、`国产化 服务器`、`存储 扩容`、`容灾 备份`

---

## 3. 数据中心 / 机房

| 层级 | 关键词 |
|---|---|
| 数据中心 | 数据中心、IDC、互联网数据中心、算力基础设施、数据基础设施、智算中心 |
| 机房 | 机房、机房建设、机房改造、机房升级、机房搬迁、机房租赁、机柜租赁、模块化机房、微模块 |
| 配套 | 精密空调、UPS、供配电、列头柜、机柜、冷通道、液冷、风冷、动环监控、消防、防雷、接地 |
| 绿色 | PUE、节能改造、绿色数据中心、余热回收 |

**组合**：`数据中心 建设`、`机房 改造`、`模块化机房`、`液冷`、`机柜 租赁`

---

## 4. 云 / 平台 / 软件

| 层级 | 关键词 |
|---|---|
| 云 | 云计算、云平台、云服务、私有云、公有云、混合云、政务云、行业云、专有云、云资源池、云桌面、虚拟化 |
| 平台 | 大数据平台、数据中台、数据湖、数据仓库、数据治理、数据共享、业务中台、技术中台 |
| 基础软件 | 数据库、中间件、操作系统、Linux、容器、云原生、微服务、Kubernetes |
| 信创 | 信创、国产化、自主可控、适配改造、迁移、替代、国芯、国产芯片、国产操作系统、国产数据库 |
| 服务 | 运维、维保、驻场、系统集成、等保、等级保护、密评、密码应用 |

**组合**：`政务云`、`私有云`、`云桌面`、`信创 改造`、`国产化 适配`、`大数据平台`、`数据库 采购`

---

## 5. 网络 / 安全

| 层级 | 关键词 |
|---|---|
| 网络 | 交换机、路由器、防火墙、负载均衡、网络设备、校园网、园区网、骨干网、SDN、网络扩容、网络改造 |
| 安全 | 网络安全、数据安全、等保、等级保护、密码应用、零信任、态势感知、堡垒机、日志审计、终端安全 |
| 视频 | 视频监控、安防、存储扩容、视频云、雪亮工程、智慧安防 |

**组合**：`核心交换机`、`网络设备 采购`、`网络安全 建设`、`等保 测评`、`视频监控 存储`

---

## 6. 行业场景

| 行业 | 关键词 |
|---|---|
| 政府/事业单位 | 数字政府、政务云、政务大数据、城市大脑、智慧城市、一网通办、一网统管、应急指挥、雪亮工程、信创改造 |
| 医疗 | 智慧医院、医院信息化、HIS、PACS、LIS、EMR、影像云、医疗大数据、互联网医院、医保信息化、AI辅助诊断、医疗大模型 |
| 教育 | 智慧校园、教育信息化、校园网、数据中心、实训室、AI实验室、算力平台、虚拟仿真、多媒体教室 |
| 金融 | 信创、核心系统、容灾、双活、分布式存储、云平台、负载均衡、数据库、智能风控、AI大模型 |
| 能源/制造 | 工业互联网、智能矿山、数字孪生、边缘计算、工业质检、SCADA、生产数据中心 |
| 运营商 | 算力网络、IDC、云资源池、边缘节点、算力调度 |
| 央国企 | 信创、国产化替代、集团云、数据中台、灾备中心 |

---

## 7. 区域词

优先用平台「地区」筛选，不要把地名写进关键词。地域词只用于重点城市补充检索：

- `<区域>`：`<城市1>`、`<城市2>`、`<城市3>`
- 按目标省份/城市自行补充。

---

## 8. 竞品/品牌词

华为、新华三、H3C、联想、中科曙光、华鲲振宇、宝德、超聚变、宁畅、戴尔、HPE、中兴、烽火等。

**用法**：用「品牌」检索范围查某品牌中标项目；用「中标企业」筛选查集成商，判断客户历史供应商与价格带。

---

## 9. 采购阶段词

招标公告、采购公告、询价公告、比选公告、竞争性磋商、谈判公告、单一来源、采购意向、招标预告、需求公示、征求意见、资格预审、中标公告、成交公告、废标公告、流标公告、更正公告。

> 销售优先级：**投标未截止的招标/询价 > 采购意向/需求公示 > 招标预告 > 中标结果（竞品情报）**。

---

## 10. 常驻监控清单

| 频率 | 检索 | 目的 |
|---|---|---|
| 每日 | 地区 + `服务器`，最近7天，投标未截止 | 抓当天在架服务器标 |
| 每日 | `算力` / `智算` / `GPU`，最近7天 | 抓 AI 算力急单 |
| 每日 | `存储` / `超融合` / `信创`，最近7天 | 抓存储与国产化 |
| 每周 | `数据中心` / `机房` / `云平台`，最近30天 | 抓项目型机会 |
| 每周 | 采购意向 + `人工智能` / `大模型` / `算力` | 抓 1–3 个月后的前置商机 |
| 每月 | 中标结果 + 竞品品牌词 | 更新价格基线与集成商地图 |


