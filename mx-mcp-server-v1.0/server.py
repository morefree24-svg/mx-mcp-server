from __future__ import annotations

import json
import os
import re
from typing import Any, Literal

import httpx
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field
from typing_extensions import Annotated

SERVER_NAME = "eastmoney-mx-mcp"
SERVER_VERSION = "1.0.0"
MX_API_URL = os.getenv("MX_API_URL", "https://mkapi2.dfcfs.com/finskillshub").rstrip("/")
REQUEST_TIMEOUT = float(os.getenv("MX_TIMEOUT", "30"))

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)
WRITE_PRIVATE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)
WRITE_DESTRUCTIVE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=True,
    idempotent_hint=False,
    open_world_hint=True,
)

mcp = MCPServer(
    SERVER_NAME,
    version=SERVER_VERSION,
    title="东方财富妙想 Remote MCP",
    description="将东方财富妙想 mx-data、mx-search、mx-xuangu、mx-zixuan、mx-moni、mx-poster 封装为 Remote MCP tools。",
    instructions=(
        "优先使用只读工具获取金融数据。自选股、模拟交易、社区互动属于写操作。"
        "模拟下单、撤单、模拟组合发帖和公开社区发文/点赞/评论必须在用户明确表达操作意图后调用，"
        "且要求 confirm=true。不要把 MX_APIKEY 暴露到结果、日志或工具参数中。"
    ),
)


def _api_key() -> str:
    key = os.getenv("MX_APIKEY", "").strip()
    if not key:
        raise RuntimeError("云端未配置 MX_APIKEY。请在 Railway Variables 中设置该环境变量。")
    return key


def _headers() -> dict[str, str]:
    return {
        "apikey": _api_key(),
        "Content-Type": "application/json; charset=UTF-8",
        "Accept": "application/json",
    }


async def _request(method: str, endpoint: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{MX_API_URL}{endpoint}"
    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, follow_redirects=True) as client:
            response = await client.request(
                method.upper(),
                url,
                headers=_headers(),
                json=payload if method.upper() != "GET" else None,
            )
        text = response.text
        try:
            data = response.json()
        except ValueError:
            data = {"rawText": text[:8000]}
        if response.is_error:
            return {
                "ok": False,
                "http_status": response.status_code,
                "message": data.get("message") if isinstance(data, dict) else "HTTP error",
                "response": data,
            }
        if isinstance(data, dict):
            return data
        return {"ok": True, "data": data}
    except httpx.TimeoutException:
        return {"ok": False, "error": "东方财富妙想 API 请求超时"}
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"东方财富妙想 API 网络错误: {type(exc).__name__}"}
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}


def _col_key(col: dict[str, Any]) -> str:
    return str(col.get("field") or col.get("name") or col.get("key") or "")


def _col_title(col: dict[str, Any]) -> str:
    base = str(col.get("displayName") or col.get("title") or col.get("label") or _col_key(col))
    date_msg = col.get("dateMsg")
    return f"{base} {date_msg}".strip() if date_msg else base


