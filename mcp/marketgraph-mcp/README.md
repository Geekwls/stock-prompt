# MarketGraph Financial MCP Server

专为 `stock-prompt` 及 Agent Plugins 1.0 标准量身打造的 **A 股全套量化金融数据 MCP 服务端**。

## 🌟 核心特性
- **零配置、零注册、免 Token**：底层直连腾讯证券与东方财富公网开放 CDN 网关，彻底抛弃 API Key 与注册认证。
- **纯原生 Python 实现**：基于 Python 3.8+ 标准库（`urllib`, `json`），零第三方外部依赖（无需安装 `akshare` 或 `pandas`），极速启动。
- **专为 A 股投研定制的 4 大工具**：
  1. `get_stock_quote`: 实时价格、PE(TTM)、PB、总市值、流通市值、换手率。
  2. `get_stock_kline`: 120日前复权连续日K线，自动计算 MA20/MA50、ATR14、Bias，**直接完美通过 `stock-analysis` 行情硬门槛**。
  3. `get_market_sentiment`: 两市总成交额、涨跌停池数量、炸板池数量、全市场精确炸板率、最高连板高度。
  4. `get_limit_up_ladder`: 今日连板天梯分布、各高度板代表票与行业。
- **高可用与防风控**：内置浏览器标准 UA 伪装、请求合并与 3 分钟轻量级内存缓存（TTL Cache）。

## 🚀 命令行直接调试
无需启动 MCP 宿主，直接使用 `--test` 命令行参数进行免配置验证：
```bash
# 测试个股实时行情
python3 mcp/marketgraph-mcp/server.py --test get_stock_quote 300308

# 测试 120 日前复权 K 线与技术指标
python3 mcp/marketgraph-mcp/server.py --test get_stock_kline 300308

# 测试全市场涨跌与炸板率
python3 mcp/marketgraph-mcp/server.py --test get_market_sentiment

# 测试连板天梯
python3 mcp/marketgraph-mcp/server.py --test get_limit_up_ladder
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
