# Tnotices · 本地标讯跟进平台（模板）

一个基于「智能体 + 标讯网站 + 本地 Gitea」的轻量标讯跟进方案：
每天自动巡检在跟项目，识别变更、中标、废标、质疑与更正，生成 Gitea 首页看板，中标公示满 30 天自动完结。

> 本仓库为**脱敏模板**：不含任何真实客户、联系人、项目金额、内网地址或账号凭据。示例数据均为占位符。

## 能做什么

- 每日按关键词矩阵抓取标讯，去重后入库
- 跟踪更正/补遗/延期/答疑/质疑
- 抓取中标/成交公告，回填中标单位、金额、公示日期
- 识别废标/流标/终止，转异常状态
- 中标公示满 30 天自动标记“已完结”，不再巡检
- Gitea 仓库首页 README 直接显示项目清单
- `index.html` 交互看板：搜索、地区/状态/优先级筛选
- `data/events.jsonl` 事件流水，可审计

## 架构

```
智能体（Cherry Studio / 其他）
   │ 浏览器检索 + 调用 CLI
   ▼
scripts/tnotices.py
   ├─ data/projects.json     唯一数据源
   ├─ data/events.jsonl      事件流水
   ├─ README.md              Gitea 首页看板
   ├─ index.html             交互看板
   └─ reports/YYYY-MM-DD.md  每日日报
   │ git push
   ▼
本地 Gitea 仓库（建议私有）
```

## 快速开始

```powershell
# 1. 解压模板到 D:\Tnotices（或任意目录）
# 2. 改 config/settings.example.json 为 config/settings.json，填入 Gitea 地址/owner/repo

cd D:\Tnotices
uv run python scripts\tnotices.py --help

# 3. 导入 CSV（可选）
uv run python scripts\tnotices.py import-csv --path "D:\path\to\notices.csv"

# 4. 生成看板
uv run python scripts\tnotices.py recompute
uv run python scripts\tnotices.py render

# 5. 本地预览
.\start_dashboard.bat
# 打开 http://127.0.0.1:8088/index.html

# 6. 建库并推送（先配置 GITEA_TOKEN 或 git credential）
uv run python scripts\tnotices.py init-repo
uv run python scripts\tnotices.py push --message "init"
```

## 目录

```
.
├─ scripts/
│  ├─ tnotices.py        # 导入/批次/更新/事件/完结/渲染/推送
│  └─ serve.py           # 本地静态看板服务
├─ config/
│  ├─ settings.example.json
│  └─ daily_prompt.md    # 每日智能体任务提示词
├─ docs/
│  ├─ 搭建与使用指南.md
│  ├─ 值班手册_一页纸.md
│  ├─ 关键词矩阵.md
│  ├─ 附录A-核心脚本.md
│  └─ 附录B-每日任务提示词.md
├─ data/                 # projects.json / events.jsonl（运行时生成）
├─ reports/              # 每日日报
├─ start_dashboard.bat
└─ .gitignore
```

## 数据模型（核心字段）

`id`、`project_name`、`project_no`、`buyer`、`agency`、`region`、`budget_wan`、`publish_date`、`sign_deadline`、`bid_deadline`、`status`、`priority`、`winner`、`win_amount_wan`、`award_date`、`source_url`、`jianyu_url`、`contacts`、`owner`、`timeline`、`closed_at`、`closed_reason`。

状态机：

```
新发现 → 观察中 → 评估中 → 投标准备 → 已投标 → 结果待出
                                             ├→ 已中标 →（30天）→ 已完结
                                             ├→ 未中标 →（30天）→ 已完结
                                             └→ 流标/废标 →（30天）→ 已完结
已终止 →（30天）→ 已完结
```

## 每日流程

1. `batch --limit 30` 选出当天要巡检的项目（优先已投标/结果待出/7天内截止）
2. 智能体逐条检索：项目编号优先，其次标题
3. 识别变更/中标/异常/质疑，写 event 并更新字段
4. 按关键词矩阵抓取新商机，去重后 `add`
5. `recompute → render → push`
6. 写 `reports/YYYY-MM-DD.md`

## 安全与合规

- 只使用公开信息与已授权账号，只读浏览
- 不识别、不绕过、不反复提交图形验证码
- 浏览器操作 ≤3 次/秒，不遍历全站
- Token 只放环境变量或本机凭据管理器，不写入仓库
- 联系人只记录公告公开信息，不写入隐私数据
- 建议 Gitea 仓库设为私有

## 免责声明

本项目为内部效率工具的脱敏模板，不构成对任何标讯网站的服务替代或数据授权。使用前请确认目标站点的服务条款与所在公司的合规要求。示例代码按“现状”提供，使用风险由使用者自行承担。

## 文档

- [搭建与使用指南](docs/搭建与使用指南.md)
- [值班手册（一页纸）](docs/值班手册_一页纸.md)
- [关键词矩阵](docs/关键词矩阵.md)
- [附录 A：核心脚本](docs/附录A-核心脚本.md)
- [附录 B：每日任务提示词](docs/附录B-每日任务提示词.md)
