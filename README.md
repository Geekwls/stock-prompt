# 📈 A股量化分析 AI 提示词与 Skill 体系库 (`stock-prompt`)

<p align="center">
  <img src="https://img.shields.io/badge/Release-v7.0.0-blue.svg" alt="Release v7.0.0" />
  <img src="https://img.shields.io/badge/Tests-97%20Passing-brightgreen.svg" alt="Tests Passing" />
  <img src="https://img.shields.io/badge/Architecture-5%20Skills%20%2B%2012%20MCP%20Tools-orange.svg" alt="Architecture" />
  <img src="https://img.shields.io/badge/Zero--Config-Built--in%20MarketGraph%20MCP-success.svg" alt="Zero-Config MCP" />
  <img src="https://img.shields.io/badge/Platform-Antigravity%20%7C%20Cursor%20%7C%20Claude%20%7C%20Gemini%20%7C%20Codex-purple.svg" alt="Platform" />
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License MIT" />
</p>

本项目是一套专为 **A 股市场** 打造的深度 AI 交易策略、板块分析与日内研判框架。结合大语言模型（如 DeepSeek, Gemini, ChatGPT, Claude）的强推理能力与内置的 **MarketGraph MCP 确定性金融数据服务**，帮助交易者实现“零幻觉、有证据、全闭环”的市场数据分析与交易决策支持。

项目具备极强的**跨平台兼容性**，原生支持在 **Antigravity**、**Cursor**、**Windsurf**、**Workbuddy**、**Dify/Coze**、**ChatGPT Custom GPTs**、**Claude Projects** 及各类 Web 网页版 AI 中即插即用。

---

## ⚡ v7.0.0 核心亮点

1. **🔌 内置 12 大确定性金融 MCP 网关 (`marketgraph-mcp`)**
   - 零注册、免 Token、零外部第三方库依赖（纯原生 Python 3.8+ 标准库实现）。
   - 直连腾讯证券与东方财富开放网络节点，涵盖 750 日宏观 K 线（MA500 两年牛熊线）、周线共振、当日分时全景/均线偏离度、交易所龙虎榜前 5 大席位穿透、行业主力资金流及等权篮子对冲容灾，**彻底消灭 AI 编造行情的幻觉隐患**。
2. **🔤 纯中文股票名秒级智能联想解析**
   - 无论输入数字代码（`301489`）、带前后缀代码（`sz301489`, `600519.SH`）还是**纯中文股票名称**（如“贵州茅台”、“中际旭创”），底层毫秒级自动解析标准化，彻底告别繁琐代码查找。
3. **💬 散户友好：首屏「30 秒大白话速览」与术语强制通俗注释**
   - **结论前置**：研报第一屏直截了当回答 3 句话——*“现在发生了什么 / 为什么这么看 / 什么情况说明判断错了（认赔止损点）”*，大白话决策一目了然。
   - **通俗比喻**：首次出现的威科夫技术黑话强制附带生活化比喻（如 Bias 偏离 ➡️ 像皮筋拉伸；ATR 波动率 ➡️ 股票单日心跳振幅；Spring 弹簧 ➡️ 假摔诱空坑），在八层量化证据纪律不减分毫的前提下，让小白也能轻松读懂。
4. **🧭 全流程 5 大 Skill 协同编排与程序化交接 (`stock-research-router`)**
   - 新增总控路由 Skill，自动协调 **盘前推演 ➡️ 盘中竞价 ➡️ 收盘复盘 ➡️ 5日轮动 ➡️ 穿透个股诊断** 的跨时段闭环。
   - 跨技能交接升级为程序化强校验的 `handoff_store.py` 与 Schema 资产，市场与板块结论无缝向下游继承，避免重复分析。
5. **📊 盘前 ↔ 盘后自校准评估台账 (Brier Loop)**
   - 盘前推演概率与收盘实际表现自动落盘至 `~/.stock-prompt/eval/predictions.jsonl`，滚动统计方向命中率、Brier Score、主线 Top3 命中率与空间有效率；情绪五项分自动落盘并支持历史滚动 P 分位自校准。
