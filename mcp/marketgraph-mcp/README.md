# MarketGraph Financial MCP Server

专为 `stock-prompt` 及 Agent Plugins 1.0 标准量身打造的 **A 股公开行情与研究辅助 MCP 服务端**。

## 📦 目录结构

```text
marketgraph-mcp/
├── server.py              # stdio JSON-RPC 入口、工具分发与统一响应信封（保持单文件启动兼容）
└── marketgraph_mcp/       # 可复用核心模块（随安装器整目录分发，禁止只拷贝 server.py）
    ├── transport.py       #   HTTP 连接、全局频控与断路器熔断
    ├── cache.py           #   内存 TTL 缓存与历史长缓存
    ├── symbols.py         #   证券代码/指数别名/日期归一化解析
    └── schemas.py         #   tools/list 的 JSON Schema 定义（版本一致性校验读取处）
```

工具实现（providers/tools 层）当前保留在 `server.py` 单模块内：测试套件通过
`SERVER.http_get` 等模块属性打补丁，拆散会破坏该契约；如需进一步模块化，
应先同步迁移 `tests/test_mcp_server.py` 的补丁目标。

## 🌟 核心特性
- **零 Token、标准 stdio**：直连腾讯证券与东方财富公开网关，无需 API Key；首次使用仍需在宿主 MCP 配置中注册。
- **纯原生 Python 实现**：基于 Python 3.8+ 标准库（`urllib`, `json`），零第三方外部依赖（无需安装 `akshare` 或 `pandas`），极速毫秒级启动。
- **纯中文股票名秒级智能联想**：全面支持股票代码（`301489`）、带前后缀代码（`sz301489`, `600519.SH`）以及**纯中文股票名称**（如 `贵州茅台`, `中际旭创`）自动无感解析。
- **专为 A 股投研打造的 21 个数据与闭环工具**：前 17 个为公开数据与上下文工具，后 4 个负责本地 Artifact 闭环；公开网关输出为 P3 线索，不能替代公告、审计报告或交易所披露。
  1. `get_stock_quote`: 实时价格、PE(TTM)、PB、总市值、流通市值、换手率与五档盘口。
  2. `get_stock_kline`: 默认 750 日（3 年，支持 20–800 根调节）前复权连续日 K 线，自动计算 MA20/50/120/250/500 全套均线矩阵、ATR14、Bias、3 年宏观时空坐标（高低区间与分位）、内存无损周线共振（周线 MA10/MA30、趋势定调与 52 周高低区间）、三层威科夫时空模型（宏观牛熊阶段 + 周线大势 + 微观 60 日交易区间）及 20 日量比 / 120 日量能分位；默认开启 Token 精简模式（附最近 30 日 K 线，节省约 85% Token）。仅返回 `adjustment: qfq`、`data_status: ok` 且不少于 120 根时可通过行情结构门槛。
  3. `get_stock_timeline`: 当日 240 分钟分时全景、分时均价线 (VWAP)、盘中放量脉冲时刻与 9:25 集合竞价开盘承接力。
  4. `get_index_kline`: 核心指数（上证指数/深证成指/创业板指/中证全指/沪深300）最近 N 个交易日（最大 130，覆盖 120 日相对强度窗口）收盘、逐日涨跌幅、ATR14（盘前 Z_ATR 判档必需）、MA5/20/60 与 20 日高低点（空间点位候补），确定性直连腾讯指数日K网关。
  5. `get_market_breadth`: 全市场广度 N 日序列——最新交易日为精确上涨/下跌/平盘家数与红盘率（东财涨跌分布快照），历史交易日以涨停/炸板/跌停池与沪指涨跌幅替代并以 `breadth_precision` 标注精度（不估算）。
  6. `get_market_sentiment`: 两市总成交额、涨跌停池数量、炸板池数量、全市场精确真实炸板率、最高连板高度；历史 `date_str` 的指数涨跌幅由腾讯指数日K主源回补（东财日K备源），两市历史成交额由东财指数日K回补（非交易日显式 `unavailable`，不以零值伪装）；`date_str` 支持 YYYYMMDD 或 YYYY-MM-DD。
  7. `get_limit_up_ladder`: 今日或历史指定交易日连板天梯分布、各高度板代表龙头与所属行业；`date_str` 支持 YYYYMMDD 或 YYYY-MM-DD。
  8. `get_sector_limit_quality`: 获取行业板块涨停与炸板封单质量（前缀安全归因与换手封单比）。
  9. `get_sector_fund_flow`: 申万与概念行业板块全天主力资金净流入 Top 榜、净流出 Top 榜、涨跌幅榜与领涨龙头代码；`days=2-10` 时对流入/流出榜板块回补 N 日主力净流入历史、累计净额与趋势定性。
  10. `get_sector_kline`: 东财行业板块指数日K序列（主源为完整 OHLCV+成交额：板块 MA5/10/20/60、5/20/60 日区间涨幅、20/60 日高低点、最新/前一日成交额与量比 `amount_ratio_1d`；主源不可用自动兜底收盘序列+主力净额口径。支持 BK 代码或中文板块名，直供个股 L4 行业基准、daily-review 资金延续 V 项与板块强度证据）；东财板块源整体不可用时返回 `hint` 引导改用 `get_basket_index`。
  11. `get_basket_index`: 以腾讯前复权日K构造等权篮子指数（日度再平衡口径，披露成分覆盖度与失败清单）——东财板块指数不可用时的合规代理序列（如保险 BK0735 仅 6 只成分股），也可用于主线篮子相对强度对照；`series_type=equal_weight_constructed`，构造序列只能用于方向性对照（使用边界见公共研究契约）。
  12. `get_longhubang_detail`: 全市场日度龙虎榜总览或个股前 5 大买卖席位穿透（自动识别机构专用、北向深/沪股通与游资营业部）；机构专用净额按席位合并买卖两榜并附逐席位明细；`date_str` 支持 YYYYMMDD 或 YYYY-MM-DD（自动归一化）。
  13. `get_company_quality`: 核心财务指标、商誉与未来限售解禁筛查；审计、质押、监管和诉讼等未覆盖项明确返回 `N/A`/待核验。
  14. `get_preopen_context`: 盘前推演标准化证据包（指数 K 线与 ATR14、情绪总分、连板天梯与广度红盘率）。
  15. `get_close_review_context`: 收盘复盘标准化证据包（收盘指数、情绪指标、广度、主力资金流向榜与领跑封板质量）。
  16. `get_rotation_context`: 5 日板块轮动标准化证据包（主力资金流动矩阵、指数 5 日基准走势与情绪序列）。
  17. `get_stock_diagnostic_context`: 个股八层诊断标准化证据包（报价估值、750日K线与威科夫结构、财务商誉质量、分时竞价、龙虎榜与基准对比）。
  18. `save_artifact`: 校验并不可变保存标准研究 Artifact，同名快照禁止覆盖。
  19. `load_artifact`: 按快照 ID 或类型、日期、标的读取最新有效 Artifact。
  20. `evaluate_prediction`: 对齐预测与收盘实际快照，计算 Brier、方向命中、板块 Top3 与点位触碰。
  21. `render_report`: 将 Artifact 渲染为 Markdown，或将完整报告数据渲染为 PNG 长图。
