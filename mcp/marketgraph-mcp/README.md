# MarketGraph Financial MCP Server

专为 `stock-prompt` 及 Agent Plugins 1.0 标准量身打造的 **A 股全套确定性量化金融数据 MCP 服务端**。

## 🌟 核心特性
- **零配置、零注册、免 Token**：底层直连腾讯证券与东方财富公网开放 CDN 网关，彻底抛弃 API Key 与注册认证。
- **纯原生 Python 实现**：基于 Python 3.8+ 标准库（`urllib`, `json`），零第三方外部依赖（无需安装 `akshare` 或 `pandas`），极速毫秒级启动。
- **纯中文股票名秒级智能联想**：全面支持股票代码（`301489`）、带前后缀代码（`sz301489`, `600519.SH`）以及**纯中文股票名称**（如 `贵州茅台`, `中际旭创`）自动无感解析。
- **专为 A 股投研打造的 8 大确定性金融网关**：
  1. `get_stock_quote`: 实时价格、PE(TTM)、PB、总市值、流通市值、换手率与五档盘口。
  2. `get_stock_kline`: 120日前复权连续日K线，自动计算 MA20/MA50、ATR14、Bias，**直接完美通过 `stock-analysis` 行情硬门槛**。
  3. `get_stock_timeline`: 当日 240 分钟分时全景、分时均价线 (VWAP)、盘中放量脉冲时刻与 9:25 集合竞价开盘承接力。
  4. `get_market_sentiment`: 两市总成交额、涨跌停池数量、炸板池数量、全市场精确真实炸板率、最高连板高度。
  5. `get_limit_up_ladder`: 今日或历史指定交易日连板天梯分布、各高度板代表龙头与所属行业。
  6. `get_sector_fund_flow`: 申万与概念行业板块全天主力资金净流入 Top 榜、净流出 Top 榜、涨跌幅榜与领涨龙头代码。
  7. `get_longhubang_detail`: 全市场日度龙虎榜总览或个股前 5 大买卖席位穿透（自动识别机构专用、北向深/沪股通与游资营业部）。
  8. `get_company_quality`: 核心财务指标（营收/净利同比、ROE、毛利率、负债率）、商誉占比、限售解禁日与审计意见状态（L8 排雷直达）。
- **高可用与防风控**：内置浏览器标准 UA 伪装、请求合并与轻量级内存缓存（TTL Cache）。

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