6. **🛡️ 军工级防漂移测试套件**
   - 内置 **97 项自动化单元测试**，严密覆盖行情门槛、数据降级审计、Schema 合规性、版本防漂移与断路器容灾机制。

---

## 📂 项目结构（四个专业 Skill + 一个编排 Router）

```text
stock-prompt/
├── registry.json                     # 🌟 单一配置源：驱动 Skill、脚本、Schema 与 MCP 工具清单
├── plugin.json                       # 🔌 核心入口：Agent Plugins 1.0 标准插件清单 (兼容 Cursor/Copilot/Gemini)
├── data/                             # 📅 A 股交易日历（支持离线交易日窗口推算）
│   └── a_share_trading_calendar.json
│
├── mcp/                              # 🔌 A 股确定性数据 MCP 服务端（本地 stdio、免 Token、零外部依赖）
│   └── marketgraph-mcp/              # 腾讯/东财公开网关（server.py 入口 + marketgraph_mcp/ 核心模块）
│
├── .agents/skills/                    # 🤖 Agent 专用 5 大 Skill 目录
│   ├── market-prediction/             # 🌅 技能 1：A股盘前研判 (08:30-09:15 / 09:25 竞价)
│   ├── daily-review/                  # 🌇 技能 2：A股每日复盘 (15:00 收盘后)
│   ├── sector-rotation/               # 🔄 技能 3：A股板块轮动 (近 5 日 / 周末)
│   ├── stock-analysis/                # 🔍 技能 4：A股个股诊断 (八层证据 + 威科夫结构)
│   └── stock-research-router/         # 🧭 技能 5：跨阶段编排与交接总控路由
│       （每个技能含 SKILL.md + references/ 契约 + agents/ 元数据 + scripts/ 捆绑脚本）
│
├── prompts/                           # 📄 从 Skill 母本同步生成的跨平台 Markdown 提示词库
│   ├── market-prediction/             # 🌅 A股盘前研判 Prompt
│   ├── daily-review/                  # 🌇 A股每日复盘 Prompt
│   ├── sector-rotation/               # 🔄 A股板块轮动 Prompt
│   ├── stock-analysis/                # 🔍 A股个股诊断 Prompt
│   └── stock-research-router/         # 🧭 跨阶段编排与路由 Prompt
│
├── contracts/                         # 📐 五个 Skill 共用研究契约的项目级母本
│   └── common-research-contract.md
│
├── docs/                              # 📖 设计文档与架构路线图
│   └── ROADMAP_CROSS_SKILL_PIPELINE.md
│
├── scripts/                           # 🛠 自动化工具与维护套件
│   ├── generate_report_card.py        # 🎨 高清极简金融研报长图自动生成脚本 (支持 4 类研报)
│   ├── report_card/                   # 🎨 长图渲染分模块包 (common/validation/4类研报排版)
│   ├── eval_tracker.py                # 📊 盘前↔盘后评估台账 (Brier/校准/Top3命中率闭环)
│   ├── handoff_store.py               # 🔗 Handoff 校验、原子写入、读取与清理工具
│   ├── project_registry.py            # 🧩 架构注册表加载与路径校验
│   ├── check_version_parity.py        # 🧪 项目/插件/MCP/发布标签版本一致性检查
│   ├── install_skills.py              # 🚀 一键安装/校验所有技能到 Gemini / Antigravity / Codex
│   ├── sync_skill_contracts.py        # 🔁 公共研究契约同步及漂移检查
│   ├── sync_prompts.py                # 🔁 Skill → Prompt 同步及漂移检查
│   ├── update.bat                     # 🔄 Windows 自动更新脚本
│   └── update.sh                      # 🔄 Linux/Mac 自动更新脚本
│
├── tests/                             # ✅ 97 项自动化单元测试 (全链路防幻觉与契约防漂移)
├── schemas/                           # 🧾 Handoff、台账、报告卡与 MCP 信封 JSON Schemas
│
├── .github/workflows/                 # ⚙️ CI 自动化测试流水线 (push/PR)
├── AGENTS.md                          # 🧭 Agent 时段感知路由与跨 Skill 闭环协议
├── CHANGELOG.md                       # 📝 项目全量更新日志
├── README.md                          # 📖 项目说明文档
└── version.json                       # 📌 版本号控制配置
```

