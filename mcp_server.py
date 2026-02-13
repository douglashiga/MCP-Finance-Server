import asyncio
import inspect
import json
import logging
import os
import signal
import time
import uuid
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable, Dict, List, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel

# Fix Event Loop before ib_insync import
try:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
except Exception:
    pass

from core.connection import ib_conn
from core.decorators import require_connection
from services.market_service import MarketService
from services.history_service import HistoryService
from services.account_service import AccountService
from services.option_service import OptionService
from services.yahoo_service import YahooService
from services.screener_service import ScreenerService
from services.job_service import JobService
from services.option_screener_service import OptionScreenerService
from services.classification_service import ClassificationService
from services.wheel_service import WheelService
from services.event_service import EventService
from services.market_intelligence_service import MarketIntelligenceService

# Local DB imports
from dataloader.database import SessionLocal
from dataloader.models import (
    Stock, Fundamental, Dividend, HistoricalPrice, 
    HistoricalEarnings, EarningsCalendar
)

# Configure logging
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP Server
MCP_HOST = os.environ.get('MCP_HOST', '0.0.0.0')
MCP_PORT = int(os.environ.get('MCP_PORT', '8000'))
MCP_TRANSPORT = os.environ.get('MCP_TRANSPORT', 'sse')  # 'sse' for network, 'stdio' for local
IB_ENABLED = os.environ.get("IB_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
DEFAULT_MARKET = os.environ.get("DEFAULT_MARKET", "sweden").lower()
DEFAULT_MARKET_TIMEZONE = os.environ.get("DEFAULT_MARKET_TIMEZONE", "Europe/Stockholm")

_allowlist_raw = os.environ.get("MCP_TOOL_ALLOWLIST", "").strip()
MCP_TOOL_ALLOWLIST = {
    item.strip()
    for item in _allowlist_raw.split(",")
    if item.strip()
}

mcp = FastMCP("mcp-finance", host=MCP_HOST, port=MCP_PORT)

# LLM-friendly capability map for "what can you do?" queries.
MARKET_CAPABILITIES = [
    {
        "category": "market_data",
        "description": "Precos em tempo real, busca de ticker e historico OHLCV.",
        "methods": ["get_stock_price", "get_historical_data", "search_symbol"],
        "examples": [
            "Qual o preco atual da Nordea?",
            "Me traga 1 mes de candles diarios da SEB.",
        ],
    },
    {
        "category": "fundamentals",
        "description": "Fundamentos, dividendos e perfil de empresa.",
        "methods": [
            "get_fundamentals",
            "get_dividends",
            "get_dividend_history",
            "get_company_info",
            "get_comprehensive_stock_info",
            "get_financial_statements",
        ],
        "examples": [
            "Quais os fundamentos da VOLV-B.ST?",
            "Quais acoes suecas pagam mais dividendos?",
        ],
    },
    {
        "category": "stock_screener",
        "description": "Rankings por performance, RSI, sinais tecnicos e filtros por setor.",
        "methods": [
            "get_stock_screener", "get_top_gainers", "get_top_losers", "get_most_active_stocks",
            "get_highest_rsi", "get_lowest_rsi", "get_top_dividend_payers", "get_fundamental_rankings",
            "get_technical_signals", "get_companies_by_sector", "get_company_core_business",
        ],
        "examples": [
            "Quais sao as maiores altas hoje na Suecia?",
            "Top 5 acoes com maior RSI hoje.",
        ],
    },
    {
        "category": "options_and_greeks",
        "description": "Option chain, greeks e screener de opcoes com filtros de delta/IV/liquidez.",
        "methods": [
            "get_option_chain",
            "get_option_greeks",
            "get_option_screener",
            "get_option_chain_snapshot",
            "get_options_data",
        ],
        "examples": [
            "Mostre puts com delta entre 0.25 e 0.35 para Nordea.",
            "Qual o delta/IV da call da SEB com vencimento mais proximo?",
        ],
    },
    {
        "category": "market_intelligence",
        "description": "News, holders institucionais, recomendacoes de analistas e analise tecnica via cache local.",
        "methods": [
            "get_news",
            "get_institutional_holders",
            "get_analyst_recommendations",
            "get_technical_analysis",
            "get_sector_performance",
            "get_historical_data_cached",
        ],
        "examples": [
            "Quais sao as noticias mais recentes da Volvo?",
            "Me mostre analise tecnica (RSI/MACD/Bollinger) da Nordea.",
        ],
    },
    {
        "category": "wheel_strategy",
        "description": "Analises completas de Wheel: selecao de put/call, retorno, risco e stress tests.",
        "methods": [
            "get_wheel_put_candidates", "get_wheel_put_annualized_return", "get_wheel_contract_capacity",
            "analyze_wheel_put_risk", "get_wheel_assignment_plan", "get_wheel_covered_call_candidates",
            "compare_wheel_premiums", "evaluate_wheel_iv", "simulate_wheel_drawdown",
            "compare_wheel_start_timing", "build_wheel_multi_stock_plan", "stress_test_wheel_portfolio",
        ],
        "examples": [
            "Qual PUT vender esta semana em Nordea com risco moderado?",
            "Com 200.000 SEK, quantos contratos de Swedbank posso vender?",
        ],
    },
    {
        "category": "event_calendar",
        "description": "Calendario de eventos corporativos, macro, politica monetaria e estrutura de mercado.",
        "methods": [
            "get_event_calendar", "get_corporate_events", "get_macro_events",
            "get_monetary_policy_events", "get_geopolitical_events",
            "get_market_structure_events", "get_wheel_event_risk_window",
        ],
        "examples": [
            "Quais eventos podem impactar Nordea nos proximos 14 dias?",
            "Quais eventos macro na Suecia essa semana?",
        ],
    },
    {
        "category": "pipeline_and_jobs",
        "description": "Observabilidade e controle dos jobs de carga/transformacao.",
        "methods": ["list_jobs", "get_job_logs", "trigger_job", "toggle_job", "get_job_status", "run_pipeline_health_check"],
        "examples": [
            "Mostre status dos jobs do pipeline.",
            "Dispare o job Calculate Stock Metrics agora.",
        ],
    },
    {
        "category": "server_introspection",
        "description": "Descoberta de tools e observabilidade operacional.",
        "methods": ["describe_tool", "help_tool", "get_server_health", "get_server_metrics", "get_market_capabilities"],
        "examples": [
            "Descreva os parametros da tool get_option_screener.",
            "Me mostre a saude do servidor e metricas.",
        ],
    },
]


ALLOWED_HISTORICAL_DURATIONS = {"1 D", "1 W", "1 M", "3 M", "1 Y"}
ALLOWED_HISTORICAL_BAR_SIZES = {"1 min", "5 mins", "15 mins", "1 hour", "1 day"}
ALLOWED_OPTION_RIGHTS = {"C", "P"}
CB_FAILURE_THRESHOLD = int(os.environ.get("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "4"))
CB_COOLDOWN_SECONDS = int(os.environ.get("CIRCUIT_BREAKER_COOLDOWN_SECONDS", "45"))

TOOL_METRICS: Dict[str, Any] = {
    "requests_total": 0,
    "failures_total": 0,
    "latency_ms_total": 0.0,
    "tool_calls": {},
    "tool_failures": {},
    "source_calls": {},
    "source_failures": {},
}

TOOL_REGISTRY: Dict[str, Callable[..., Any]] = {}


class HistoricalDataInput(BaseModel):
    duration: str = "1 D"
    bar_size: str = "1 hour"


class OptionGreeksInput(BaseModel):
    last_trade_date: str
    right: str


class OptionScreenerInput(BaseModel):
    right: Optional[str] = None
    limit: int = 50


TOOL_INPUT_MODELS: Dict[str, type[BaseModel]] = {
    "get_historical_data": HistoricalDataInput,
    "get_option_greeks": OptionGreeksInput,
    "get_option_screener": OptionScreenerInput,
}


class _CircuitBreaker:
    def __init__(self):
        self._states: Dict[str, Dict[str, Any]] = {}

    def _state(self, source: str) -> Dict[str, Any]:
        return self._states.setdefault(
            source,
            {"consecutive_failures": 0, "opened_until": 0.0, "last_error": None},
        )

    def is_open(self, source: str) -> bool:
        state = self._state(source)
        return time.time() < float(state["opened_until"])

    def on_success(self, source: str) -> None:
        state = self._state(source)
        state["consecutive_failures"] = 0
        state["opened_until"] = 0.0
        state["last_error"] = None

    def on_failure(self, source: str, error_message: str) -> None:
        state = self._state(source)
        state["consecutive_failures"] += 1
        state["last_error"] = error_message
        if state["consecutive_failures"] >= CB_FAILURE_THRESHOLD:
            state["opened_until"] = time.time() + CB_COOLDOWN_SECONDS

    def snapshot(self) -> Dict[str, Any]:
        now = time.time()
        out: Dict[str, Any] = {}
        for source, state in self._states.items():
            out[source] = {
                "is_open": now < float(state["opened_until"]),
                "opened_for_seconds": max(0, int(state["opened_until"] - now)),
                "consecutive_failures": state["consecutive_failures"],
                "last_error": state["last_error"],
            }
        return out


CIRCUIT_BREAKER = _CircuitBreaker()


def _safe_iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_error(error: Any) -> Dict[str, Any]:
    if error is None:
        return {"code": None, "message": None, "details": None}
    if isinstance(error, dict):
        return {
            "code": error.get("code"),
            "message": error.get("message") or error.get("error") or "Unknown error",
            "details": error.get("details"),
        }
    return {"code": "runtime_error", "message": str(error), "details": None}


def _annotation_to_string(annotation: Any) -> str:
    if annotation is inspect.Signature.empty:
        return "Any"
    if isinstance(annotation, type):
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _is_tool_allowed(tool_name: str) -> bool:
    if not MCP_TOOL_ALLOWLIST:
        return True
    return tool_name in MCP_TOOL_ALLOWLIST


def _infer_source(tool_name: str) -> str:
    if tool_name in {"get_stock_price", "get_historical_data", "search_symbol", "get_account_summary", "get_option_chain", "get_option_greeks"}:
        return "ibkr"
    if tool_name in {"get_fundamentals", "get_dividends", "get_company_info", "get_financial_statements", "get_exchange_info", "yahoo_search", "get_comprehensive_stock_info"}:
        return "yahoo"
    if tool_name.startswith("get_job_") or tool_name in {"list_jobs", "trigger_job", "toggle_job", "run_pipeline_health_check"}:
        return "pipeline"
    if "wheel" in tool_name:
        return "wheel_engine"
    if "event" in tool_name:
        return "event_store"
    if "option" in tool_name:
        return "options_cache"
    if "local" in tool_name or "earnings" in tool_name:
        return "local_db"
    if tool_name in {"describe_tool", "help_tool", "get_server_health", "get_server_metrics"}:
        return "system"
    return "mixed"


def _normalize_tool_result(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        known = {"success", "data", "error", "meta"}
        normalized = {
            "success": bool(result.get("success", True)),
            "data": result.get("data"),
            "error": _normalize_error(result.get("error")),
            "meta": result.get("meta") if isinstance(result.get("meta"), dict) else {},
        }
        for k, v in result.items():
            if k not in known:
                normalized[k] = v
        if "data" not in result and normalized["success"]:
            normalized["data"] = {
                k: v for k, v in result.items() if k not in {"success", "error", "meta"}
            }
        return normalized

    return {
        "success": True,
        "data": result,
        "error": _normalize_error(None),
        "meta": {},
    }


def _record_metrics(tool_name: str, source: str, success: bool, latency_ms: float) -> None:
    TOOL_METRICS["requests_total"] += 1
    TOOL_METRICS["latency_ms_total"] += latency_ms
    TOOL_METRICS["tool_calls"][tool_name] = TOOL_METRICS["tool_calls"].get(tool_name, 0) + 1
    TOOL_METRICS["source_calls"][source] = TOOL_METRICS["source_calls"].get(source, 0) + 1
    if not success:
        TOOL_METRICS["failures_total"] += 1
        TOOL_METRICS["tool_failures"][tool_name] = TOOL_METRICS["tool_failures"].get(tool_name, 0) + 1
        TOOL_METRICS["source_failures"][source] = TOOL_METRICS["source_failures"].get(source, 0) + 1


def _prometheus_metrics() -> str:
    requests_total = TOOL_METRICS["requests_total"]
    failures_total = TOOL_METRICS["failures_total"]
    avg_latency = (
        TOOL_METRICS["latency_ms_total"] / requests_total if requests_total else 0.0
    )
    lines = [
        "# HELP mcp_requests_total Total tool requests",
        "# TYPE mcp_requests_total counter",
        f"mcp_requests_total {requests_total}",
        "# HELP mcp_failures_total Total failed tool requests",
        "# TYPE mcp_failures_total counter",
        f"mcp_failures_total {failures_total}",
        "# HELP mcp_latency_avg_ms Average tool latency in ms",
        "# TYPE mcp_latency_avg_ms gauge",
        f"mcp_latency_avg_ms {avg_latency:.4f}",
    ]
    for name, count in sorted(TOOL_METRICS["tool_calls"].items()):
        lines.append(f'mcp_tool_calls_total{{tool="{name}"}} {count}')
    for name, count in sorted(TOOL_METRICS["tool_failures"].items()):
        lines.append(f'mcp_tool_failures_total{{tool="{name}"}} {count}')
    return "\n".join(lines) + "\n"


def _validate_historical_params(duration: str, bar_size: str) -> None:
    payload = _model_validate(HistoricalDataInput, {"duration": duration, "bar_size": bar_size})
    if payload.duration not in ALLOWED_HISTORICAL_DURATIONS:
        raise ValueError(
            f"Invalid duration '{payload.duration}'. Allowed: {sorted(ALLOWED_HISTORICAL_DURATIONS)}"
        )
    if payload.bar_size not in ALLOWED_HISTORICAL_BAR_SIZES:
        raise ValueError(
            f"Invalid bar_size '{payload.bar_size}'. Allowed: {sorted(ALLOWED_HISTORICAL_BAR_SIZES)}"
        )


def _validate_option_greeks_params(last_trade_date: str, right: str) -> None:
    payload = _model_validate(
        OptionGreeksInput, {"last_trade_date": last_trade_date, "right": right}
    )
    if len(payload.last_trade_date) != 8 or not payload.last_trade_date.isdigit():
        raise ValueError("last_trade_date must be in YYYYMMDD format")
    if payload.right.upper() not in ALLOWED_OPTION_RIGHTS:
        raise ValueError("right must be 'C' or 'P'")


def _validate_option_screener_params(right: Optional[str], limit: int) -> None:
    payload = _model_validate(OptionScreenerInput, {"right": right, "limit": limit})
    if payload.right:
        normalized = payload.right.upper()
        if normalized in {"CALL", "PUT"}:
            normalized = normalized[0]
        if normalized not in ALLOWED_OPTION_RIGHTS:
            raise ValueError("right must be 'C', 'P', 'CALL', 'PUT' or null")
    if payload.limit < 1 or payload.limit > 500:
        raise ValueError("limit must be between 1 and 500")


def _model_validate(model_cls: type[BaseModel], payload: Dict[str, Any]) -> BaseModel:
    model_validate = getattr(model_cls, "model_validate", None)
    if callable(model_validate):
        return model_validate(payload)
    return model_cls.parse_obj(payload)


def _model_schema(model_cls: type[BaseModel]) -> Dict[str, Any]:
    model_json_schema = getattr(model_cls, "model_json_schema", None)
    if callable(model_json_schema):
        return model_json_schema()
    return model_cls.schema()


def tool_endpoint(source: Optional[str] = None):
    def decorator(func: Callable[..., Any]):
        tool_name = func.__name__
        tool_source = source or _infer_source(tool_name)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            request_id = uuid.uuid4().hex
            started = time.perf_counter()

            if not _is_tool_allowed(tool_name):
                response = {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "tool_not_allowed",
                        "message": f"Tool '{tool_name}' is not allowed by MCP_TOOL_ALLOWLIST.",
                        "details": {"allowlist": sorted(MCP_TOOL_ALLOWLIST)},
                    },
                    "meta": {},
                }
            elif CIRCUIT_BREAKER.is_open(tool_source):
                response = {
                    "success": False,
                    "data": None,
                    "error": {
                        "code": "circuit_open",
                        "message": f"Upstream source '{tool_source}' is temporarily open-circuited.",
                        "details": {"retry_after_seconds": CB_COOLDOWN_SECONDS},
                    },
                    "meta": {},
                }
            else:
                try:
                    raw = await func(*args, **kwargs)
                    response = _normalize_tool_result(raw)
                except ValueError as exc:
                    response = {
                        "success": False,
                        "data": None,
                        "error": _normalize_error(
                            {
                                "code": "validation_error",
                                "message": str(exc),
                                "details": None,
                            }
                        ),
                        "meta": {},
                    }
                except Exception as exc:
                    logger.exception("[TOOL_ERROR] %s failed", tool_name)
                    response = {
                        "success": False,
                        "data": None,
                        "error": _normalize_error(
                            {
                                "code": "internal_error",
                                "message": str(exc),
                                "details": {"exception_type": type(exc).__name__},
                            }
                        ),
                        "meta": {},
                    }

            latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
            response["error"] = _normalize_error(response.get("error"))
            response_meta = response.get("meta", {}) or {}
            response["meta"] = {
                **response_meta,
                "request_id": request_id,
                "source": response_meta.get("source") or tool_source,
                "asof": response_meta.get("asof") or _safe_iso_utc_now(),
                "cache_ttl": response_meta.get("cache_ttl"),
                "default_market": DEFAULT_MARKET,
                "market_timezone": DEFAULT_MARKET_TIMEZONE,
                "transport": MCP_TRANSPORT,
                "ib_enabled": IB_ENABLED,
                "latency_ms": latency_ms,
            }

            tracked_sources = {"ibkr", "yahoo", "options_cache", "mixed"}
            error_code = response["error"]["code"]
            if tool_source in tracked_sources:
                if response["success"]:
                    CIRCUIT_BREAKER.on_success(tool_source)
                elif error_code not in {"tool_not_allowed", "circuit_open", "validation_error"}:
                    CIRCUIT_BREAKER.on_failure(tool_source, response["error"]["message"] or "unknown")

            _record_metrics(tool_name, tool_source, response["success"], latency_ms)
            logger.info(
                json.dumps(
                    {
                        "event": "tool_call",
                        "tool": tool_name,
                        "success": response["success"],
                        "source": tool_source,
                        "request_id": request_id,
                        "latency_ms": latency_ms,
                    }
                )
            )
            return response

        wrapper.__is_finance_tool__ = True
        wrapper.__tool_source__ = tool_source
        TOOL_REGISTRY[tool_name] = wrapper
        return wrapper

    return decorator


@mcp.tool()
@tool_endpoint()
async def get_market_capabilities() -> Dict[str, Any]:
    """
    Lista as capacidades do servidor financeiro por categoria, incluindo metodos e exemplos de perguntas.

    Use este metodo quando o usuario perguntar:
    - "que tipo de informacao voce pode prover?"
    - "o que voce consegue fazer?"
    - "quais metodos existem para mercado/opcoes/wheel?"
    """
    return {
        "data": {
            "default_market": DEFAULT_MARKET,
            "market_timezone": DEFAULT_MARKET_TIMEZONE,
            "profiles": {
                "yahoo_only": {"ib_enabled": False, "description": "Fundamentals, screeners, eventos e analytics sem conexao IBKR."},
                "ibkr_plus_yahoo": {"ib_enabled": True, "description": "Real-time IBKR + Yahoo + cache local."},
            },
            "categories": MARKET_CAPABILITIES,
            "usage_hint": "Escolha uma categoria e use os methods sugeridos; para duvidas gerais, comece por stock_screener, wheel_strategy e event_calendar.",
        }
    }


@mcp.tool()
@tool_endpoint(source="system")
async def describe_tool(tool_name: str) -> Dict[str, Any]:
    """Describe tool parameters, defaults, and examples for MCP clients."""
    fn = TOOL_REGISTRY.get(tool_name)
    if not fn:
        return {
            "success": False,
            "error": {
                "code": "tool_not_found",
                "message": f"Tool '{tool_name}' not found.",
                "details": {"available_count": len(TOOL_REGISTRY)},
            },
        }

    signature = inspect.signature(fn)
    parameters = []
    for name, param in signature.parameters.items():
        if name in {"args", "kwargs"}:
            continue
        default = None if param.default is inspect.Signature.empty else param.default
        required = param.default is inspect.Signature.empty
        parameters.append(
            {
                "name": name,
                "type": _annotation_to_string(param.annotation),
                "required": required,
                "default": default,
            }
        )

    examples: List[str] = []
    category = None
    for capability in MARKET_CAPABILITIES:
        if tool_name in capability.get("methods", []):
            category = capability["category"]
            examples = capability.get("examples", [])
            break

    model_cls = TOOL_INPUT_MODELS.get(tool_name)
    validation_schema = _model_schema(model_cls) if model_cls else None

    return {
        "data": {
            "name": tool_name,
            "category": category,
            "source": getattr(fn, "__tool_source__", _infer_source(tool_name)),
            "doc": (fn.__doc__ or "").strip(),
            "parameters": parameters,
            "validation_schema": validation_schema,
            "examples": examples,
        }
    }


@mcp.tool()
@tool_endpoint(source="system")
async def help_tool(tool_name: str) -> Dict[str, Any]:
    """Alias for describe_tool(tool_name), useful for MCP clients that ask for 'help'."""
    return await describe_tool(tool_name)


@mcp.tool()
@tool_endpoint(source="system")
async def get_server_health() -> Dict[str, Any]:
    """Server operational health summary equivalent to /health."""
    ib_health = await ib_conn.check_health()
    ib_status = ib_health.get("status")
    status = "ok"
    if ib_status == "degraded":
        status = "degraded"
    if ib_status == "disconnected" and IB_ENABLED:
        status = "degraded"
    return {
        "data": {
            "status": status,
            "ib": ib_health,
            "runtime": {
                "transport": MCP_TRANSPORT,
                "ib_enabled": IB_ENABLED,
                "default_market": DEFAULT_MARKET,
                "market_timezone": DEFAULT_MARKET_TIMEZONE,
            },
            "circuit_breaker": CIRCUIT_BREAKER.snapshot(),
        }
    }


@mcp.tool()
@tool_endpoint(source="system")
async def get_server_metrics(output_format: str = "json") -> Dict[str, Any]:
    """Server metrics equivalent to /metrics (json or prometheus text)."""
    metrics_payload = {
        "requests_total": TOOL_METRICS["requests_total"],
        "failures_total": TOOL_METRICS["failures_total"],
        "latency_avg_ms": (
            TOOL_METRICS["latency_ms_total"] / TOOL_METRICS["requests_total"]
            if TOOL_METRICS["requests_total"]
            else 0.0
        ),
        "tool_calls": TOOL_METRICS["tool_calls"],
        "tool_failures": TOOL_METRICS["tool_failures"],
        "source_calls": TOOL_METRICS["source_calls"],
        "source_failures": TOOL_METRICS["source_failures"],
        "circuit_breaker": CIRCUIT_BREAKER.snapshot(),
        "connection": ib_conn.runtime_metrics(),
    }
    if output_format.lower() == "prometheus":
        return {"data": {"format": "prometheus", "payload": _prometheus_metrics()}}
    return {"data": {"format": "json", "payload": metrics_payload}}

# ============================================================================
# IBKR Tools (Real-time, Priority)
# ============================================================================

@mcp.tool()
@tool_endpoint()
@require_connection
async def get_stock_price(symbol: str, exchange: str = None, currency: str = 'USD') -> Dict[str, Any]:
    """
    Get real-time market price for a stock from Interactive Brokers.

    IMPORTANT: Use IB ticker format (no dots or suffixes).
    For fundamentals (PE, EPS) use get_fundamentals instead.

    Parameters:
        symbol: IB ticker (NO suffixes like .SA .ST .DE). Examples:
            - US: 'AAPL', 'MSFT', 'TSLA', 'AMZN'
            - Brazil: 'PETR4', 'VALE3', 'ITUB4'
            - Sweden: 'VOLVB', 'ERICB'
            - Germany: 'BMW', 'SAP'
        exchange: IB exchange code. Examples: 'SMART' (US default), 'BOVESPA' (Brazil), 'SFB' (Stockholm), 'IBIS' (Germany/Xetra), 'LSE' (London)
        currency: 'USD', 'BRL', 'SEK', 'EUR', 'GBP'

    Returns: {"success": true, "data": {"symbol": "AAPL", "exchange": "SMART", "currency": "USD", "price": 150.25, "close": 149.0}}

    Example: get_stock_price("AAPL") or get_stock_price("PETR4", "BOVESPA", "BRL")
    """
    return await MarketService.get_price(symbol, exchange, currency)


@mcp.tool()
@tool_endpoint()
@require_connection
async def get_historical_data(symbol: str, duration: str = "1 D", bar_size: str = "1 hour",
                              exchange: str = None, currency: str = "USD") -> Dict[str, Any]:
    """
    Get historical OHLCV bars from Interactive Brokers.

    Use this for chart data, technical analysis, or trend detection.
    Results are cached for 30 seconds to reduce API load.

    Parameters:
        symbol: IB ticker (no suffixes), e.g. 'AAPL', 'PETR4', 'VOLVB'
        duration: How far back. Options: '1 D', '1 W', '1 M', '3 M', '1 Y'
        bar_size: Bar granularity. Options: '1 min', '5 mins', '15 mins', '1 hour', '1 day'
        exchange: Optional IB exchange code for non-US symbols (e.g. BOVESPA, SFB)
        currency: Optional quote currency, e.g. USD, BRL, SEK

    Returns: {"success": true, "data": [{"date": "2024-01-15", "open": 150.0, "high": 155.0, "low": 149.0, "close": 153.0, "volume": 50000}]}

    Example: get_historical_data("AAPL", "1 M", "1 day")
    """
    _validate_historical_params(duration, bar_size)
    return await HistoryService.get_historical_data(symbol, duration, bar_size, exchange, currency)


@mcp.tool()
@tool_endpoint()
@require_connection
async def search_symbol(query: str) -> Dict[str, Any]:
    """
    Search for a stock contract on Interactive Brokers by name or symbol.

    Use this when you know the ticker but want to confirm it exists on IB,
    or to find the conId for further queries. For broader search by name/keyword,
    use yahoo_search instead.

    Parameters:
        query: Ticker symbol or company name, e.g. 'AAPL', 'PETR4', 'Volvo', 'Apple'

    Returns: {"success": true, "data": [{"symbol": "AAPL", "secType": "STK", "exchange": "NASDAQ", "conId": 265598}]}

    Example: search_symbol("AAPL")
    """
    return await MarketService.search_symbol(query)


@mcp.tool()
@tool_endpoint()
@require_connection
async def get_account_summary(masked: bool = True) -> Dict[str, Any]:
    """
    Get account summary with balances and margin from Interactive Brokers.

    Includes: NetLiquidation, BuyingPower, TotalCashValue, Margin Requirements,
    AvailableFunds, ExcessLiquidity, and Cushion.

    Parameters:
        masked: True by default. Returns bucketed/masked monetary values to avoid leaking sensitive balances.
                Set False only in trusted local environments.

    Returns: {"success": true, "data": {"NetLiquidation": {"value": "100000", "currency": "USD"}, "MaintMarginReq": {"value": "5000", "currency": "USD"}, ...}}

    Example: get_account_summary()
    """
    result = await AccountService.get_summary()
    if not result.get("success"):
        return result
    if not masked:
        return result

    data = result.get("data", {}) or {}
    masked: Dict[str, Any] = {}
    for key, payload in data.items():
        value = payload.get("value") if isinstance(payload, dict) else None
        currency = payload.get("currency") if isinstance(payload, dict) else None
        if value is None:
            masked[key] = payload
            continue
        try:
            numeric = float(value)
            masked[key] = {
                "value": round(numeric, 2),
                "masked_value": f"{int(round(numeric / 1000.0) * 1000)}+",
                "currency": currency,
            }
        except Exception:
            masked[key] = {"value": value, "currency": currency}
    return {"success": True, "data": masked, "meta": {"masked": True}}


@mcp.tool()
@tool_endpoint()
@require_connection
async def get_option_chain(symbol: str) -> Dict[str, Any]:
    """
    Get available option strikes and expirations for a stock from Interactive Brokers.

    Use this FIRST to discover available options before calling get_option_greeks.

    Parameters:
        symbol: Underlying IB ticker (no suffixes), e.g. 'AAPL', 'PETR4'

    Returns: {"success": true, "data": {"underlying": "AAPL", "multiplier": "100", "expirations": ["20240119", "20240216"], "strikes": [140.0, 145.0, 150.0]}}

    Example: get_option_chain("AAPL")
    """
    return await OptionService.get_option_chain(symbol)


@mcp.tool()
@tool_endpoint()
@require_connection
async def get_option_greeks(symbol: str, last_trade_date: str, strike: float, right: str) -> Dict[str, Any]:
    """
    Get Greeks (delta, gamma, theta, vega) and market data for a specific option from Interactive Brokers.

    Call get_option_chain first to find valid expirations and strikes.

    Parameters:
        symbol: Underlying IB ticker (no suffixes), e.g. 'AAPL'
        last_trade_date: Expiration in format 'YYYYMMDD', e.g. '20240119'
        strike: Strike price, e.g. 150.0
        right: 'C' for Call, 'P' for Put

    Returns: {"success": true, "data": {"delta": 0.55, "gamma": 0.03, "theta": -0.05, "vega": 0.15, "impliedVol": 0.25, "bid": 3.50, "ask": 3.80}}

    Example: get_option_greeks("AAPL", "20240119", 150.0, "C")
    """
    _validate_option_greeks_params(last_trade_date, right)
    return await OptionService.get_option_greeks(symbol, last_trade_date, strike, right.upper())


# ============================================================================
# Yahoo Finance Tools (Fundamentals, Complementary Data)
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def get_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    Get fundamental analysis data from Yahoo Finance: PE ratio, EPS, market cap, revenue, margins, and more.

    Use this for valuation analysis. Does NOT require IB connection.

    Parameters:
        symbol: Yahoo Finance ticker. For international stocks use suffix: 'AAPL' (US), 'PETR4.SA' (Brazil), 'VOLV-B.ST' (Sweden), 'BMW.DE' (Germany)

    Returns: {"success": true, "data": {"symbol": "AAPL", "marketCap": 3000000000000, "trailingPE": 28.5, "trailingEps": 6.42, "revenue": 383000000000, ...}}

    Example: get_fundamentals("AAPL")
    """
    return YahooService.get_fundamentals(symbol)


@mcp.tool()
@tool_endpoint()
async def get_dividends(symbol: str) -> Dict[str, Any]:
    """
    Get dividend information from Yahoo Finance: yield, rate, payout ratio, and payment history.

    Use this to analyze income potential of a stock.

    Parameters:
        symbol: Yahoo Finance ticker. Use suffix for international: 'AAPL', 'PETR4.SA', 'VOLV-B.ST'

    Returns: {"success": true, "data": {"dividendYield": 0.005, "dividendRate": 0.96, "payoutRatio": 0.15, "history": [{"date": "2024-01-10", "amount": 0.24}]}}

    Example: get_dividends("KO")
    """
    return YahooService.get_dividends(symbol)


@mcp.tool()
@tool_endpoint()
async def get_company_info(symbol: str) -> Dict[str, Any]:
    """
    Get company profile from local database cache: sector, industry, description, employees, website.

    Use this to understand what a company does before analyzing its stock.

    Parameters:
        symbol: Yahoo Finance ticker. Use suffix for international: 'AAPL', 'PETR4.SA', 'VOLV-B.ST'

    Returns: {"success": true, "data": {"shortName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics", "longBusinessSummary": "...", ...}}

    Example: get_company_info("AAPL")
    """
    return YahooService.get_company_info(symbol)


@mcp.tool()
@tool_endpoint()
async def get_financial_statements(symbol: str, statement_type: str = "all") -> Dict[str, Any]:
    """
    Get cached financial statements (Income Statement, Balance Sheet, Cash Flow) from local database.

    Data is loaded by ETL (Load Market Intelligence) and served locally at runtime.

    Parameters:
        symbol: Yahoo Finance ticker. Use suffix for international: 'AAPL', 'PETR4.SA'
        statement_type: 'all', 'income', 'balance', 'cashflow',
                        'quarterly_income', 'quarterly_balance', 'quarterly_cashflow'

    Returns: cached statements from local database snapshot.

    Example: get_financial_statements("MSFT", "all")
    """
    return MarketIntelligenceService.get_financial_statements(symbol, statement_type)


@mcp.tool()
@tool_endpoint()
async def get_exchange_info(symbol: str) -> Dict[str, Any]:
    """
    Get exchange information for a ticker from Yahoo Finance: timezone, market hours, market state.

    Use this to check if a market is open, what timezone it operates in, etc.

    Parameters:
        symbol: Yahoo Finance ticker, e.g. 'AAPL' for NASDAQ, 'VOW3.DE' for Frankfurt

    Returns: {"success": true, "data": {"exchange": "NMS", "exchangeTimezoneName": "America/New_York", "marketState": "REGULAR"}}

    Example: get_exchange_info("AAPL")
    """
    return YahooService.get_exchange_info(symbol)


@mcp.tool()
@tool_endpoint()
async def yahoo_search(query: str) -> Dict[str, Any]:
    """
    Search for tickers by company name, sector, or keyword using Yahoo Finance.

    Use this for DISCOVERY: finding tickers you don't know yet.
    For confirming a known ticker on IB, use search_symbol instead.

    Parameters:
        query: Company name or keyword, e.g. 'Tesla', 'Brazilian banks', 'semiconductor'

    Returns: {"success": true, "data": [{"symbol": "TSLA", "shortname": "Tesla, Inc.", "exchange": "NMS", "quoteType": "EQUITY"}]}

    Example: yahoo_search("Tesla")
    """
    return YahooService.search_tickers(query)


@mcp.tool()
@tool_endpoint()
async def get_comprehensive_stock_info(symbol: str) -> Dict[str, Any]:
    """
    Get comprehensive stock information from local cached tables/snapshots.

    Includes company profile, market data, fundamentals, dividends, earnings
    and analyst target/recommendation context.
    """
    return MarketIntelligenceService.get_comprehensive_stock_info(symbol)


@mcp.tool()
@tool_endpoint()
async def get_historical_data_cached(symbol: str, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
    """
    Get cached historical price data from local database.
    Supports intervals: 1d, 1wk, 1mo.
    """
    return MarketIntelligenceService.get_historical_data_cached(symbol, period, interval)


@mcp.tool()
@tool_endpoint()
async def get_options_data(symbol: str, expiration_date: str = None) -> Dict[str, Any]:
    """
    Get local cached options chain grouped by expiration date.
    """
    return MarketIntelligenceService.get_options_data(symbol, expiration_date)


@mcp.tool()
@tool_endpoint()
async def get_institutional_holders(symbol: str, limit: int = 50) -> Dict[str, Any]:
    """
    Get local cached institutional and major holder data.
    """
    return MarketIntelligenceService.get_institutional_holders(symbol, limit)


@mcp.tool()
@tool_endpoint()
async def get_analyst_recommendations(symbol: str, limit: int = 50) -> Dict[str, Any]:
    """
    Get local cached analyst recommendations and upgrades/downgrades.
    """
    return MarketIntelligenceService.get_analyst_recommendations(symbol, limit)


@mcp.tool()
@tool_endpoint()
async def get_news(symbol: str, limit: int = 10) -> Dict[str, Any]:
    """
    Get local cached news headlines for a stock.
    """
    return MarketIntelligenceService.get_news(symbol, limit)


@mcp.tool()
@tool_endpoint()
async def get_technical_analysis(symbol: str, period: str = "1y") -> Dict[str, Any]:
    """
    Get local technical analysis (SMA/EMA/RSI/MACD/Bollinger/volume/support-resistance).
    """
    return MarketIntelligenceService.get_technical_analysis(symbol, period)


@mcp.tool()
@tool_endpoint()
async def get_sector_performance(symbols: List[str]) -> Dict[str, Any]:
    """
    Compare local performance metrics across a list of symbols.
    """
    return MarketIntelligenceService.get_sector_performance(symbols)


@mcp.tool()
@tool_endpoint()
async def get_dividend_history(symbol: str, period: str = "2y") -> Dict[str, Any]:
    """
    Get local dividend history with summary metrics for a period.
    """
    return MarketIntelligenceService.get_dividend_history(symbol, period)


# ============================================================================
# Stock Screener Tools
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def get_stock_screener(market: str = "sweden", sector: str = None,
                             sort_by: str = "perf_1d", limit: int = 50) -> Dict[str, Any]:
    """
    Stock screener with filters and technical indicators.
    Returns sorted list of stocks with performance, RSI, MACD, volume, etc.

    Parameters:
        market: Market filter. Options: 'brazil', 'sweden', 'usa', 'all'
        sector: Sector filter. Examples: 'Technology', 'Financials', 'Energy'
        sort_by: Sort column. Options: 'perf_1d', 'perf_1w', 'perf_1m', 'perf_1y', 'rsi', 'volume', 'volatility'
        limit: Max results (default 50)

    Example: get_stock_screener("brazil", sector="Financials", sort_by="perf_1d")
    """
    return ScreenerService.get_stock_screener(market, sector, sort_by, limit)


@mcp.tool()
@tool_endpoint()
async def get_top_gainers(market: str = "sweden", period: str = "1D", limit: int = 10) -> Dict[str, Any]:
    """
    Get top performing stocks (biggest gains) by market and period.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        period: '1D' (day), '1W' (week), '1M' (month)
        limit: Number of results (default 10)

    Example: get_top_gainers("brazil", "1D") → "Maiores altas do dia no Brasil"
    """
    return ScreenerService.get_top_movers(market, period, "top_gainers", limit)


@mcp.tool()
@tool_endpoint()
async def get_top_losers(market: str = "sweden", period: str = "1D", limit: int = 10) -> Dict[str, Any]:
    """
    Get worst performing stocks (biggest drops) by market and period.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        period: '1D' (day), '1W' (week), '1M' (month)
        limit: Number of results (default 10)

    Example: get_top_losers("sweden", "1W") → "Maiores baixas da semana na Suécia"
    """
    return ScreenerService.get_top_movers(market, period, "top_losers", limit)


@mcp.tool()
@tool_endpoint()
async def get_top_dividend_payers(market: str = "sweden", sector: str = None,
                                  limit: int = 10) -> Dict[str, Any]:
    """
    Get stocks with highest dividend yields.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        sector: Optional sector filter (e.g. 'Financials', 'Energy')
        limit: Number of results (default 10)

    Example: get_top_dividend_payers("sweden", sector="Financials") → "Top dividendos bancários da Suécia"
    """
    return ScreenerService.get_top_dividend_payers(market, sector, limit)


@mcp.tool()
@tool_endpoint()
async def get_technical_signals(market: str = "sweden", signal_type: str = "oversold",
                                limit: int = 20) -> Dict[str, Any]:
    """
    Find stocks with specific technical signals.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        signal_type: Signal to detect:
            - 'oversold': RSI < 30 (potential buy)
            - 'overbought': RSI > 70 (potential sell)
            - 'golden_cross': EMA20 > SMA200 (bullish)
            - 'death_cross': EMA20 < SMA200 (bearish)
            - 'high_volume': Volume 2x above average
            - 'near_52w_high': Within 5% of 52-week high
            - 'near_52w_low': Within 5% of 52-week low

    Example: get_technical_signals("brazil", "oversold")
    """
    return ScreenerService.get_technical_signals(market, signal_type, limit)


@mcp.tool()
@tool_endpoint()
async def get_highest_rsi(market: str = "sweden", limit: int = 10) -> Dict[str, Any]:
    """
    Get stocks with highest RSI values for the latest available metrics date.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        limit: Number of results (default 10)
    """
    return ScreenerService.get_rsi_leaders(market=market, direction="high", limit=limit)


@mcp.tool()
@tool_endpoint()
async def get_lowest_rsi(market: str = "sweden", limit: int = 10) -> Dict[str, Any]:
    """
    Get stocks with lowest RSI values for the latest available metrics date.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        limit: Number of results (default 10)
    """
    return ScreenerService.get_rsi_leaders(market=market, direction="low", limit=limit)


@mcp.tool()
@tool_endpoint()
async def get_most_active_stocks(market: str = "sweden", period: str = "1D", limit: int = 10) -> Dict[str, Any]:
    """
    Get most active stocks by market mover cache.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        period: '1D', '1W', '1M'
        limit: Number of results (default 10)
    """
    return ScreenerService.get_top_movers(market, period, "most_active", limit)


@mcp.tool()
@tool_endpoint()
async def get_fundamental_rankings(market: str = "sweden", metric: str = "market_cap",
                                   limit: int = 10, sector: str = None) -> Dict[str, Any]:
    """
    Rank stocks using latest fundamentals by metric.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        metric: 'market_cap', 'trailing_pe', 'forward_pe', 'roe', 'net_margin',
                'revenue', 'free_cash_flow', 'debt_to_equity'
        limit: Number of results (default 10)
        sector: Optional sector filter
    """
    return ScreenerService.get_fundamental_leaders(market=market, metric=metric, limit=limit, sector=sector)


# ============================================================================
# Classification & Company Profile Tools
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def get_companies_by_sector(market: str = "sweden", sector: str = None, industry: str = None,
                                  subindustry: str = None, limit: int = 50) -> Dict[str, Any]:
    """
    List companies by normalized sector/industry/subindustry.

    Parameters:
        market: 'brazil', 'sweden', 'usa', 'all'
        sector: Optional sector name filter (e.g. 'Financials')
        industry: Optional industry filter (e.g. 'Banking')
        subindustry: Optional subindustry filter
        limit: Max rows (default 50)
    """
    return ClassificationService.get_companies_by_sector(
        market=market, sector=sector, industry=industry, subindustry=subindustry, limit=limit
    )


@mcp.tool()
@tool_endpoint()
async def get_company_core_business(symbol: str) -> Dict[str, Any]:
    """
    Return enriched company profile with 'core business' summary.

    Parameters:
        symbol: Ticker symbol, e.g. 'VOLV-B.ST', 'AAPL', 'PETR4.SA'
    """
    return ClassificationService.get_company_core_business(symbol)


@mcp.tool()
@tool_endpoint()
async def get_earnings_events(symbol: str = None, market: str = "sweden",
                              upcoming_only: bool = False, limit: int = 20) -> Dict[str, Any]:
    """
    Get curated earnings events from normalized earnings pipeline.

    Parameters:
        symbol: Optional symbol filter
        market: 'brazil', 'sweden', 'usa', 'all'
        upcoming_only: If true, only upcoming events
        limit: Max rows (default 20)
    """
    return ClassificationService.get_earnings_events(
        symbol=symbol, market=market, upcoming_only=upcoming_only, limit=limit
    )


# ============================================================================
# Option Screener Tools
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def get_option_screener(symbol: str = None, expiry: str = None, 
                             right: str = None, min_delta: float = None, 
                             max_delta: float = None, min_iv: float = None,
                             max_iv: float = None, has_liquidity: bool = True,
                             limit: int = 50) -> Dict[str, Any]:
    """
    Options screener with Greeks (delta, gamma, theta, vega) and IV.
    Filters by symbol, expiry, delta range, IV range, and liquidity.

    Notes:
    - Expiries are limited to 5 weeks from now in the background jobs.
    - 'has_liquidity' filters for options with active bid/ask.

    Parameters:
        symbol: Underlying symbol (e.g. 'PETR4', 'AAPL')
        expiry: Specific expiry date (YYYY-MM-DD)
        right: 'CALL' or 'PUT'
        min_delta/max_delta: Filter by delta range (e.g. 0.2 to 0.5)
        min_iv/max_iv: Filter by Implied Volatility range
        has_liquidity: Filter for options with active quotes
        limit: Max results (default 50)
    """
    _validate_option_screener_params(right, limit)
    normalized_right = right.upper() if right else None
    if normalized_right == "CALL":
        normalized_right = "C"
    if normalized_right == "PUT":
        normalized_right = "P"

    return OptionScreenerService.get_option_screener(
        symbol, expiry, normalized_right, min_delta, max_delta, min_iv, max_iv, has_liquidity, limit
    )


@mcp.tool()
@tool_endpoint()
async def get_option_chain_snapshot(symbol: str, expiry: str = None) -> Dict[str, Any]:
    """
    Get the latest cached option chain for a symbol and optional expiry.
    Returns bid, ask, last, delta, and IV for all strikes.

    Parameters:
        symbol: Underlying symbol
        expiry: Optional expiry date (YYYY-MM-DD)
    """
    return OptionScreenerService.get_option_chain_snapshot(symbol, expiry)


# ============================================================================
# Wheel Strategy Tools (Sweden-first defaults)
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def get_wheel_put_candidates(symbol: str, market: str = "sweden",
                                   delta_min: float = 0.25, delta_max: float = 0.35,
                                   dte_min: int = 4, dte_max: int = 10,
                                   limit: int = 5, require_liquidity: bool = True) -> Dict[str, Any]:
    """
    Select candidate PUTs to start the Wheel strategy.

    Parameters:
        symbol: Underlying symbol or company name (e.g. 'Nordea', 'NDA-SE.ST')
        market: Default 'sweden'
        delta_min/delta_max: Typical Wheel range 0.25-0.35
        dte_min/dte_max: Near-term expiry window (default weekly range)
        limit: Max candidates
        require_liquidity: Require positive bid+ask
    """
    return WheelService.select_put_for_wheel(
        symbol=symbol, market=market, delta_min=delta_min, delta_max=delta_max,
        dte_min=dte_min, dte_max=dte_max, limit=limit, require_liquidity=require_liquidity
    )


@mcp.tool()
@tool_endpoint()
async def get_wheel_put_annualized_return(symbol: str, market: str = "sweden",
                                          target_dte: int = 7) -> Dict[str, Any]:
    """
    Compute annualized return for an ATM PUT candidate.

    Formula:
    - period_return_% = premium / strike
    - annualized_% = period_return_% * (365 / DTE)
    """
    return WheelService.get_atm_put_annualized_return(
        symbol=symbol, market=market, target_dte=target_dte
    )


@mcp.tool()
@tool_endpoint()
async def get_wheel_contract_capacity(symbol: str, capital_sek: float, market: str = "sweden",
                                      strike: float = None, margin_requirement_pct: float = 1.0,
                                      cash_buffer_pct: float = 0.0, target_dte: int = 7) -> Dict[str, Any]:
    """
    Estimate how many Wheel PUT contracts can be sold with available capital.

    Formula:
    contracts = floor((capital * (1-cash_buffer_pct)) / (strike * 100 * margin_requirement_pct))
    """
    return WheelService.get_wheel_contract_capacity(
        symbol=symbol,
        capital_sek=capital_sek,
        market=market,
        strike=strike,
        margin_requirement_pct=margin_requirement_pct,
        cash_buffer_pct=cash_buffer_pct,
        target_dte=target_dte,
    )


@mcp.tool()
@tool_endpoint()
async def analyze_wheel_put_risk(symbol: str, market: str = "sweden",
                                 pct_below_spot: float = 5.0, target_dte: int = 7) -> Dict[str, Any]:
    """
    Analyze risk for selling a PUT below spot.
    Includes delta-based assignment probability proxy, break-even, and exposure.
    """
    return WheelService.analyze_put_risk(
        symbol=symbol, market=market, pct_below_spot=pct_below_spot, target_dte=target_dte
    )


@mcp.tool()
@tool_endpoint()
async def get_wheel_assignment_plan(symbol: str, assignment_strike: float, premium_received: float,
                                    market: str = "sweden") -> Dict[str, Any]:
    """
    Evaluate assignment scenario and next Wheel step.
    Returns net cost basis and covered-call continuation plan.
    """
    return WheelService.evaluate_assignment(
        symbol=symbol,
        assignment_strike=assignment_strike,
        premium_received=premium_received,
        market=market,
    )


@mcp.tool()
@tool_endpoint()
async def get_wheel_covered_call_candidates(symbol: str, average_cost: float, market: str = "sweden",
                                            delta_min: float = 0.25, delta_max: float = 0.35,
                                            dte_min: int = 4, dte_max: int = 21,
                                            min_upside_pct: float = 1.0, limit: int = 5) -> Dict[str, Any]:
    """
    Suggest covered CALLs after assignment to continue the Wheel.
    Filters strike above average cost and target delta window.
    """
    return WheelService.suggest_covered_call_after_assignment(
        symbol=symbol,
        average_cost=average_cost,
        market=market,
        delta_min=delta_min,
        delta_max=delta_max,
        dte_min=dte_min,
        dte_max=dte_max,
        min_upside_pct=min_upside_pct,
        limit=limit,
    )


@mcp.tool()
@tool_endpoint()
async def compare_wheel_premiums(symbol_a: str, symbol_b: str, market: str = "sweden",
                                 delta_min: float = 0.25, delta_max: float = 0.35,
                                 dte_min: int = 4, dte_max: int = 10) -> Dict[str, Any]:
    """
    Compare Wheel PUT premiums between two symbols normalized by capital usage.
    """
    return WheelService.compare_wheel_put_premiums(
        symbol_a=symbol_a,
        symbol_b=symbol_b,
        market=market,
        delta_min=delta_min,
        delta_max=delta_max,
        dte_min=dte_min,
        dte_max=dte_max,
    )


@mcp.tool()
@tool_endpoint()
async def evaluate_wheel_iv(symbol: str, market: str = "sweden", lookback_days: int = 90,
                            high_iv_threshold_percentile: float = 70.0, target_dte: int = 7) -> Dict[str, Any]:
    """
    Evaluate if current IV is rich enough to justify starting Wheel.
    Uses historical IV snapshots from local DB (does not infer missing history).
    """
    return WheelService.evaluate_iv_regime_for_wheel(
        symbol=symbol,
        market=market,
        lookback_days=lookback_days,
        high_iv_threshold_percentile=high_iv_threshold_percentile,
        target_dte=target_dte,
    )


@mcp.tool()
@tool_endpoint()
async def simulate_wheel_drawdown(symbol: str, strike: float, premium_received: float,
                                  drop_percent: float = 10.0, market: str = "sweden") -> Dict[str, Any]:
    """
    Simulate drawdown scenario after selling a PUT if underlying drops by X%.
    """
    return WheelService.simulate_wheel_drawdown(
        symbol=symbol,
        strike=strike,
        premium_received=premium_received,
        drop_percent=drop_percent,
        market=market,
    )


@mcp.tool()
@tool_endpoint()
async def compare_wheel_start_timing(symbol: str, market: str = "sweden",
                                     wait_drop_percent: float = 3.0,
                                     delta_min: float = 0.25, delta_max: float = 0.35,
                                     dte_min: int = 4, dte_max: int = 10) -> Dict[str, Any]:
    """
    Scenario comparison: start Wheel now vs wait for a pullback.
    Returns a no-forecast, uncertainty-aware comparison.
    """
    return WheelService.compare_wheel_start_now_vs_wait(
        symbol=symbol,
        market=market,
        wait_drop_percent=wait_drop_percent,
        delta_min=delta_min,
        delta_max=delta_max,
        dte_min=dte_min,
        dte_max=dte_max,
    )


@mcp.tool()
@tool_endpoint()
async def build_wheel_multi_stock_plan(capital_sek: float, symbols: List[str] = None,
                                       market: str = "sweden",
                                       delta_min: float = 0.25, delta_max: float = 0.35,
                                       dte_min: int = 4, dte_max: int = 10,
                                       margin_requirement_pct: float = 1.0,
                                       cash_buffer_pct: float = 0.10) -> Dict[str, Any]:
    """
    Build a multi-stock Wheel plan (capital split) for Swedish names by default.
    """
    return WheelService.build_multi_stock_wheel_plan(
        capital_sek=capital_sek,
        symbols=symbols,
        market=market,
        delta_min=delta_min,
        delta_max=delta_max,
        dte_min=dte_min,
        dte_max=dte_max,
        margin_requirement_pct=margin_requirement_pct,
        cash_buffer_pct=cash_buffer_pct,
    )


@mcp.tool()
@tool_endpoint()
async def stress_test_wheel_portfolio(capital_sek: float, sector_drop_percent: float = 20.0,
                                      symbols: List[str] = None, market: str = "sweden",
                                      delta_min: float = 0.25, delta_max: float = 0.35,
                                      dte_min: int = 4, dte_max: int = 10) -> Dict[str, Any]:
    """
    Stress-test Wheel portfolio under a sector-wide drop scenario.
    """
    return WheelService.stress_test_wheel_portfolio(
        capital_sek=capital_sek,
        sector_drop_percent=sector_drop_percent,
        symbols=symbols,
        market=market,
        delta_min=delta_min,
        delta_max=delta_max,
        dte_min=dte_min,
        dte_max=dte_max,
    )


# ============================================================================
# Event Calendar Tools (LLM-ready normalized events)
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def get_event_calendar(market: str = "sweden", category: str = None, event_type: str = None,
                             ticker: str = None, start_date: str = None, end_date: str = None,
                             min_volatility_impact: str = "low", limit: int = 50) -> Dict[str, Any]:
    """
    Get normalized event calendar with filters.
    Categories: corporate, macro, monetary_policy, geopolitical, market_structure
    """
    return EventService.get_event_calendar(
        market=market,
        category=category,
        event_type=event_type,
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        min_volatility_impact=min_volatility_impact,
        limit=limit,
    )


@mcp.tool()
@tool_endpoint()
async def get_corporate_events(market: str = "sweden", ticker: str = None,
                               start_date: str = None, end_date: str = None,
                               min_volatility_impact: str = "low", limit: int = 50) -> Dict[str, Any]:
    """Corporate events affecting single names (earnings, dividends, splits, guidance, M&A, etc)."""
    return EventService.get_events_by_category(
        category="corporate",
        market=market,
        ticker=ticker,
        start_date=start_date,
        end_date=end_date,
        min_volatility_impact=min_volatility_impact,
        limit=limit,
    )


@mcp.tool()
@tool_endpoint()
async def get_macro_events(market: str = "sweden", start_date: str = None, end_date: str = None,
                           min_volatility_impact: str = "low", limit: int = 50) -> Dict[str, Any]:
    """Macro calendar events (CPI, PPI, GDP, unemployment, PMI, etc)."""
    return EventService.get_events_by_category(
        category="macro",
        market=market,
        start_date=start_date,
        end_date=end_date,
        min_volatility_impact=min_volatility_impact,
        limit=limit,
    )


@mcp.tool()
@tool_endpoint()
async def get_monetary_policy_events(market: str = "sweden", start_date: str = None, end_date: str = None,
                                     min_volatility_impact: str = "low", limit: int = 50) -> Dict[str, Any]:
    """Central bank policy events (FOMC/ECB/Riksbank meetings, rate decisions, minutes)."""
    return EventService.get_events_by_category(
        category="monetary_policy",
        market=market,
        start_date=start_date,
        end_date=end_date,
        min_volatility_impact=min_volatility_impact,
        limit=limit,
    )


@mcp.tool()
@tool_endpoint()
async def get_geopolitical_events(market: str = "sweden", start_date: str = None, end_date: str = None,
                                  min_volatility_impact: str = "low", limit: int = 50) -> Dict[str, Any]:
    """Geopolitical events (sanctions, elections, energy crisis, OPEC, etc)."""
    return EventService.get_events_by_category(
        category="geopolitical",
        market=market,
        start_date=start_date,
        end_date=end_date,
        min_volatility_impact=min_volatility_impact,
        limit=limit,
    )


@mcp.tool()
@tool_endpoint()
async def get_market_structure_events(market: str = "sweden", start_date: str = None, end_date: str = None,
                                      min_volatility_impact: str = "low", limit: int = 50) -> Dict[str, Any]:
    """Market structure events (index rebalance, option expiration, triple witching, ETF rebalance)."""
    return EventService.get_events_by_category(
        category="market_structure",
        market=market,
        start_date=start_date,
        end_date=end_date,
        min_volatility_impact=min_volatility_impact,
        limit=limit,
    )


@mcp.tool()
@tool_endpoint()
async def get_wheel_event_risk_window(ticker: str, market: str = "sweden",
                                      days_ahead: int = 14, limit: int = 100) -> Dict[str, Any]:
    """
    Event risk window for Wheel strategy decisions.
    Returns upcoming events sorted by wheel_risk_score.
    """
    return EventService.get_wheel_event_risk_window(
        ticker=ticker, market=market, days_ahead=days_ahead, limit=limit
    )


# ============================================================================
# Job Management Tools (LLM can manage data pipeline)
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def list_jobs() -> Dict[str, Any]:
    """
    List all data loader jobs with their schedule, status, and last run info.
    Use this to understand what data pipelines exist and their health.

    Returns: List of jobs with name, cron schedule, active status, and last run details.
    """
    return JobService.list_jobs()


@mcp.tool()
@tool_endpoint()
async def get_job_logs(job_name: str, limit: int = 5) -> Dict[str, Any]:
    """
    Get recent execution logs for a specific data loader job.
    Useful for debugging failures or checking data freshness.

    Parameters:
        job_name: Full or partial job name (e.g. 'Yahoo Prices', 'Stock Metrics')
        limit: Number of recent runs to return (default 5)

    Example: get_job_logs("Yahoo Prices") → last 5 runs with stdout/stderr
    """
    return JobService.get_job_logs(job_name, limit)


@mcp.tool()
@tool_endpoint()
async def trigger_job(job_name: str) -> Dict[str, Any]:
    """
    Manually trigger a data loader job to run immediately.
    Use this when data seems stale or you need fresh data.

    Parameters:
        job_name: Full or partial job name (e.g. 'Calculate Stock Metrics')

    Example: trigger_job("Extract Yahoo Prices") → runs the price extractor now
    """
    return await JobService.trigger_job(job_name)


@mcp.tool()
@tool_endpoint()
async def toggle_job(job_name: str, active: bool) -> Dict[str, Any]:
    """
    Enable or disable a scheduled job.

    Parameters:
        job_name: Full or partial job name
        active: True to enable, False to disable

    Example: toggle_job("Extract IBKR Prices", false) → disables IBKR extraction
    """
    return JobService.toggle_job(job_name, active)


@mcp.tool()
@tool_endpoint()
async def get_job_status() -> Dict[str, Any]:
    """
    Get health overview of all data pipeline jobs.
    Shows total, healthy, warning, and error counts plus per-job details.

    Returns: Summary with counts + list of all jobs with last run status.
    """
    return JobService.get_job_status()


@mcp.tool()
@tool_endpoint()
async def run_pipeline_health_check() -> Dict[str, Any]:
    """
    Trigger a lightweight health check across all data loader jobs.
    Each job script is executed in 'test' mode (limiting symbols) 
    to verify connectivity, authentication and basic parsing.

    Use this when you want to verify that the whole pipeline is functional.
    """
    return await JobService.run_pipeline_health_check()


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("finance://status")
async def resource_status() -> Dict[str, Any]:
    """Get the current connection status, health, and server time from IB Gateway."""
    return await ib_conn.check_health()


@mcp.resource("finance://health")
async def resource_health() -> Dict[str, Any]:
    """MCP resource equivalent of /health for external clients."""
    health = await get_server_health()
    return health.get("data", health)


@mcp.resource("finance://metrics")
async def resource_metrics() -> Dict[str, Any]:
    """MCP resource equivalent of /metrics (JSON payload)."""
    metrics = await get_server_metrics("json")
    return metrics.get("data", metrics)


@mcp.resource("finance://account/summary")
@require_connection
async def resource_account_summary() -> Dict[str, Any]:
    """Get account summary with masked values by default."""
    response = await get_account_summary(masked=True)
    return response.get("data", response)


@mcp.resource("finance://portfolio/positions")
@require_connection
async def resource_portfolio_positions() -> Dict[str, Any]:
    """Get current portfolio positions with cost basis."""
    return await AccountService.get_positions()


@mcp.resource("finance://market/ticker/{symbol}")
@require_connection
async def resource_market_ticker(symbol: str) -> Dict[str, Any]:
    """Get a real-time market snapshot for a symbol."""
    return await MarketService.get_price(symbol)


# ============================================================================
# Prompts
# ============================================================================

@mcp.prompt()
def ibkr_guide() -> str:
    """Essential guide about Interactive Brokers API. READ THIS FIRST before using any IB tools."""
    return """## Interactive Brokers (IBKR) — Guide for LLM

### 1. Ticker Format (CRITICAL)
IB uses its OWN ticker format. NEVER send Yahoo/Bloomberg suffixes (.SA, .ST, .DE, .L, etc.) to IB tools.

| What the user says | IB Ticker | Exchange | Currency |
|---------------------|-----------|----------|----------|
| Petrobras / PETR4 | PETR4 | BOVESPA | BRL |
| Volvo B / VOLV-B | VOLVB | SFB | SEK |
| BMW | BMW | IBIS | EUR |
| Apple / AAPL | AAPL | SMART | USD |
| Shell / SHEL | SHEL | LSE | GBP |
| LVMH / MC | MC | SBF | EUR |
| Toyota / 7203 | 7203 | TSE | JPY |

Rules:
- Remove dots and everything after them (PETR4.SA → PETR4)
- Remove dashes (VOLV-B → VOLVB)
- Always pass exchange and currency for non-US stocks

### 2. Exchange Codes
| Country | IB Exchange | Currency |
|---------|------------|----------|
| US | SMART | USD |
| Brazil | BOVESPA | BRL |
| Sweden | SFB | SEK |
| Germany | IBIS | EUR |
| UK | LSE | GBP |
| France | SBF | EUR |
| Japan | TSE | JPY |
| Hong Kong | SEHK | HKD |
| Australia | ASX | AUD |
| Canada | TSE | CAD |
| Italy | BVME | EUR |
| Netherlands | AEB | EUR |
| Norway | OSE | NOK |
| Denmark | CSE | DKK |

### 3. Market Hours (UTC)
- US (NYSE/NASDAQ): 14:30–21:00
- Brazil (BOVESPA): 14:00–21:00
- Europe (LSE/IBIS/SFB): 08:00–16:30
- Japan (TSE): 00:00–06:00
- Hong Kong (SEHK): 01:30–08:00
Outside these hours, bid/ask/price may be null. The 'close' field shows the last trading day's close.

### 4. Data Limitations
- Prices require market data subscription per exchange (paid separately in IB account)
- If price/bid/ask/close are all null → User likely has no market data subscription for that exchange
- Delayed data (15 min) may be available depending on subscription

### 5. Read-Only Mode
This server runs in READ-ONLY mode. You CANNOT place orders, modify positions, or execute trades.
Available actions: view prices, historical data, account summary, portfolio positions, options data.

### 6. Recommended Workflow
1. If user asks about a stock, first determine the IB ticker + exchange
2. Use search_symbol("company name") if unsure about the IB ticker
3. For price: get_stock_price("TICKER", "EXCHANGE", "CURRENCY")
4. For fundamentals/info: use Yahoo tools with Yahoo format (PETR4.SA, VOLV-B.ST)
5. Combine data from both sources for complete analysis

### 7. Yahoo vs IB — When to use which
| Need | Tool | Format |
|------|------|--------|
| Live price, bid/ask | get_stock_price (IB) | PETR4 |
| PE, EPS, margins | get_fundamentals (Yahoo) | PETR4.SA |
| Company profile | get_company_info (Yahoo) | PETR4.SA |
| Dividends | get_dividends (Yahoo) | PETR4.SA |
| Historical bars | get_historical_data (IB) | PETR4 |
| Options | get_option_chain (IB) | PETR4 |
| Account/Portfolio | get_account_summary (IB) | — |
"""

@mcp.prompt()
def analyze_ticker(symbol: str) -> str:
    """Comprehensive stock analysis prompt. Combines real-time IB data with Yahoo fundamentals."""
    return f"""Please perform a comprehensive analysis of {symbol}:

1. **Current Price** — use get_stock_price("{symbol}")
2. **Company Profile** — use get_company_info("{symbol}")
3. **Fundamentals** — use get_fundamentals("{symbol}")
4. **Dividends** — use get_dividends("{symbol}")
5. **Historical Trend** — use get_historical_data("{symbol}", "3 M", "1 day")
6. **Options Activity** (optional) — use get_option_chain("{symbol}")

Based on this data, provide:
- Current trend analysis
- Valuation assessment (PE, PEG, Price-to-Book)
- Dividend sustainability
- Risk factors
- Overall recommendation
"""


@mcp.prompt()
def portfolio_review() -> str:
    """Portfolio review prompt using account data and positions."""
    return """Please review my portfolio:

1. **Account Summary** — use get_account_summary()
2. **Positions** — read resource finance://portfolio/positions

Analyze:
- Total exposure and margin utilization
- Position concentration risk
- Sector diversification (use get_company_info for each position)
- Suggestions for rebalancing (hypothetical, read-only mode)
"""


@mcp.prompt()
def ticker_format_guide() -> str:
    """Guide on how to format stock tickers. IMPORTANT: IB tools and Yahoo tools use DIFFERENT formats."""
    return """## Ticker Format Guide

IMPORTANT: IB tools and Yahoo tools use DIFFERENT ticker formats!

### IB Tools (get_stock_price, search_symbol, get_historical_data, get_option_chain, get_option_greeks)
Use clean IB tickers WITHOUT dots or suffixes:
| Market | Ticker | Exchange | Currency |
|--------|--------|----------|----------|
| US | AAPL | SMART | USD |
| Brazil | PETR4 | BOVESPA | BRL |
| Sweden | VOLVB | SFB | SEK |
| Germany | BMW | IBIS | EUR |
| UK | SHEL | LSE | GBP |
| France | MC | SBF | EUR |

Examples:
- get_stock_price("AAPL")
- get_stock_price("PETR4", "BOVESPA", "BRL")
- get_stock_price("VOLVB", "SFB", "SEK")

### Yahoo Tools (get_fundamentals, get_dividends, get_company_info, get_financial_statements)
Use Yahoo Finance format WITH dot suffixes for international stocks:
- get_fundamentals("AAPL")          # US (no suffix)
- get_fundamentals("PETR4.SA")      # Brazil
- get_fundamentals("VOLV-B.ST")     # Sweden
- get_fundamentals("BMW.DE")        # Germany

### When unsure:
Use search_symbol("company name") to find the correct IB ticker.
"""


@mcp.prompt()
def market_capabilities_guide() -> str:
    """Guide with supported market information capabilities and example questions."""
    return """## Market Capabilities Guide

When the user asks "what information can you provide?", call `get_market_capabilities`.

Recommended categories:
- `stock_screener`: gainers/losers/RSI/dividend/fundamental rankings
- `options_and_greeks`: chain, greeks, filtered option screeners
- `wheel_strategy`: put selection, annualized return, risk, assignment, covered call
- `event_calendar`: corporate + macro + central bank + market structure events
- `pipeline_and_jobs`: monitor and trigger ingestion/analytics jobs

Default analytics market is `sweden`.
Prefer intent-specific methods instead of generic mega-queries.
"""


# ============================================================================
# Local Database Tools (Pre-Cached)
# ============================================================================

@mcp.tool()
@tool_endpoint()
async def get_earnings_history(symbol: str, limit: int = 10) -> Dict[str, Any]:
    """
    Get historical earnings data (EPS surprises) for a stock from the local database.
    Generally covers the last 10 years if available.

    Parameters:
        symbol: Ticker symbol (Yahoo format), e.g. 'AAPL', 'PETR4.SA'
        limit: Number of recent quarters to return

    Returns: {"success": true, "data": [{"date": "2023-11-01", "eps_estimate": 1.2, "eps_actual": 1.4, "surprise_percent": 16.6}, ...]}
    """
    session = SessionLocal()
    try:
        stock = session.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            return {"success": False, "error": f"Stock {symbol} not found"}
        
        results = session.query(HistoricalEarnings).filter(
            HistoricalEarnings.stock_id == stock.id
        ).order_by(HistoricalEarnings.date.desc()).limit(limit).all()
        
        return {
            "success": True,
            "data": [
                {
                    "date": h.date.isoformat(),
                    "period_ending": h.period_ending.isoformat() if h.period_ending else None,
                    "eps_estimate": h.eps_estimate,
                    "eps_actual": h.eps_actual,
                    "surprise_percent": h.surprise_percent
                }
                for h in results
            ]
        }
    finally:
        session.close()


@mcp.tool()
@tool_endpoint()
async def get_earnings_calendar(symbol: str) -> Dict[str, Any]:
    """
    Get upcoming earnings date and analyst expectations for a stock.

    Parameters:
        symbol: Ticker symbol (Yahoo format), e.g. 'AAPL', 'PETR4.SA'

    Returns: {"success": true, "data": {"earnings_date": "2024-05-01", "eps_average": 1.5, ...}}
    """
    session = SessionLocal()
    try:
        stock = session.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            return {"success": False, "error": f"Stock {symbol} not found"}
        
        cal = session.query(EarningsCalendar).filter(EarningsCalendar.stock_id == stock.id).first()
        if not cal:
            return {"success": False, "error": "No upcoming earnings calendar data found"}
        
        return {
            "success": True,
            "data": {
                "symbol": symbol,
                "earnings_date": cal.earnings_date.isoformat(),
                "earnings_average": cal.earnings_average,
                "earnings_low": cal.earnings_low,
                "earnings_high": cal.earnings_high,
                "revenue_average": cal.revenue_average,
                "revenue_low": cal.revenue_low,
                "revenue_high": cal.revenue_high,
                "updated_at": cal.updated_at.isoformat()
            }
        }
    finally:
        session.close()


@mcp.tool()
@tool_endpoint()
async def query_local_stocks(country: str = None, sector: str = None) -> Dict[str, Any]:
    """
    List stocks available in the local database, optionally filtered.

    Use this to see what data is pre-cached and available for fast querying.

    Parameters:
        country: Filter by country, e.g. 'Brazil', 'Sweden', 'USA'
        sector: Filter by sector, e.g. 'Financials', 'Energy'

    Returns: {"success": true, "data": [{"symbol": "PETR4.SA", "name": "Petrobras", "sector": "Energy"}]}
    """
    session = SessionLocal()
    try:
        query = session.query(Stock)
        if country:
            query = query.filter(Stock.country == country)
        if sector:
            query = query.filter(Stock.sector == sector)
        
        results = query.all()
        return {
            "success": True,
            "data": [
                {
                    "symbol": s.symbol,
                    "name": s.name,
                    "sector": s.sector,
                    "country": s.country,
                    "currency": s.currency
                }
                for s in results
            ]
        }
    finally:
        session.close()


@mcp.tool()
@tool_endpoint()
async def query_local_fundamentals(symbol: str) -> Dict[str, Any]:
    """
    Get the latest fundamental data from the local database.

    Faster than fetching from Yahoo, but might be slightly outdated (updated daily).

    Parameters:
        symbol: Ticker symbol, e.g. 'PETR4.SA'

    Returns: {"success": true, "data": {"pe": 4.5, "eps": 2.1, ...}}
    """
    session = SessionLocal()
    try:
        stock = session.query(Stock).filter(Stock.symbol == symbol).first()
        if not stock:
            return {"success": False, "error": f"Stock {symbol} not found in local DB"}
        
        # Get latest fundamental record
        fund = session.query(Fundamental).filter(
            Fundamental.stock_id == stock.id
        ).order_by(Fundamental.fetched_at.desc()).first()
        
        if not fund:
            return {"success": False, "error": "No fundamental data available"}
        
        return {
            "success": True,
            "data": {
                "symbol": stock.symbol,
                "fetched_at": fund.fetched_at.isoformat(),
                "market_cap": fund.market_cap,
                "pe": fund.trailing_pe,
                "eps": fund.trailing_eps,
                "revenue": fund.revenue,
                "net_margin": fund.net_margin,
                "roe": fund.roe,
                "debt_to_equity": fund.debt_to_equity,
                "dividend_yield": session.query(Dividend).filter(
                    Dividend.stock_id == stock.id
                ).order_by(Dividend.ex_date.desc()).first().dividend_yield if stock.dividends else None
            }
        }
    finally:
        session.close()


# ============================================================================
# Lifecycle
# ============================================================================

async def _startup():
    """Initialize optional IBKR connection and heartbeat."""
    if not IB_ENABLED:
        logger.warning("[SERVER] IB_ENABLED=false (Yahoo-only profile active).")
        return
    await ib_conn.connect()
    await ib_conn.start_heartbeat()


def _handle_signal(sig, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    logger.info(f"[SIGNAL] Received {signal.Signals(sig).name}, shutting down...")
    loop = asyncio.get_event_loop()
    loop.create_task(ib_conn.shutdown())


def main():
    """CLI entrypoint for mcp-finance."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(
        "[SERVER] Starting MCP Finance Server "
        f"(transport={MCP_TRANSPORT}, host={MCP_HOST}, port={MCP_PORT}, ib_enabled={IB_ENABLED})"
    )
    try:
        boot_loop = asyncio.get_event_loop()
        boot_loop.run_until_complete(_startup())
        mcp.run(transport=MCP_TRANSPORT)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Server crashed: {e}")
    finally:
        try:
            shutdown_loop = asyncio.get_event_loop()
            if IB_ENABLED:
                shutdown_loop.run_until_complete(ib_conn.shutdown())
        except Exception:
            pass


if __name__ == "__main__":
    main()
