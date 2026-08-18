# 原始 Skills → Remote MCP 映射

根据用户上传的 6 个 ZIP 中 `SKILL.md` 与 Python 脚本整理。

## mx-data

- 原接口：`POST /api/claw/query`
- Header：`apikey: MX_APIKEY`
- Body：`{"toolQuery":"自然语言查询"}`
- MCP：`mx_financial_data`

## mx-search

- 原接口：`POST /api/claw/news-search`
- Body：`{"query":"自然语言搜索"}`
- MCP：`mx_financial_search`

## mx-xuangu

- 原接口：`POST /api/claw/stock-screen`
- Body：`{"keyword":"自然语言选股条件"}`
- MCP：`mx_stock_screen`

## mx-zixuan

- 查询：`POST /api/claw/self-select/get`，Body `{}`
- 管理：`POST /api/claw/self-select/manage`，Body `{"query":"自然语言操作"}`
- MCP：`mx_watchlist_get` / `mx_watchlist_manage`

## mx-moni

- `POST /api/claw/mockTrading/balance`
- `POST /api/claw/mockTrading/positions`
- `POST /api/claw/mockTrading/orders`
- `POST /api/claw/mockTrading/trade`
- `POST /api/claw/mockTrading/cancel`
- `POST /api/claw/mockTrading/newPost`

注意：原脚本对限价委托价格会按市场小数位放大成整数：6/9 开头代码 ×100，其他 ×1000。MCP 已保留该转换逻辑。

## mx-poster

- 动态：`GET /api/aifinancecommunity/queryLxDynamicArticleList`
- 发文：`POST /api/aifinancecommunity/postArticle`
- 点赞：`POST /api/aifinancecommunity/likeArticle`
- 评论：`POST /api/aifinancecommunity/replyArticle`

这些工具会影响东方财富社区，MCP 强制要求 `confirm=true` 才执行写操作。