def _compact_data_result(result: dict[str, Any], max_rows: int) -> dict[str, Any]:
    if result.get("status") not in (0, "0", None):
        return result
    outer = result.get("data", {}) or {}
    inner = outer.get("data", outer) if isinstance(outer, dict) else {}
    search_result = inner.get("searchDataResultDTO", {}) if isinstance(inner, dict) else {}
    dto_list = search_result.get("dataTableDTOList", []) if isinstance(search_result, dict) else []
    tables: list[dict[str, Any]] = []

    for dto in dto_list or []:
        if not isinstance(dto, dict):
            continue
        table = dto.get("table") or {}
        name_map = dto.get("nameMap") or {}
        indicator_order = dto.get("indicatorOrder") or []
        heads = table.get("headName") if isinstance(table, dict) else None
        if not isinstance(heads, list):
            heads = []

        keys: list[str] = []
        for key in indicator_order:
            key = str(key)
            if key in table and key not in keys:
                keys.append(key)
        for key in table.keys() if isinstance(table, dict) else []:
            if key != "headName" and key not in keys:
                keys.append(str(key))

        n = min(max_rows, max([len(heads)] + [len(table.get(k, [])) for k in keys if isinstance(table.get(k), list)] + [0]))
        rows: list[dict[str, Any]] = []
        for i in range(n):
            row: dict[str, Any] = {}
            if heads:
                row[str(name_map.get("headNameSub") or name_map.get("headName") or "时间/维度")] = heads[i] if i < len(heads) else None
            for key in keys:
                values = table.get(key, [])
                value = values[i] if isinstance(values, list) and i < len(values) else None
                row[str(name_map.get(key) or key)] = value
            rows.append(row)

        tables.append(
            {
                "title": dto.get("title") or dto.get("inputTitle"),
                "entity": dto.get("entityName"),
                "code": dto.get("code"),
                "dataType": dto.get("dataType"),
                "rows": rows,
                "truncated": n >= max_rows,
            }
        )

    return {
        "status": result.get("status"),
        "message": result.get("message", ""),
        "questionId": outer.get("questionId") if isinstance(outer, dict) else None,
        "tables": tables,
        "tableCount": len(tables),
    }


def _compact_search_result(result: dict[str, Any], max_items: int) -> dict[str, Any]:
    outer = result.get("data", {}) or {}
    inner = outer.get("data", outer) if isinstance(outer, dict) else {}
    search_response = inner.get("llmSearchResponse", {}) if isinstance(inner, dict) else {}
    items = search_response.get("data", []) if isinstance(search_response, dict) else []
    if not isinstance(items, list):
        return result
    compact = []
    for item in items[:max_items]:
        if not isinstance(item, dict):
            continue
        compact.append({
            "title": item.get("title"),
            "content": item.get("content") or item.get("trunk"),
            "date": item.get("date"),
            "source": item.get("insName") or item.get("source"),
            "informationType": item.get("informationType"),
            "rating": item.get("rating"),
            "entity": item.get("entityFullName"),
            "url": item.get("url") or item.get("sourceUrl"),
        })
    return {
        "status": result.get("status"),
        "message": result.get("message", ""),
        "items": compact,
        "count": len(compact),
        "truncated": len(items) > max_items,
    }


def _compact_screen_result(result: dict[str, Any], max_items: int) -> dict[str, Any]:
    if result.get("status") not in (0, "0", None):
        return result
    outer = result.get("data", {}) or {}
    inner = outer.get("data", outer) if isinstance(outer, dict) else {}
    all_results = inner.get("allResults", {}) if isinstance(inner, dict) else {}
    result_block = all_results.get("result", {}) if isinstance(all_results, dict) else {}
    columns = result_block.get("columns", []) if isinstance(result_block, dict) else []
    data_list = result_block.get("dataList", []) if isinstance(result_block, dict) else []
    column_map = {_col_key(c): _col_title(c) for c in columns if isinstance(c, dict) and _col_key(c)}
    rows = []
    for src in (data_list or [])[:max_items]:
        if not isinstance(src, dict):
            continue
        row = {column_map.get(str(k), str(k)): v for k, v in src.items()}
        rows.append(row)
    return {
        "status": result.get("status"),
        "message": result.get("message", ""),
        "rows": rows,
        "count": len(rows),
        "total": result_block.get("total") if isinstance(result_block, dict) else None,
        "responseConditionList": inner.get("responseConditionList") if isinstance(inner, dict) else None,
        "totalCondition": inner.get("totalCondition") if isinstance(inner, dict) else None,
        "parserText": inner.get("parserText") if isinstance(inner, dict) else None,
        "truncated": isinstance(data_list, list) and len(data_list) > max_items,
    }


@mcp.tool(title="查询东方财富金融数据", annotations=READ_ONLY)
async def mx_financial_data(
    query: Annotated[str, Field(min_length=1, max_length=500, description="自然语言金融数据查询，例如：贵州茅台最新价和主力资金流向")],
    max_rows: Annotated[int, Field(ge=1, le=200, description="每张表最多返回的行数")] = 50,
) -> dict[str, Any]:
    """查询实时/历史行情、资金流、估值、财务、股东、公司信息、板块和指数等东方财富金融数据。"""
    result = await _request("POST", "/api/claw/query", {"toolQuery": query})
    return _compact_data_result(result, max_rows) if isinstance(result, dict) else result


