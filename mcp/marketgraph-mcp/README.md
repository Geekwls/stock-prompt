# MarketGraph Financial MCP Server

专为 `stock-prompt` 及 Agent Plugins 1.0 标准量身打造的 **A 股公开行情与研究辅助 MCP 服务端**。

## 🌟 核心特性
- **零 Token、标准 stdio**：直连腾讯证券与东方财富公开网关，无需 API Key；首次使用仍需在宿主 MCP 配置中注册。
- **纯原生 Python 实现**：基于 Python 3.8+ 标准库（`urllib`, `json`），零第三方外部依赖（无需安装 `akshare` 或 `pandas`），极速毫秒级启动。
- **纯中文股票名秒级智能联想**：全面支持股票代码（`301489`）、带前后缀代码（`sz301489`, `600519.SH`）以及**纯中文股票名称**（如 `贵州茅台`, `中际旭创`）自动无感解析。
- **专为 A 股投研打造的 8 个公开数据工具**：所有结果均应以响应中的 `source`、`data_status` 和时点为准；公开网关输出为 P3 线索，不能替代公告、审计报告或交易所披露。
  1. `get_stock_quote`: 实时价格、PE(TTM)、PB、总市值、流通市值、换手率与五档盘口。
  2. `get_stock_kline`: 前复权连续日 K 线，自动计算 MA20/MA50、ATR14、Bias；仅返回 `adjustment: qfq`、`data_status: ok` 且不少于 120 根时可通过行情结构门槛。
  3. `get_stock_timeline`: 当日 240 分钟分时全景、分时均价线 (VWAP)、盘中放量脉冲时刻与 9:25 集合竞价开盘承接力。
  4. `get_market_sentiment`: 两市总成交额、涨跌停池数量、炸板池数量、全市场精确真实炸板率、最高连板高度。
  5. `get_limit_up_ladder`: 今日或历史指定交易日连板天梯分布、各高度板代表龙头与所属行业。
  6. `get_sector_fund_flow`: 申万与概念行业板块全天主力资金净流入 Top 榜、净流出 Top 榜、涨跌幅榜与领涨龙头代码。
  7. `get_longhubang_detail`: 全市场日度龙虎榜总览或个股前 5 大买卖席位穿透（自动识别机构专用、北向深/沪股通与游资营业部）。
  8. `get_company_quality`: 核心财务指标、商誉与未来限售解禁筛查；审计、质押、监管和诉讼等未覆盖项明确返回 `N/A`/待核验。
- **失败不伪造**：关键上游不可用时返回 `partial` 或 `unavailable`，不会以零值生成市场情绪结论。
- **安全边界**：仅访问预设的 HTTPS 数据主机，并限制单次响应大小；服务端不执行命令、不读写用户文件。

## 🚀 命令行直接调试
无需启动 MCP 宿主，直接使用 `--test` 命令行参数进行免配置验证：
```bash
# 测试个股实时行情 (支持中文名)
python3 mcp/marketgraph-mcp/server.py --test get_stock_quote 贵州茅台

# 测试 120 日前复权 K 线与技术指标
python3 mcp/marketgraph-mcp/server.py --test get_stock_kline 300308

# 测试当日分时均线与放量脉冲
python3 mcp/marketgraph-mcp/server.py --test get_stock_timeline 301489

# 测试全市场涨跌与炸板率
python3 mcp/marketgraph-mcp/server.py --test get_market_sentiment

# 测试连板天梯
python3 mcp/marketgraph-mcp/server.py --test get_limit_up_ladder

# 测试行业板块资金流向
python3 mcp/marketgraph-mcp/server.py --test get_sector_fund_flow

# 测试龙虎榜席位明细
python3 mcp/marketgraph-mcp/server.py --test get_longhubang_detail 思泉新材

# 测试个股财务排雷与解禁
python3 mcp/marketgraph-mcp/server.py --test get_company_quality 思泉新材
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
