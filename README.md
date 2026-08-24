# 📈 A股量化分析 AI 提示词与 Skill 体系库 (`stock-prompt`)

本项目是一套专为 **A 股市场** 打造的深度 AI 交易策略、板块分析与日内研判框架。结合大语言模型（如 DeepSeek, Gemini, ChatGPT, Claude）的联网能力与强推理能力，帮助交易者实现深度的市场数据分析与交易决策支持。

项目经过全面精简与规范化，消除了模型特定的冗余文件与复杂后缀，支持 **Antigravity**、**Workbuddy**、**Cursor**、**Dify/Coze**、**ChatGPT Custom GPTs** 及 **Web 网页版** 等各类 AI 工具与平台使用。

---

## 📂 项目结构（规范工程化版）

```text
stock-prompt/
├── .agents/skills/                    # 🤖 Antigravity / Agent 专用 Skill 目录
│   ├── daily-review/                  # 技能 1: A股每日强势板块与产业链共振分析
│   ├── index-prediction/              # 技能 2: A股四大指数盘前概率推演与路径预测
│   ├── market-prediction/             # 技能 3: A股盘前行情板块预测与日内策略研判
│   └── sector-rotation/               # 技能 4: A股近5日板块轮动与节奏深度复盘
├── prompts/                           # 📄 通用 Markdown 提示词库（与 skills 对齐）
│   ├── daily-review/                  # 每日强势板块共振分析
│   │   ├── 每天强势板块产业链共振分析.md
│   │   └── CHANGELOG.md
│   ├── index-prediction/              # 四大指数盘前路径预测
│   │   └── A股四大指数盘前概率推演与路径预测.md
│   ├── market-prediction/             # 每日行情板块预测
│   │   └── 每天行情板块预测.md
│   └── sector-rotation/               # 近5日板块轮动节奏分析
│       └── 5日内板块轮动节奏分析.md
├── scripts/                           # 🛠 自动化脚本（update.bat / update.sh）
├── CHANGELOG.md                       # 项目版本日志
├── README.md                          # 项目说明文档
└── version.json                       # 版本号控制配置
```

---

## 🌐 跨平台多场景使用指南

### 方式一：在 Antigravity / Agent 客户端中使用（⭐️⭐️⭐️⭐️⭐️ 推荐，零配置）
如果你使用 **Antigravity** 或支持标准 Agent Skill 的 IDE：
1. **直接 Clone / 打开本仓库** 作为工作区。
2. **自然语言提问**，Agent 会自动感知并激活对应技能：
   - 🗣 *"帮我深度复盘今天的强势板块"* ➡️ 自动激活 `daily-review`
   - 🗣 *"预测一下今天四大指数的开盘和走势路径"* ➡️ 自动激活 `index-prediction`
   - 🗣 *"根据隔夜外盘和盘后消息，做一份今天的盘前预测"* ➡️ 自动激活 `market-prediction`
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
1. **盘前（7:00 - 9:15）**：打开 `prompts/market-prediction/每天行情板块预测.md` 或 `prompts/index-prediction/A股四大指数盘前概率推演与路径预测.md`
2. **盘后复盘**：打开 `prompts/daily-review/每天强势板块产业链共振分析.md`
3. **中期节奏分析**：打开 `prompts/sector-rotation/5日内板块轮动节奏分析.md`
4. 复制完整 Markdown 内容粘贴给大模型。如果模型没有联网功能，请手动附上当天行情数据。

---

## 🧠 核心分析逻辑与防幻觉机制

1. **严谨的数据降级与防幻觉**：所有提示词均设有严格的**数据缺失处理规则**，当关键数据获取受限时强制按照中性或定性规则推演，防止 AI 编造假数据。
2. **三维共振理论**：龙头决定方向、中军决定容量、补涨决定扩散、共振决定持续性。
3. **情绪与量价结构**：结合市场总量环境（增量做多、存量轮动、减量退潮）动态匹配仓位建议与开仓盈亏比评估。

---

## 🤝 贡献与反馈

欢迎提交 PR 或 Issue 共同完善 A 股 AI 策略提示词库！