---

## 🔌 MarketGraph MCP 12 大确定性金融网关全览

服务端基于标准 JSON-RPC 2.0 stdio 协议运行，内置 3 分钟盘中轻量缓存与历史数据 24 小时长缓存，内置请求频控与断路器熔断机制：

| 工具名称 | 核心能力与输出指标 | 典型适配场景 |
| :--- | :--- | :--- |
| `get_stock_quote` | 实时价格、PE(TTM)、PB、总/流通市值、换手率、五档盘口、纯中文名自动联想 | 任意时段实时估值与微观盘口 |
| `get_stock_kline` | 默认 750 日（3 年）前复权日 K 线，MA20/50/120/250/500、ATR14、Bias、周线共振（MA10/30、52周区间）、三层威科夫时空模型、量比分位；附 30 日精简 K 线（省 85% Token） | `stock-analysis` 行情硬门槛与中长期结构研判 |
| `get_stock_timeline` | 当日 240 分钟分时全景、分时均价线 (VWAP)、盘中放量脉冲时刻 Top 3、9:25 集合竞价成交与开盘涨跌幅 | `market-prediction` 竞价承接力 / 盘中异动分析 |
| `get_index_kline` | 核心指数（上证/深证/创业板/全指/沪深300）最近 N 日收盘、ATR14（盘前 Z_ATR 判档）、MA5/20/60 与 20 日高低点 | `market-prediction` 点位计算与相对强度基准 |
| `get_market_breadth` | 全市场上涨/平盘/下跌家数与红盘率（东财快照），历史日期以打板池与指数替代并明确标注精度 | `daily-review` 市场整体赚钱效应审计 |
| `get_market_sentiment`| 两市总成交额、涨跌停池数量、炸板池数量、全市场精确真实炸板率、最高连板高度；支持历史日期回补 | 情绪周期量能与短线极值判定 |
| `get_limit_up_ladder` | 今日或历史指定交易日连板天梯分布、各高度板代表龙头标的与所属行业 | 市场最高连板高度与短线情绪梯队拆解 |
| `get_sector_fund_flow`| 申万/概念板块主力资金净流入 Top 榜、净流出 Top 榜、涨幅榜与领涨龙头；支持 2-10 日历史流向回补 | `daily-review` / `sector-rotation` 主线资金追踪 |
| `get_sector_kline` | 行业指数日 K 序列（MA5/10/20/60、区间涨幅、高低点、成交额与量比）；支持 BK 代码或中文板块名 | 板块中期强度、均线支撑与资金延续判定 |
| `get_basket_index` | 以腾讯前复权日 K 构造**等权篮子代理指数**（日度再平衡口径），披露成分覆盖度与失败清单 | 行业指数接口抖动时的合规代理序列对冲 |
| `get_longhubang_detail`| 全市场日度龙虎榜总览或个股前 5 大买卖席位穿透（自动识别机构专用、外资北向与游资营业部） | 资金合力属性、机构净买入与游资溢价研判 |
| `get_company_quality` | 核心财务指标（营收/净利同比、ROE、毛利率、负债率）、商誉占比、未来限售解禁日筛查 | `stock-analysis` L8 公司基本面排雷与解禁雷达 |

---

## 🎨 自动生成超高清研报长图 (战报卡片引擎)

项目内置了全自动 Python 研报长图生成器 (`scripts/generate_report_card.py`)，支持将四大核心场景的全量量化数据一键渲染为极简金融研报风长图（支持浅色/深色主题）：

```bash
# 1. 个股完整诊断与威科夫结构研报长图 (输入任意个股使用)
python scripts/generate_report_card.py --demo --type stock

# 2. 每日收盘强势板块与产业链复盘长图 (15:00 收盘后使用)
python scripts/generate_report_card.py --demo --type daily

# 3. 5 日板块轮动与主线节奏复盘长图 (周五/周末/月末使用)
python scripts/generate_report_card.py --demo --type rotation

# 4. 盘前全景量化推演战报长图 (08:30-09:15 使用)
python scripts/generate_report_card.py --demo --type prediction

# 5. 深色科技风卡片 (末尾加上 --theme dark)
python scripts/generate_report_card.py --demo --type stock --theme dark
```

