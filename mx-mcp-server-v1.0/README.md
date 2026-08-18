# 东方财富妙想 Remote MCP V1.0

将用户提供的 6 个东方财富妙想 Skills 封装为一个可部署到 Railway 的 Remote MCP Server：

- `mx-data` → 金融数据查询
- `mx-search` → 金融资讯搜索
- `mx-xuangu` → 自然语言选股
- `mx-zixuan` → 自选股查询/管理
- `mx-moni` → 模拟组合资金、持仓、委托、模拟买卖/撤单/操作帖
- `mx-poster` → 妙想AI社区动态、发文、点赞、评论

## 1. MCP Tools

| Tool | 类型 | 说明 |
|---|---|---|
| `mx_financial_data` | 只读 | 行情、资金、财务、股东、公司、板块、指数等 |
| `mx_financial_search` | 只读 | 新闻、公告、研报、政策、交易规则等 |
| `mx_stock_screen` | 只读 | 自然语言选股 |
| `mx_watchlist_get` | 只读 | 查询东方财富自选股 |
| `mx_watchlist_manage` | 写入 | 添加/删除自选股 |
| `mx_mock_balance` | 只读 | 查询模拟账户资金 |
| `mx_mock_positions` | 只读 | 查询模拟账户持仓 |
| `mx_mock_orders` | 只读 | 查询模拟委托 |
| `mx_mock_trade` | 写入 | 模拟买卖，要求 `confirm=true` |
| `mx_mock_cancel` | 写入/撤销 | 模拟撤单，要求 `confirm=true` |
| `mx_mock_post` | 写入 | 发布模拟组合操作帖，要求 `confirm=true` |
| `mx_community_list` | 只读 | 查询妙想AI社区动态 |
| `mx_community_post` | 公开写入 | 社区发文，要求 `confirm=true` |
| `mx_community_like` | 公开写入 | 点赞，要求 `confirm=true` |
| `mx_community_reply` | 公开写入 | 评论，要求 `confirm=true` |

> `mx-moni` 仅操作妙想的**模拟组合**，不是券商真实证券交易接口。

## 2. 部署到 Railway（推荐）

### 2.1 GitHub

1. 新建 GitHub 仓库，例如 `mx-mcp-server`。
2. 上传本项目全部文件。
3. **不要上传 `.env`，不要把真实 `MX_APIKEY` 写进代码。**

### 2.2 Railway

1. Railway → `New Project` → `Deploy from GitHub repo`。
2. 选择 `mx-mcp-server` 仓库。
3. Service → `Variables` 添加：

```text
MX_APIKEY=你的新妙想APIKey
MCP_PATH_TOKEN=至少16字符的高强度随机字符串
```

建议正式部署前重新生成一枚妙想 API Key，因为旧 Key 曾经在聊天中明文出现。

4. Service → Settings → Networking → Public Networking → `Generate Domain`。

Railway 会提供类似：

```text
mx-mcp-server-production.up.railway.app
```

本项目会自动读取 Railway 的 `RAILWAY_PUBLIC_DOMAIN`，加入 MCP Host allowlist。

### 2.3 最终 MCP URL

V1.0 默认**要求**设置 `MCP_PATH_TOKEN`，且至少16字符。例如：

```text
MCP_PATH_TOKEN=mx_7f2c91d4e8b34a6fa24b8c10
```

则 MCP URL 为：

```text
https://你的域名/mx_7f2c91d4e8b34a6fa24b8c10/mcp
```

秘密 URL 可以显著降低随机扫描风险，但不是完整身份认证；如果未来多人使用或公开发布，应升级为 OAuth 2.1。只有本地临时测试时才可设置 `ALLOW_INSECURE_NO_TOKEN=true` 使用 `/mcp`。

## 3. 接入 ChatGPT

当前 ChatGPT Developer mode 可以连接 Remote MCP。大致流程：

1. ChatGPT → Settings → Security and login → 开启 Developer mode。
2. ChatGPT Plugins / Apps 中选择添加开发者 MCP App。
3. 填写上面的 HTTPS MCP URL。
4. 扫描 tools。
5. 在测试对话中先执行只读工具：

```text
查一下金发科技当前最新价、涨跌幅和主力资金流。
```

然后测试：

```text
搜索金发科技最近一周的重要公告和研报。
```

最后测试选股：

```text
筛选今天站上5日线、成交量达到昨天1.45倍的A股，排除ST、科创板、北交所。
```

## 4. 安全设计

- `MX_APIKEY` 只从云端环境变量读取，不作为 MCP Tool 参数暴露。
- 所有接口只访问默认官方域名 `https://mkapi2.dfcfs.com/finskillshub`。
- 模拟下单、撤单、社区公开发文、点赞、评论要求 `confirm=true`。
- 工具按 MCP annotations 标记只读/写入/撤销属性，方便 ChatGPT 做确认和风险控制。
- `MCP_PATH_TOKEN` 可降低公网随机扫描风险，但不替代正式 OAuth。
- 如改用自定义域名，请设置：

```text
MCP_ALLOWED_HOSTS=mcp.example.com
```

## 5. 常见错误

### `421 Misdirected Request`

说明域名不在 MCP Host allowlist。

Railway 自带域名会自动读取；自定义域名请在 Variables 添加：

```text
MCP_ALLOWED_HOSTS=mcp.example.com
```

然后重新部署。

### `401` / API 密钥不存在

更新 Railway Variables 中的 `MX_APIKEY`。

### `code=113`

妙想当日 API 调用次数达到上限。

### 社区发文/互动提示未授权

需先在东方财富 APP 完成妙想AI社区相关授权。

## 6. 本地测试（可选）

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MX_APIKEY='你的Key'
export MCP_PATH_TOKEN='local_test_token_1234567890'
python server.py
```

默认要求设置 `MCP_PATH_TOKEN`，所以本地地址为：

```text
http://127.0.0.1:8000/<token>/mcp
```

如果只是本地临时调试，也可以设置 `ALLOW_INSECURE_NO_TOKEN=true` 后使用 `/mcp`。

可使用 MCP Inspector 测试初始化、tools/list 和 tool call。
