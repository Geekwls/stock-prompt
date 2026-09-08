"""13 个 MCP 工具的 JSON Schema 定义（供 tools/list 声明）。"""

AVAILABLE_TOOLS = [
    {
        "name": "get_stock_quote",
        "description": "获取 A 股个股实时行情、PE(TTM)、PB、总市值、流通市值、换手率与五档盘口（支持代码或中文名，毫秒级直连）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或简称，例如 '300308', '000938.SZ', 'sh600519', '贵州茅台'",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_kline",
        "description": "获取 A 股个股 750 日 (3年) 连续前复权日K线、全套均线矩阵 (MA20/50/120/250/500)、3年宏观时空坐标、内存无损周线共振与三层威科夫时空模型（宏观牛熊阶段+周线大势+微观60日交易区间与量价触发）（支持代码或中文名，完全满足行情硬门槛）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '300308', '中际旭创'",
                },
                "count": {
                    "type": "integer",
                    "description": "K 线根数，默认 750 (整整3年宏观时空，含MA120/MA250/MA500两年线与周线共振)；支持 20 至 800 根自由调节",
                    "default": 750,
                    "minimum": 20,
                    "maximum": 800,
                },
                "compact": {
                    "type": "boolean",
                    "description": "是否开启 Token 瘦身精简模式（默认 true，附最近30日K线、3年宏观时空坐标与周线共振指标，节省85% Token；传 false 则返回全量日线数组）",
                    "default": True,
                },
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_stock_timeline",
        "description": "获取 A 股个股当日分时全景、分时均价线 (VWAP)、盘中量能脉冲时刻与 9:25 集合竞价承接力（支持代码或中文名）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '301489', '贵州茅台', '中际旭创'",
                }
            },
            "required": ["symbol"],
        },
    },
    {
        "name": "get_index_kline",
        "description": "获取核心指数（上证指数/深证成指/创业板指/中证全指/沪深300）最近 N 个交易日的收盘、逐日涨跌幅、ATR14、MA5/20/60 与 20 日高低点，确定性直连腾讯指数日K网关（ATR14 支撑盘前 Z_ATR 判档，均线与高低点支撑空间点位测算；直供5日轮动全窗口指数强弱与个股 L4 宽基基准）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "indices": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "指数列表，支持 SHCI/SZCI/CYB/CSIALL/HS300 或中文别名（上证指数/深成指/创业板指/中证全指/沪深300），省略默认返回前四个",
                },
                "count": {
                    "type": "integer",
                    "description": "交易日数量，默认 5；最大 130 (覆盖 L4 的 120 日相对强度窗口；count>=15 时输出 ATR14)",
                    "default": 5,
                    "minimum": 2,
                    "maximum": 130,
                },
            },
        },
    },
    {
        "name": "get_market_breadth",
        "description": "获取全市场广度 N 个交易日序列：最新交易日为精确上涨/下跌/平盘家数与红盘率（东财涨跌分布快照），历史交易日以涨停/炸板/跌停池与沪指涨跌幅替代并通过 breadth_precision 显式标注精度（不估算）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "交易日窗口，默认 5",
                    "default": 5,
                    "minimum": 2,
                    "maximum": 10,
                },
            },
        },
    },
    {
        "name": "get_market_sentiment",
        "description": "获取全市场情绪总分指标（两市成交总额、涨停家数、炸板家数、真实炸板率、最高连板高度）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "交易日期，格式 YYYYMMDD 或 YYYY-MM-DD，省略则为当天",
                    "pattern": "^[0-9]{8}$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                }
            },
        },
    },
    {
        "name": "get_limit_up_ladder",
        "description": "获取今日或指定交易日的 A 股连板天梯分布（各连板高度数量、领航龙头标的与所属行业）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "date_str": {
                    "type": "string",
                    "description": "交易日期，格式 YYYYMMDD 或 YYYY-MM-DD，省略则为当天",
                    "pattern": "^[0-9]{8}$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                }
            },
        },
    },
    {
        "name": "get_sector_limit_quality",
        "description": "获取行业板块当日或指定交易日的触板结构：涨停/炸板清单、板块炸板率与封板质量 Q=(1-板块炸板率)×100（触板<3家记 null）。涨停池/炸板池 hybk 行业字段为 ≤4 字缩写（如\"农产品加工\"→\"农产品加\"），本工具在确定性层完成前缀安全匹配与多板块歧义剔除，杜绝按板块全称精确匹配漏票导致的板块炸板率失真",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "description": "行业板块 BK 代码或中文名，例如 'BK1036', '半导体', '农产品加工'（概念板块无 hybk 归属，不支持）",
                },
                "date_str": {
                    "type": "string",
                    "description": "交易日期，格式 YYYYMMDD 或 YYYY-MM-DD，省略则为当天",
                    "pattern": "^[0-9]{8}$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                }
            },
            "required": ["sector"],
        },
    },
    {
        "name": "get_sector_fund_flow",
        "description": "获取 A 股全行业板块主力资金净流入榜、流出榜、涨幅榜、跌幅榜及领涨龙头股票；days>1 时对流入/流出榜板块回补 N 日主力净流入历史与趋势定性（直供复盘与5日轮动资金迁移）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {
                    "type": "integer",
                    "description": "返回的行业板块数量，默认 20；days>1 时上限 12",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
                "days": {
                    "type": "integer",
                    "description": "主力资金流历史天数，默认 1（仅当日）；支持 2-10 日回补",
                    "default": 1,
                    "minimum": 1,
                    "maximum": 10,
                },
            },
        },
    },
    {
        "name": "get_sector_kline",
        "description": "获取东财行业板块指数日K序列（主源为完整OHLCV+成交额：板块 MA5/10/20/60、5/20/60日区间涨幅、20/60日高低点、最新/前一日成交额与量比 amount_ratio_1d；主源不可用自动兜底收盘序列+主力净额口径。支持板块代码 BK1036 或中文板块名，直供个股 L4 行业基准、daily-review 资金延续 V 项与板块强度证据）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sector": {
                    "type": "string",
                    "description": "板块代码 (如 BK1036) 或中文板块名 (如 半导体)；板块代码可先经 get_sector_fund_flow 查询",
                },
                "count": {
                    "type": "integer",
                    "description": "交易日数量，默认 130 (覆盖 L4 的 120 日相对强度窗口)",
                    "default": 130,
                    "minimum": 20,
                    "maximum": 250,
                },
            },
            "required": ["sector"],
        },
    },
    {
        "name": "get_basket_index",
        "description": "以腾讯前复权日K构造等权篮子指数（日度再平衡口径，披露成分覆盖度与失败清单）：东财板块指数网关不可用时的合规代理序列（如保险 BK0735 仅6只成分股），也可用于主线篮子相对强度对照；构造序列只能用于方向性对照，不得用于精确评分阈值（使用边界见公共研究契约）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "stocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "成分股列表（2-10 个，支持代码或中文名），如 ['601318','601628','601601','601366']",
                },
                "count": {
                    "type": "integer",
                    "description": "交易日数量，默认 20",
                    "default": 20,
                    "minimum": 5,
                    "maximum": 60,
                },
            },
            "required": ["stocks"],
        },
    },
    {
        "name": "get_longhubang_detail",
        "description": "获取 A 股交易所公开龙虎榜席位明细（全市场当日上榜概览或指定个股前5大买卖席位穿透，支持代码或中文名）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '301489', '思泉新材'，省略时返回全市场龙虎榜概览",
                },
                "date_str": {
                    "type": "string",
                    "description": "交易日期 YYYYMMDD 或 YYYY-MM-DD，省略则为最新交易日",
                    "pattern": "^[0-9]{8}$|^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                },
            },
        },
    },
    {
        "name": "get_company_quality",
        "description": "获取 A 股个股基本面质量财务指标（营收/净利同比、ROE、毛利率、负债率）、商誉占比、限售解禁日与审计意见状态（支持代码或中文名）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "股票代码或中文名，例如 '301489', '思泉新材'",
                }
            },
            "required": ["symbol"],
        },
    },
]