> Linux/macOS 环境请将 `python` 替换为 `python3`。正式报告通过 `--json` 传入完整数据（各技能内置已通过校验的最小示例 `references/report-card-example.json`，可直接复制修改）；未指定 `--output` 时输出文件名自动带日期，不会覆盖历史战报。

---

## 🌐 跨平台多场景使用指南

> **先看能力分层**：本项目的数据可靠性取决于宿主能否运行本地 MCP 服务。
> - **完整模式**（推荐）：Antigravity、Gemini CLI、Claude Code、Cursor 等**本地 Agent 宿主**——注册 `marketgraph-data` MCP 后获得 12 大确定性数据网关（750日K线、指数ATR、板块资金流历史等），断网搜索仅在 MCP 覆盖外字段（隔夜外盘、宏观汇率等）作补充。
> - **降级模式**：Dify/Coze 工作流平台、ChatGPT GPTs、网页版 LLM——**无法运行本地 stdio MCP**，只能绑定联网搜索插件获取行情（公共契约 P4 线索），数据缺失时按各 Skill 降级规则输出 N/A，不伪造。
> 两种模式下 Skill 的分析纪律完全相同，差别只在数据来源的确定性。

### 方式一：在 Antigravity / Agent 客户端中使用（⭐️⭐️⭐️⭐️⭐️ 最推荐，零配置）
如果你使用 **Antigravity** 或支持标准 Agent Skill 的 IDE：
1. **直接 Clone / 打开本仓库** 作为工作区。
2. **日常口语化自然提问**，Agent 会自动识别时段与意图并唤醒对应专业技能：
   - 🌅 **盘前（08:30 - 09:15）**：
     - 🗣 *“做一份今天的盘前全景预测”*
     - 🗣 *“明天大盘怎么走？早盘看多还是看空？”*
     - 🗣 *“9:25 集合竞价怎么看？今天开盘强不强？”*
   - 🌇 **收盘后（15:00 - 21:00）**：
     - 🗣 *“帮我深度复盘今天的强势板块与产业链共振”*
     - 🗣 *“今天大盘怎么看？为什么突然大跌/大涨？”*
     - 🗣 *“今天主力资金净流入哪个行业？龙虎榜机构买了什么？”*
   - 🔄 **周五 / 周末 / 月末**：
     - 🗣 *“帮我分析近 5 个交易日的板块轮动和主线节奏”*
     - 🗣 *“最近哪几个板块在轮动？高位题材还能追吗？”*
   - 🔍 **任意时段（个股诊断）**：
     - 🗣 *“诊断 300308”* / *“中际旭创现在能买吗？”*
     - 🗣 *“301489 被套了怎么办，成本 xxx 怎么解套？”*
     - 🗣 *“帮我看下贵州茅台，财务有没有暴雷风险？”*
     - *(若会话中已有当日盘前/复盘报告，市场与板块结论将作为 L1/L2 证据自动继承)*
   - 🧭 **跨阶段连续研究**：
     - 🗣 *“按完整流程帮我研究一下这个票”* ➡️ 自动激活 `stock-research-router`

Agent 客户端会自动读取根目录 [AGENTS.md](AGENTS.md)，按交易时段路由到对应技能并执行跨 Skill 闭环协议。

---

### 方式二：在 Cursor / Windsurf / Workbuddy / Claude Code / Gemini CLI 等 AI 开发工具中使用
如果你使用 **Cursor**、**Windsurf**、**Workbuddy**、**Claude Code** 或 **Gemini CLI**：
- **项目级集成**：直接 Clone 本项目作为 Workspace，编辑器会自动索引 `.agents/` 目录中的技能、规则与 `plugin.json`（Agent Plugins 1.0 标准，含 `mcpServers` 声明，Cursor / VS Code Copilot / Gemini CLI / Claude Code 可直接识别）。
- **注册 MCP 网关（解锁完整模式的关键一步）**：将 `mcp/marketgraph-mcp/server.py` 注册为本地 stdio MCP 服务（Cursor 的 `mcp.json`、Claude Code 的 `claude mcp add`、Gemini CLI 的 `settings.json` 均可），配置片段与自测命令见 [mcp/marketgraph-mcp/README.md](mcp/marketgraph-mcp/README.md)。未注册时 Skill 仍可运行，但行情数据退回联网搜索降级模式。
- **自定义提示词库**：在 Prompt 管理面板中新增自定义提示词，将 `prompts/` 对应目录下的 `.md` 主文件全文粘贴保存即可。Prompt 由对应 `SKILL.md` 自动生成，请勿单独维护两份规则。

