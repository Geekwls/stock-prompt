# 📈 A股量化分析 AI 提示词与 Skill 体系库 (`stock-prompt`)

本项目是一套专为 **A 股市场** 打造的深度 AI 交易策略、板块分析与日内研判框架。结合大语言模型（如 DeepSeek, Gemini, ChatGPT, Claude）的联网能力与强推理能力，帮助交易者实现深度的市场数据分析与交易决策支持。

项目具备极强的**跨平台兼容性**，支持在 **Antigravity**、**Workbuddy**、**Cursor**、**Dify/Coze**、**ChatGPT Custom GPTs** 及 **Web 网页版** 等各类 AI 工具与平台中使用。

---

## 📂 项目结构（四大核心交易与研究场景）

```text
stock-prompt/
├── plugin.json                       # 🌟 核心入口：Agent Plugins 1.0 标准插件清单 (兼容 Cursor/Copilot/Gemini)
│
├── mcp/                              # 🔌 确定性金融事实层 (零配置、免Token本地 MCP 服务端)
│   └── marketgraph-mcp/              # 直连腾讯证券与东财打板网关 (120日K线/ATR/炸板率/盘口)
│
├── .agents/skills/                    # 🤖 Antigravity / Agent 专用 Skill 目录
│   ├── market-prediction/             # 🌅 技能 1：A股盘前研判
│   ├── daily-review/                  # 🌇 技能 2：A股每日复盘
│   ├── sector-rotation/               # 🔄 技能 3：A股板块轮动
│   └── stock-analysis/                # 🔍 技能 4：A股个股诊断
│
├── prompts/                           # 📄 从 Skill 母本同步生成的跨平台 Markdown 提示词库
│   ├── market-prediction/             # 🌅 A股盘前研判
│   │   └── A股盘前全景研判与概率推演.md
│   ├── daily-review/                  # 🌇 A股每日复盘
│   │   └── A股每日主线与产业链共振复盘.md
│   ├── sector-rotation/               # 🔄 A股板块轮动
│   │   └── A股近5日板块轮动与节奏复盘.md
│   └── stock-analysis/                # 🔍 A股个股诊断
│       └── A股个股完整诊断与威科夫结构研判.md
│
├── contracts/                         # 📐 四个 Skill 共用研究契约的项目级母本
│   └── common-research-contract.md
│
├── scripts/                           # 🛠 自动化工具库
│   ├── generate_report_card.py        # 🎨 高清极简金融研报长图自动生成脚本 (支持 prediction/daily/rotation/stock)
│   ├── install_skills.py              # 🚀 一键安装/校验所有技能到 Gemini / Antigravity / Codex
│   ├── sync_skill_contracts.py         # 🔁 公共研究契约同步及漂移检查
│   ├── sync_prompts.py                # 🔁 Skill → Prompt 同步及漂移检查
│   ├── update.bat                     # 🔄 Windows 自动更新脚本
│   └── update.sh                      # 🔄 Linux/Mac 自动更新脚本
├── CHANGELOG.md                       # 项目主版本日志
├── README.md                          # 项目说明文档
└── version.json                       # 版本号控制配置
```

---

## 🎨 📊 自动生成超高清研报长图 (战报卡片引擎)

项目内置了全自动 Python 研报长图生成器 (`scripts/generate_report_card.py`)，支持将四大核心场景的全量量化数据一键渲染为极简金融研报风长图（支持浅色/深色主题）：

```bash
# 1. 个股完整诊断与威科夫结构研报长图 (输入任意个股使用)
python3 scripts/generate_report_card.py --demo --type stock

# 2. 每日收盘强势板块与产业链复盘长图 (15:00 收盘后使用)
python3 scripts/generate_report_card.py --demo --type daily

# 3. 5 日板块轮动与主线节奏复盘长图 (周五/周末/月末使用)
python3 scripts/generate_report_card.py --demo --type rotation

# 4. 盘前全景量化推演战报长图 (08:30-09:15 使用)
python3 scripts/generate_report_card.py --demo --type prediction

# 5. 深色科技风卡片 (末尾加上 --theme dark)
python3 scripts/generate_report_card.py --demo --type stock --theme dark
```

---

## 🌐 跨平台多场景使用指南

### 方式一：在 Antigravity / Agent 客户端中使用（⭐️⭐️⭐️⭐️⭐️ 推荐，零配置）
如果你使用 **Antigravity** 或支持标准 Agent Skill 的 IDE：
1. **直接 Clone / 打开本仓库** 作为工作区。
2. **自然语言提问**，Agent 会自动感知并激活对应技能：
   - 🗣 *"做一份今天的盘前全景预测（大盘点位+板块机会）"* ➡️ 自动激活 `market-prediction`
   - 🗣 *"帮我深度复盘今天的强势板块与产业链共振"* ➡️ 自动激活 `daily-review`
   - 🗣 *"帮我分析近 5 个交易日的板块轮动和主线节奏"* ➡️ 自动激活 `sector-rotation`
   - 🗣 *"完整诊断一下这只股票当前的逻辑、结构和风险"* ➡️ 自动激活 `stock-analysis`

---

