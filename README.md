# 📈 A股量化分析 AI 提示词与 Skill 体系库 (`stock-prompt`)

本项目是一套专为 **A 股市场** 打造的实盘级 AI 交易策略、板块分析与日内研判框架。结合大语言模型（如 DeepSeek, Gemini, ChatGPT, Claude）的联网能力与强推理能力，帮助交易者实现深度的市场数据分析与交易决策支持。

支持 **Antigravity**、**Workbuddy**、**Cursor**、**Windsurf**、**Dify/Coze**、**ChatGPT Custom GPTs** 及 **Web 网页版** 等各类 AI 工具与平台使用。

---

## 📂 项目结构

```text
stock-prompt/
├── .agents/skills/                    # 🤖 Antigravity / Agent 专用 Skill 目录
│   ├── daily-review/                  # 技能 1: A股每日强势板块与产业链共振分析
│   ├── sector-rotation/               # 技能 2: A股近5日板块轮动与节奏深度复盘
│   └── market-prediction/             # 技能 3: A股盘前行情板块预测与日内策略研判
├── 每天复盘强势板块分析/               # 📄 每日复盘通用核心主文档
│   └── 每天强势板块产业链共振分析.md
├── 5日内板块轮动分析/                  # 📄 板块轮动分析通用核心主文档
│   └── 5日内板块轮动节奏分析.md
├── 每天行情板块预测/                  # 📄 盘前预测通用核心主文档
│   └── 每天行情板块预测.md
├── scripts/                           # 🛠️ 一键更新与版本检查脚本
│   ├── update.sh                      # Linux / macOS 自动更新脚本
│   └── update.bat                     # Windows 自动更新脚本
├── .github/workflows/                 # ⚙️ GitHub Actions 自动构建与发布流水线
│   └── release-auto.yml
├── version.json                       # 📌 单一版本感知清单文件 (Source of Truth)
├── CHANGELOG.md                       # 📝 详细更新日志
└── README.md                          # 📘 使用与分发更新指南
```

---

## 🔄 跨平台版本检查与更新指南 (Update Protocol)

> **GitHub `main` 分支是唯一的源代码与 Skill 源（Source of Truth）。**
> 任何使用者与客户端均可通过检查 `version.json` 明确得知当前版本并进行快速升级。

### 1. IDE 与本地 Agent 客户端（Antigravity / Cursor / Windsurf）
* **终端一键更新**：
  在项目根目录下直接运行更新脚本：
  ```bash
  # Linux / macOS
  ./scripts/update.sh

  # Windows
  .\scripts\update.bat
  ```
  或者直接运行标准的 Git 命令：
  ```bash
  git pull origin main
  ```
  *说明：Agent 客户端会在秒级内自动感知更新后的技能，无需重启 IDE。*

### 2. Dify / FastGPT / Coze 等 Agent 工作流平台
* **免手动静默更新（推荐）**：
  如果平台支持动态读取 URL，建议在系统提示词节点中直接挂载 GitHub Raw 链接（例如：`https://raw.githubusercontent.com/Geekwls/stock-prompt/main/.agents/skills/daily-review/SKILL.md`）。平台每次调用均会自动拉取最新版本。

### 3. ChatGPT Custom GPTs / Claude Projects / Web 网页端
* **版本检查与更新**：
  检查 [version.json](file:///home/wls/workspace/stock-prompt/version.json) 中的 `"latest"` 版本号。当发现有新版本时，前往对应目录复制最新 `.md` 主文件内容并覆盖粘贴到 GPTs 或 Claude 的 System Prompt 中。

---

## 🌐 跨平台多场景使用指南

### 方式一：在 Antigravity / Agent 客户端中使用（⭐️⭐️⭐️⭐️⭐️ 推荐，零配置）
直接 Clone / 打开本仓库作为工作区。用自然语言提问，Agent 会自动感知并激活对应技能：
- 🗣 *"帮我深度复盘今天的强势板块"* ➡️ 自动激活 `daily-review`
- 🗣 *"帮我分析近 5 个交易日的板块轮动和主线节奏"* ➡️ 自动激活 `sector-rotation`
- 🗣 *"根据隔夜外盘和盘后消息，做一份今天的盘前预测"* ➡️ 自动激活 `market-prediction`

---

### 方式二：在 Workbuddy / Cursor / Windsurf 等 AI 开发工具中使用
- **项目级集成**：直接 Clone 本项目作为 Workspace，工具会自动识别并索引 `.agents/` 目录中的技能与规则。
- **自定义提示词库**：在 Prompt/Rule 管理面板中新增自定义提示词，将对应 `.md` 主文件全文粘贴保存。

---

### 方式三：在 Dify / Coze / FastGPT 等 Agent 工作流平台构建 Bots
1. **System Prompt**：新建 Bot/Workflow 节点，将 `SKILL.md` 或主 Prompt 文件的文本粘贴到 **系统提示词 (System Prompt)** 中。
2. **工具集成**：为 Bot 绑定**联网搜索插件**（如 Tavily, Serper 或财经资讯 API）。

---

## 🧠 核心分析逻辑与防幻觉机制

1. **严谨的数据降级与防幻觉**：所有提示词均设有严格的**数据缺失处理规则**，当关键数据获取受限时强制按照中性或定性规则推演，防止 AI 编造假数据。
2. **三维共振理论**：龙头决定方向、中军决定容量、补涨决定扩散、共振决定持续性。
3. **实盘筹码与博弈**：结合 9:25 竞价爆量比率、龙虎榜席位品质（鉴别假机构与散户大本营）、筹码换手率与极强防守铁律。

---

## 🤝 贡献与反馈

欢迎提交 PR 或 Issue 共同完善 A 股 AI 策略提示词库！