---

### 方式三：在 Dify / Coze / FastGPT 等 Agent 工作流平台构建 Bots
如果你想把这些提示词搭建成飞书/钉钉/微信群里的**自动化复盘机器人**：
1. **System Prompt**：新建 Bot/Workflow 节点，将 `prompts/` 目录或 `SKILL.md` 中主 Prompt 文件的文本粘贴到 **系统提示词 (System Prompt)** 中。
2. **工具集成**：为 Bot 绑定**联网搜索插件**（如 Tavily, Serper 或财经资讯 API），让 Bot 具备获取当日实时行情数据的能力。

> ⚠️ **能力边界**：这类平台无法运行本地 stdio MCP 服务，因此只能工作在**降级模式**——行情数据依赖联网搜索（P4 线索），无法获得 12 大确定性网关。Skill 的防幻觉规则会保证数据不足时明确输出 N/A 而非编造，但评分覆盖率和结论置信度会显著低于本地宿主。若 Bot 只需"大盘情绪 + 板块轮动"级别的粗粒度结论，降级模式可用；个股八层诊断建议在本地宿主中运行。

---

### 方式四：在 ChatGPT Custom GPTs / Claude Projects 中使用
- **ChatGPT Custom GPTs**：在 ChatGPT 中“Create a GPT”，将 Prompt 粘贴至 **Instructions**，并确保勾选 **Web Browsing (联网功能)**。
- **Claude Projects**：在 Claude 中新建 Project，将 Prompt 写入 **Project Instructions**。

> ⚠️ **能力边界**：同方式三，网页端无法运行本地 MCP，属**降级模式**（仅联网搜索）。注意区分：**Claude Projects（网页版）≠ Claude Code（CLI）**——Claude Code 可注册本地 `marketgraph-data` MCP 获得完整模式，见方式二。

---

### 方式五：在网页版 LLM (ChatGPT / DeepSeek / Kimi / Gemini) 中使用
如果在 Web 页面直接对话：
1. **盘前（8:30 - 9:15）**：打开 `prompts/market-prediction/A股盘前全景研判与概率推演.md`
2. **盘后复盘**：打开 `prompts/daily-review/A股每日主线与产业链共振复盘.md`
3. **中期节奏分析**：打开 `prompts/sector-rotation/A股近5日板块轮动与节奏复盘.md`
4. **个股完整诊断**：打开 `prompts/stock-analysis/A股个股完整诊断与威科夫结构研判.md`
5. **全流程总控**：打开 `prompts/stock-research-router/A股全流程研究总控路由.md`
6. 复制完整 Markdown 内容粘贴给大模型。如果模型没有联网功能，请手动附上当天行情数据。
7. **此方式属降级模式**（无 MCP 确定性数据）；数据缺失时报告会按防幻觉规则输出 `N/A` 与待补清单，属预期行为而非故障。

---

## 🧠 核心分析逻辑与防幻觉机制

1. **严谨的数据覆盖率与防幻觉**：所有提示词均设有 `Data Coverage` 和缺失值规则；关键覆盖率不足时只输出条件情景，不用中性值、0分或示例行情伪造精确结论。
2. **贝叶斯先验与机会函数双解耦**：大盘四维立体空间点位（ATR波动率 + 筹码POC + 期权对冲墙）界定安全边际，机会评分 (Opportunity Score) 解耦方向与盈亏比。
3. **多维闭环自检**：盘前预测与收盘实际统一落盘评估台账，滚动追踪 Brier Score、校准度 (Calibration)、锐度 (Sharpness) 与主线/点位命中率（用法见下方「盘前 ↔ 盘后评估闭环」一节）。
4. **跨 Skill 交接与穿透**：每份报告末尾输出标准化交接摘要 JSON，市场与板块结论可被后续技能直接继承；复盘标的支持 `诊断 <代码>` 一键穿透至个股八层诊断。
5. **个股行情硬门槛**：缺少120日复权OHLCV或同期宽基/行业基准时，L4–L7统一为 `N/A`，不输出威科夫定级、赔率或综合评分。