@mcp.tool(title="搜索东方财富金融资讯", annotations=READ_ONLY)
async def mx_financial_search(
    query: Annotated[str, Field(min_length=1, max_length=500, description="自然语言资讯搜索，例如：金发科技最新公告和研报")],
    max_items: Annotated[int, Field(ge=1, le=50, description="最多返回资讯条数")] = 15,
) -> dict[str, Any]:
    """搜索新闻、公告、研报、政策、交易规则、事件和市场解读等金融资讯。"""
    result = await _request("POST", "/api/claw/news-search", {"query": query})
    return _compact_search_result(result, max_items) if isinstance(result, dict) else result


@mcp.tool(title="东方财富自然语言选股", annotations=READ_ONLY)
async def mx_stock_screen(
    query: Annotated[str, Field(min_length=1, max_length=800, description="自然语言选股条件")],
    max_items: Annotated[int, Field(ge=1, le=200, description="最多返回股票数量")] = 100,
) -> dict[str, Any]:
    """基于行情、财务、行业、板块、指数成分等条件进行自然语言选股。"""
    result = await _request("POST", "/api/claw/stock-screen", {"keyword": query})
    return _compact_screen_result(result, max_items) if isinstance(result, dict) else result


@mcp.tool(title="查询我的东方财富自选股", annotations=READ_ONLY)
async def mx_watchlist_get() -> dict[str, Any]:
    """读取当前东方财富通行证账户下的自选股列表。"""
    return await _request("POST", "/api/claw/self-select/get", {})


@mcp.tool(title="修改我的东方财富自选股", annotations=WRITE_DESTRUCTIVE)
async def mx_watchlist_manage(
    instruction: Annotated[str, Field(min_length=1, max_length=300, description="明确的自然语言操作，如：把600519加入自选；从自选删除贵州茅台")],
) -> dict[str, Any]:
    """添加或删除东方财富自选股。只在用户明确要求修改自选股时使用。"""
    return await _request("POST", "/api/claw/self-select/manage", {"query": instruction})


@mcp.tool(title="查询模拟账户资金", annotations=READ_ONLY)
async def mx_mock_balance() -> dict[str, Any]:
    """查询妙想模拟组合的账户资金、总资产、可用资金等信息；不是真实证券账户交易。"""
    return await _request("POST", "/api/claw/mockTrading/balance", {"moneyUnit": 1})


@mcp.tool(title="查询模拟账户持仓", annotations=READ_ONLY)
async def mx_mock_positions() -> dict[str, Any]:
    """查询妙想模拟组合持仓；不是真实证券账户交易。"""
    return await _request("POST", "/api/claw/mockTrading/positions", {"moneyUnit": 1})


@mcp.tool(title="查询模拟账户委托", annotations=READ_ONLY)
async def mx_mock_orders() -> dict[str, Any]:
    """查询妙想模拟组合的当日委托/成交记录；不是真实证券账户交易。"""
    return await _request("POST", "/api/claw/mockTrading/orders", {"fltOrderDrt": 0, "fltOrderStatus": 0})