- **失败不伪造**：关键上游不可用时返回 `partial` 或 `unavailable`，不会以零值生成市场情绪结论。
- **频控自愈**：同一数据主机全局最小请求间隔（0.5s）+ 连接类失败自动退避重试；同主机连续 3 次失败触发断路器熔断 10 分钟并快速失败，冷却结束自动半开探测；收盘定格的历史数据（龙虎榜、板块资金流历史、历史情绪等）缓存 24 小时，当日盘中数据缓存 3 分钟——从源头避免触发东财 IP 级频控。
- **安全边界**：仅访问预设的 HTTPS 数据主机，并限制单次响应大小；服务端不执行外部命令，Artifact 与报告只写入受控用户状态目录，快照不可覆盖，输出文件名经过白名单校验。

## 🚀 命令行直接调试
无需启动 MCP 宿主，直接使用 `--test` 命令行参数进行免配置验证：
```bash
# 测试个股实时行情 (支持中文名)
python3 mcp/marketgraph-mcp/server.py --test get_stock_quote 贵州茅台

# 测试 750 日 (3年) 前复权 K 线、均线矩阵与周线共振
python3 mcp/marketgraph-mcp/server.py --test get_stock_kline 300308

# 测试当日分时均线与放量脉冲
python3 mcp/marketgraph-mcp/server.py --test get_stock_timeline 301489

# 测试核心指数 5 日逐日涨跌幅 (沪指/深成指/创业板指/中证全指)
python3 mcp/marketgraph-mcp/server.py --test get_index_kline

# 测试全市场广度 5 日序列 (最新交易日精确红盘率 + 历史情绪池)
python3 mcp/marketgraph-mcp/server.py --test get_market_breadth

# 测试全市场涨跌与炸板率
python3 mcp/marketgraph-mcp/server.py --test get_market_sentiment

# 测试连板天梯
python3 mcp/marketgraph-mcp/server.py --test get_limit_up_ladder

# 测试行业板块资金流向 (附 5 日主力净流入历史)
python3 mcp/marketgraph-mcp/server.py --test get_sector_fund_flow 5

# 测试板块指数日K收盘序列 (支持 BK 代码或中文板块名)
python3 mcp/marketgraph-mcp/server.py --test get_sector_kline 半导体

# 测试等权篮子指数 (东财板块源不可用时的代理序列; 逗号分隔成分股)
python3 mcp/marketgraph-mcp/server.py --test get_basket_index 601318,601628,601601,601366

# 测试龙虎榜席位明细
python3 mcp/marketgraph-mcp/server.py --test get_longhubang_detail 思泉新材

# 测试个股财务排雷与解禁
python3 mcp/marketgraph-mcp/server.py --test get_company_quality 思泉新材

# 测试盘前推演标准化证据包
python3 mcp/marketgraph-mcp/server.py --test get_preopen_context

# 测试收盘复盘标准化证据包
python3 mcp/marketgraph-mcp/server.py --test get_close_review_context

# 测试 5 日板块轮动标准化证据包
python3 mcp/marketgraph-mcp/server.py --test get_rotation_context

# 测试个股八层诊断标准化证据包
python3 mcp/marketgraph-mcp/server.py --test get_stock_diagnostic_context 300308
```

## 🔌 在宿主环境中注册 (Antigravity / Gemini / Cursor / Claude)
编辑宿主 MCP 配置文件（例如 `~/.gemini/antigravity/mcp_config.json` 或 Cursor `mcp.json`）：
```json
{
  "mcpServers": {
    "marketgraph-data": {
      "command": "python3",
      "args": ["/绝对路径/to/stock-prompt/mcp/marketgraph-mcp/server.py"]
    }
  }
}
```

## 数据使用边界

- 本服务不会提供买卖指令，也不构成投资建议。
- `data_status != "ok"` 时不得将数据用于评分、概率或方向判断。
- 审计意见、监管处罚、诉讼、股权质押和公司事件须回到交易所公告、定期报告或公司披露核验。