---

## 🔁 盘前 ↔ 盘后评估闭环 (Evaluation Loop)

盘前预测与收盘实际统一落盘到评估台账，滚动输出 Brier Score、校准度与命中率，让模型推演可验证、可证伪：

```bash
# 盘前 8:30-9:15：落盘当日预测（三态概率 / 机会分 / 主线 Top3 / R1 / S1）
python scripts/eval_tracker.py record --date 2026-09-07 --regime S3 \
    --p-up 55 --p-side 30 --p-down 15 --opportunity 78 \
    --top-sector 半导体 --top-sectors 半导体,PCB,低空经济 --r1 3850 --s1 3800

# 收盘 15:00 后：落盘当日实际（daily-review 复盘完成后执行）
python scripts/eval_tracker.py result --date 2026-09-07 --z-atr 0.62 \
    --top-sectors 半导体,农业,化工 --close 3842 --high 3855 --low 3805

# 任意时点：输出 20 日滚动评估（Brier / 方向命中 / 校准 / 主线 Top1与Top3 / 点位有效率）
python scripts/eval_tracker.py report
```

> Linux/macOS 环境请将 `python` 替换为 `python3`。台账固定写入 `~/.stock-prompt/eval/predictions.jsonl`（不随工作目录漂移；旧 `./eval/` 台账首次运行自动迁移，`--ledger` 参数与 `STOCK_PROMPT_LEDGER` 环境变量可覆盖）。收盘复盘后另可执行 `record-daily` 将情绪五项分落盘至同目录 `daily_scores.jsonl`，`report-daily` 输出固定阈值的历史分位落位（阈值自校准依据）。`market-prediction` 与 `daily-review` 的 SKILL.md 已内置对应步骤。

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

更新脚本会先检查本地修改；存在未提交内容时停止，避免覆盖用户定制。随后先比对远程再以 fast-forward 方式拉取 GitHub main，并运行 `install_skills.py` 将五大技能同步到 Gemini、Antigravity 与 Codex。安装器通过 manifest 清理旧版本残留，只处理本项目记录的文件；`--check` 会校验完整 Skill 文件。

安装成功后会自动打印 **30 秒快速上手速查表**，并检测 MarketGraph MCP 数据网关的注册状态——未注册时会给出配置片段与自测命令（手动配置见 [mcp/marketgraph-mcp/README.md](mcp/marketgraph-mcp/README.md)）。

---

## 🗺️ 未来演进路线 (Roadmap)

项目正持续从“独立的单点技能”演进为“全天候跨 Skill 交易闭环协同流水线”：
- **已落地**：公共契约交接摘要（各报告模板内置）、程序化交接存储（`handoff_store.py`）、板块→个股穿透与 L1/L2 继承、盘前↔盘后评估台账自校准闭环、AGENTS.md 时段路由与总控路由 Skill、12 大确定性金融 MCP 网关。
- 详细设计方案与实施阶段规划见：[📖 跨 Skill 交易闭环协同流水线计划 (docs/ROADMAP_CROSS_SKILL_PIPELINE.md)](docs/ROADMAP_CROSS_SKILL_PIPELINE.md)

---

## 🤝 贡献与反馈

欢迎提交 PR 或 Issue 共同完善 A 股 AI 策略提示词库！

- 修改 `SKILL.md` 或公共契约后，请先运行 `python3 scripts/sync_prompts.py` 与 `python3 scripts/sync_skill_contracts.py` 再提交；仓库纪律详见 [AGENTS.md](AGENTS.md)。
- PR 会自动触发 CI：运行全部 **97 项单元测试**（本地可用 `python3 -m unittest discover -s tests`）与契约、Prompt、捆绑脚本三项防漂移检查。
- 当前版本受 `version.json` 控制，每次更新记录见 [CHANGELOG.md](CHANGELOG.md)。