@mcp.tool(title="模拟买入或卖出", annotations=WRITE_DESTRUCTIVE)
async def mx_mock_trade(
    action: Annotated[Literal["buy", "sell"], Field(description="buy=模拟买入，sell=模拟卖出")],
    stock_code: Annotated[str, Field(pattern=r"^[0369]\d{5}$", description="6位A股代码")],
    quantity: Annotated[int, Field(ge=100, description="股数，通常应为100股整数倍")],
    price: Annotated[float | None, Field(gt=0, description="限价价格；市价模式可不传")] = None,
    use_market_price: Annotated[bool, Field(description="是否按最新行情价模拟委托")] = False,
    confirm: Annotated[bool, Field(description="必须为true才会真正提交模拟委托")] = False,
) -> dict[str, Any]:
    """提交妙想模拟组合买入/卖出。仅影响模拟账户。必须在用户明确确认后将 confirm 设为 true。"""
    if not confirm:
        return {
            "ok": False,
            "requires_confirmation": True,
            "message": "尚未提交模拟委托。请确认股票代码、方向、数量和价格后，再以 confirm=true 调用。",
            "preview": {
                "action": action,
                "stock_code": stock_code,
                "quantity": quantity,
                "price": price,
                "use_market_price": use_market_price,
            },
        }
    if quantity % 100 != 0:
        return {"ok": False, "error": "模拟委托数量需为100股整数倍。"}
    if not use_market_price and price is None:
        return {"ok": False, "error": "限价模拟委托必须提供 price，或将 use_market_price=true。"}
    payload: dict[str, Any] = {
        "type": action,
        "stockCode": stock_code,
        "quantity": quantity,
        "useMarketPrice": use_market_price,
    }
    if not use_market_price and price is not None:
        decimal_places = 2 if stock_code[0] in ("6", "9") else 3
        payload["price"] = int(round(price * (10**decimal_places)))
    return await _request("POST", "/api/claw/mockTrading/trade", payload)


@mcp.tool(title="撤销模拟委托", annotations=WRITE_DESTRUCTIVE)
async def mx_mock_cancel(
    cancel_all: Annotated[bool, Field(description="true=撤销全部未成交模拟委托；false=撤销指定委托")] = False,
    order_id: Annotated[str | None, Field(description="指定模拟委托编号")] = None,
    stock_code: Annotated[str | None, Field(pattern=r"^[0369]\d{5}$", description="指定委托对应的6位A股代码")] = None,
    confirm: Annotated[bool, Field(description="必须为true才会真正撤单")] = False,
) -> dict[str, Any]:
    """撤销妙想模拟组合委托。必须在用户明确确认后将 confirm 设为 true。"""
    if not confirm:
        return {
            "ok": False,
            "requires_confirmation": True,
            "message": "尚未执行撤单。确认后再以 confirm=true 调用。",
        }
    if cancel_all:
        payload = {"type": "all"}
    else:
        if not order_id or not stock_code:
            return {"ok": False, "error": "撤销指定委托需要 order_id 和 stock_code。"}
        payload = {"type": "order", "orderId": order_id, "stockCode": stock_code}
    return await _request("POST", "/api/claw/mockTrading/cancel", payload)


@mcp.tool(title="发布模拟组合操作帖", annotations=WRITE_PRIVATE)
async def mx_mock_post(
    text: Annotated[str, Field(min_length=1, max_length=10000, description="模拟组合操作总结正文")],
    confirm: Annotated[bool, Field(description="必须为true才会发布")]=False,
) -> dict[str, Any]:
    """发布妙想模拟组合操作总结。必须在用户明确要求发布后调用，并设置 confirm=true。"""
    if not confirm:
        return {"ok": False, "requires_confirmation": True, "message": "尚未发布。确认正文后再以 confirm=true 调用。"}
    return await _request("POST", "/api/claw/mockTrading/newPost", {"text": text})


@mcp.tool(title="读取妙想AI社区动态", annotations=READ_ONLY)
async def mx_community_list() -> dict[str, Any]:
    """读取东方财富妙想AI社区动态列表。账号需已在东方财富APP完成相关授权。"""
    return await _request("GET", "/api/aifinancecommunity/queryLxDynamicArticleList")