### 方式二：在 Workbuddy / Cursor / Windsurf 等 AI 开发工具中使用
如果你或你的朋友使用 **Workbuddy**、**Cursor** 或 **Windsurf**：
- **项目级集成**：直接 Clone 本项目作为 Workspace，Workbuddy / Cursor 会自动识别并索引 `.agents/` 目录中的技能与规则。
- **自定义提示词库**：在 Workbuddy 的 Prompt/Rule 管理面板中，新增自定义提示词，将 `prompts/` 对应目录下的 `.md` 主文件全文粘贴保存，即可随用随点。Prompt 由对应 `SKILL.md` 自动生成，请勿单独维护两份规则。

---

### 方式三：在 Dify / Coze / FastGPT 等 Agent 工作流平台构建 Bots
如果你想把这些提示词搭建成飞书/钉钉/微信群里的**自动化复盘机器人**：
1. **System Prompt**：新建 Bot/Workflow 节点，将 `prompts/` 目录或 `SKILL.md` 中主 Prompt 文件的文本粘贴到 **系统提示词 (System Prompt)** 中。
2. **工具集成**：为 Bot 绑定**联网搜索插件**（如 Tavily, Serper 或财经资讯 API），让 Bot 具备获取当日实时行情数据的能力。

---

### 方式四：在 ChatGPT Custom GPTs / Claude Projects 中使用
- **ChatGPT Custom GPTs**：在 ChatGPT 中“Create a GPT”，将 Prompt 粘贴至 **Instructions**，并确保勾选 **Web Browsing (联网功能)**。
- **Claude Projects**：在 Claude 中新建 Project，将 Prompt 写入 **Project Instructions**。

---

### 方式五：在网页版 LLM (ChatGPT / DeepSeek / Kimi / Gemini) 中使用
如果在 Web 页面直接对话：
1. **盘前（8:30 - 9:15）**：打开 `prompts/market-prediction/A股盘前全景研判与概率推演.md`
2. **盘后复盘**：打开 `prompts/daily-review/A股每日主线与产业链共振复盘.md`
3. **中期节奏分析**：打开 `prompts/sector-rotation/A股近5日板块轮动与节奏复盘.md`
4. **个股完整诊断**：打开 `prompts/stock-analysis/A股个股完整诊断与威科夫结构研判.md`
5. 复制完整 Markdown 内容粘贴给大模型。如果模型没有联网功能，请手动附上当天行情数据。

---

## 🧠 核心分析逻辑与防幻觉机制

1. **严谨的数据覆盖率与防幻觉**：所有提示词均设有 `Data Coverage` 和缺失值规则；关键覆盖率不足时只输出条件情景，不用中性值、0分或示例行情伪造精确结论。
2. **贝叶斯先验与机会函数双解耦**：大盘四维立体空间点位（ATR波动率 + 筹码POC + 期权对冲墙）界定安全边际，机会评分 (Opportunity Score) 解耦方向与盈亏比。
3. **多维闭环自检**：引入 Brier Score、校准度 (Calibration) 与锐度 (Sharpness) 持续追踪模型效能。
4. **个股行情硬门槛**：缺少120日复权OHLCV或同期宽基/行业基准时，L4–L7统一为 `N/A`，不输出威科夫定级、赔率或综合评分。

---

## 🚀 首次安装与一键更新

四份跨平台 Prompt 以 `.agents/skills/*/SKILL.md` 为唯一母本。修改 Skill 后运行：

```bash
python3 scripts/sync_skill_contracts.py
python3 scripts/sync_prompts.py
python3 scripts/sync_skill_contracts.py --check
python3 scripts/sync_prompts.py --check
```

本仓库内置完整的**独立分发与更新机制**，使用者无需手动拷贝技能文件。

**首次安装**（默认同步到 Gemini、Antigravity 与 Codex；manifest 只清理本项目曾管理的旧文件）：

```bash
python3 scripts/install_skills.py

# 只安装到指定平台
python3 scripts/install_skills.py --target codex

# 先查看将新增、更新或删除哪些项目管理文件
python3 scripts/install_skills.py --dry-run
```

**日常更新**（上游发布新版本后，一条命令完成 拉取代码 ➡️ 同步全局副本 ➡️ 防漂移校验）：

```bash
# Linux / macOS
bash scripts/update.sh

# Windows（双击运行亦可）
scripts\update.bat
```

更新脚本会先检查本地修改；存在未提交内容时停止，避免覆盖用户定制。随后以 fast-forward 方式拉取 GitHub main，并运行 `install_skills.py` 将四大技能同步到 Gemini、Antigravity 与 Codex。安装器通过 manifest 清理旧版本残留，只处理本项目记录的文件；`--check` 会校验完整 Skill 文件，而不只是报告卡脚本。当前版本见 `version.json`，每次更新的内容见 `CHANGELOG.md`。

---

## 🗺️ 未来演进路线 (Roadmap)

项目正持续从“4 个独立的分析技能”演进为“全天候跨 Skill 交易闭环协同流水线”：
- 详细设计方案与实施阶段规划见：[📖 跨 Skill 交易闭环协同流水线计划 (docs/ROADMAP_CROSS_SKILL_PIPELINE.md)](docs/ROADMAP_CROSS_SKILL_PIPELINE.md)

---

## 🤝 贡献与反馈

欢迎提交 PR 或 Issue 共同完善 A 股 AI 策略提示词库！
