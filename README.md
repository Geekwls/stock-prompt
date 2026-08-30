# 📈 A股量化分析 AI 提示词与 Skill 体系库 (`stock-prompt`)

本项目是一套专为 **A 股市场** 打造的深度 AI 交易策略、板块分析与日内研判框架。结合大语言模型（如 DeepSeek, Gemini, ChatGPT, Claude）的联网能力与强推理能力，帮助交易者实现深度的市场数据分析与交易决策支持。

项目具备极强的**跨平台兼容性**，支持在 **Antigravity**、**Workbuddy**、**Cursor**、**Dify/Coze**、**ChatGPT Custom GPTs** 及 **Web 网页版** 等各类 AI 工具与平台中使用。

---

## 📂 项目结构（三大核心交易场景）

```text
stock-prompt/
├── .agents/skills/                    # 🤖 Antigravity / Agent 专用 Skill 目录
│   ├── market-prediction/             # 🌅 技能 1 (盘前)：大盘点位 + 行业主线 + 竞价全景研判 (V3.0)
│   ├── daily-review/                  # 🌇 技能 2 (盘后)：每日强势板块产业链共振深度复盘
│   └── sector-rotation/               # 🔄 技能 3 (中期)：近5日板块轮动与节奏深度推演
│
├── prompts/                           # 📄 通用 Markdown 提示词库（与 skills 完全对齐）
│   ├── market-prediction/             # 🌅 盘前全景研判
│   │   └── A股盘前全景策略研判.md
│   ├── daily-review/                  # 🌇 盘后共振复盘
│   │   └── 每天强势板块产业链共振分析.md
│   └── sector-rotation/               # 🔄 近5日轮动节奏
│       └── 5日内板块轮动节奏分析.md
│
├── scripts/                           # 🛠 自动化工具库
│   ├── generate_report_card.py        # 🎨 高清深色科技风战报长图自动生成脚本
│   ├── update.bat                     # 🔄 Windows 自动更新脚本
│   └── update.sh                      # 🔄 Linux/Mac 自动更新脚本
├── CHANGELOG.md                       # 项目主版本日志
├── README.md                          # 项目说明文档
└── version.json                       # 版本号控制配置
```

---

## 🎨 自动化战报长图生成器 (Report Card Generator)

本项目内置了高分辨率深色科技风战报长图渲染脚本 `scripts/generate_report_card.py`，支持将研判与复盘数据一键渲染为精美卡片（适配微信、小红书、朋友圈）：

```bash
# 生成示例战报长图
python scripts/generate_report_card.py --demo

# 根据自定义 JSON 数据生成长图
python scripts/generate_report_card.py --json my_report.json --output today_report.png
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

---

### 方式二：在 Workbuddy / Cursor / Windsurf 等 AI 开发工具中使用
如果你或你的朋友使用 **Workbuddy**、**Cursor** 或 **Windsurf**：
- **项目级集成**：直接 Clone 本项目作为 Workspace，Workbuddy / Cursor 会自动识别并索引 `.agents/` 目录中的技能与规则。
- **自定义提示词库**：在 Workbuddy 的 Prompt/Rule 管理面板中，新增自定义提示词，将 `prompts/` 对应目录下的 `.md` 主文件全文粘贴保存，即可随用随点。

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
1. **盘前（8:30 - 9:15）**：打开 `prompts/market-prediction/A股盘前全景策略研判.md`
2. **盘后复盘**：打开 `prompts/daily-review/每天强势板块产业链共振分析.md`
3. **中期节奏分析**：打开 `prompts/sector-rotation/5日内板块轮动节奏分析.md`
4. 复制完整 Markdown 内容粘贴给大模型。如果模型没有联网功能，请手动附上当天行情数据。

---

## 🧠 核心分析逻辑与防幻觉机制

1. **严谨的数据降级与防幻觉**：所有提示词均设有严格的**数据缺失处理规则**，当关键数据获取受限时强制按照中性或定性规则推演，防止 AI 编造假数据。
2. **贝叶斯先验与机会函数双解耦**：大盘四维立体空间点位（ATR波动率 + 筹码POC + 期权对冲墙）界定安全边际，机会评分 (Opportunity Score) 解耦方向与盈亏比。
3. **多维闭环自检**：引入 Brier Score、校准度 (Calibration) 与锐度 (Sharpness) 持续追踪模型效能。

---

## 🤝 贡献与反馈

欢迎提交 PR 或 Issue 共同完善 A 股 AI 策略提示词库！