@mcp.tool(title="发布妙想AI社区文章", annotations=WRITE_PRIVATE)
async def mx_community_post(
    title: Annotated[str, Field(min_length=1, max_length=200, description="文章标题")],
    text_html: Annotated[str, Field(min_length=1, max_length=50000, description="UTF-8 HTML正文，不要把标题重复放进正文")],
    confirm: Annotated[bool, Field(description="必须为true才会公开发布")]=False,
) -> dict[str, Any]:
    """在东方财富妙想AI社区公开发文。账号需已授权；只有用户明确要求发布时才能设置 confirm=true。"""
    if not confirm:
        return {
            "ok": False,
            "requires_confirmation": True,
            "message": "尚未公开发布。请确认标题和正文后，再以 confirm=true 调用。",
            "preview": {"title": title, "text_length": len(text_html)},
        }
    return await _request("POST", "/api/aifinancecommunity/postArticle", {"title": title, "text": text_html})


@mcp.tool(title="点赞妙想AI社区文章", annotations=WRITE_PRIVATE)
async def mx_community_like(
    article_id: Annotated[str, Field(min_length=1, max_length=200, description="社区帖子ID")],
    confirm: Annotated[bool, Field(description="必须为true才会点赞")]=False,
) -> dict[str, Any]:
    """点赞东方财富妙想AI社区文章。账号需已授权；必须有明确的用户操作意图。"""
    if not confirm:
        return {"ok": False, "requires_confirmation": True, "message": "尚未点赞。确认后再以 confirm=true 调用。"}
    return await _request("POST", "/api/aifinancecommunity/likeArticle", {"id": article_id})


@mcp.tool(title="评论妙想AI社区文章", annotations=WRITE_PRIVATE)
async def mx_community_reply(
    article_id: Annotated[str, Field(min_length=1, max_length=200, description="社区帖子ID")],
    text: Annotated[str, Field(min_length=1, max_length=3000, description="评论内容")],
    confirm: Annotated[bool, Field(description="必须为true才会公开评论")]=False,
) -> dict[str, Any]:
    """评论东方财富妙想AI社区文章。账号需已授权；只有用户明确要求公开评论时才能设置 confirm=true。"""
    if not confirm:
        return {"ok": False, "requires_confirmation": True, "message": "尚未公开评论。确认内容后再以 confirm=true 调用。"}
    return await _request("POST", "/api/aifinancecommunity/replyArticle", {"id": article_id, "text": text})


def _split_csv_env(name: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def _transport_security() -> TransportSecuritySettings:
    allowed_hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_domain:
        allowed_hosts += [railway_domain, f"{railway_domain}:*"]
    for host in _split_csv_env("MCP_ALLOWED_HOSTS"):
        allowed_hosts += [host, f"{host}:*"] if ":" not in host else [host]

    allowed_origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    allowed_origins += _split_csv_env("MCP_ALLOWED_ORIGINS")

    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=list(dict.fromkeys(allowed_hosts)),
        allowed_origins=list(dict.fromkeys(allowed_origins)),
    )


def _mcp_path() -> str:
    token = os.getenv("MCP_PATH_TOKEN", "").strip()
    allow_insecure = os.getenv("ALLOW_INSECURE_NO_TOKEN", "").strip().lower() in {"1", "true", "yes"}
    if not token:
        if allow_insecure:
            return "/mcp"
        raise RuntimeError(
            "未配置 MCP_PATH_TOKEN。为避免把包含账户能力的 MCP 端点直接暴露到公网，"
            "请设置一段足够长的随机字符串；仅本地临时测试时可设置 ALLOW_INSECURE_NO_TOKEN=true。"
        )
    safe = re.sub(r"[^A-Za-z0-9_-]", "", token)[:120]
    if len(safe) < 16:
        raise RuntimeError("MCP_PATH_TOKEN 至少需要16个字母/数字/下划线/连字符字符。")
    return f"/{safe}/mcp"


# Railway/uvicorn 直接加载这个 ASGI app。
app = mcp.streamable_http_app(
    streamable_http_path=_mcp_path(),
    json_response=True,
    stateless_http=True,
    host="0.0.0.0",
    transport_security=_transport_security(),
)

if __name__ == "__main__":
    # 本地直接运行时可用；Railway 默认通过 Dockerfile 的 uvicorn 启动。
    mcp.run(
        "streamable-http",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        streamable_http_path=_mcp_path(),
        json_response=True,
        stateless_http=True,
        transport_security=_transport_security(),
    )
