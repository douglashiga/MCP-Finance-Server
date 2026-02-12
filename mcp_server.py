import asyncio
import logging
import os
import signal
from typing import Any, Dict, List
from mcp.server.fastmcp import FastMCP

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

mcp = FastMCP("mcp-finance", host=MCP_HOST, port=MCP_PORT)

# ============================================================================
# IBKR Tools (Real-time, Priority)
# ============================================================================

@mcp.tool()
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
@require_connection
async def get_historical_data(symbol: str, duration: str = "1 D", bar_size: str = "1 hour") -> Dict[str, Any]:
    """
    Get historical OHLCV bars from Interactive Brokers.

    Use this for chart data, technical analysis, or trend detection.
    Results are cached for 30 seconds to reduce API load.

    Parameters:
        symbol: IB ticker (no suffixes), e.g. 'AAPL', 'PETR4', 'VOLVB'
        duration: How far back. Options: '1 D', '1 W', '1 M', '3 M', '1 Y'
        bar_size: Bar granularity. Options: '1 min', '5 mins', '15 mins', '1 hour', '1 day'

    Returns: {"success": true, "data": [{"date": "2024-01-15", "open": 150.0, "high": 155.0, "low": 149.0, "close": 153.0, "volume": 50000}]}

    Example: get_historical_data("AAPL", "1 M", "1 day")
    """
    return await HistoryService.get_historical_data(symbol, duration, bar_size)


@mcp.tool()
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
@require_connection
async def get_account_summary() -> Dict[str, Any]:
    """
    Get account summary with balances and margin from Interactive Brokers.

    Includes: NetLiquidation, BuyingPower, TotalCashValue, Margin Requirements,
    AvailableFunds, ExcessLiquidity, and Cushion.

    Returns: {"success": true, "data": {"NetLiquidation": {"value": "100000", "currency": "USD"}, "MaintMarginReq": {"value": "5000", "currency": "USD"}, ...}}

    Example: get_account_summary()
    """
    return await AccountService.get_summary()


@mcp.tool()
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
    return await OptionService.get_option_greeks(symbol, last_trade_date, strike, right)


# ============================================================================
# Yahoo Finance Tools (Fundamentals, Complementary Data)
# ============================================================================

@mcp.tool()
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
async def get_company_info(symbol: str) -> Dict[str, Any]:
    """
    Get company profile from Yahoo Finance: sector, industry, description, employees, website.

    Use this to understand what a company does before analyzing its stock.

    Parameters:
        symbol: Yahoo Finance ticker. Use suffix for international: 'AAPL', 'PETR4.SA', 'VOLV-B.ST'

    Returns: {"success": true, "data": {"shortName": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics", "longBusinessSummary": "...", ...}}

    Example: get_company_info("AAPL")
    """
    return YahooService.get_company_info(symbol)


@mcp.tool()
async def get_financial_statements(symbol: str) -> Dict[str, Any]:
    """
    Get annual financial statements from Yahoo Finance: Income Statement, Balance Sheet, Cash Flow.

    Use this for deep financial analysis and comparing across periods.

    Parameters:
        symbol: Yahoo Finance ticker. Use suffix for international: 'AAPL', 'PETR4.SA'

    Returns: {"success": true, "data": {"income_statement": [...], "balance_sheet": [...], "cash_flow": [...]}}

    Example: get_financial_statements("MSFT")
    """
    return YahooService.get_financial_statements(symbol)


@mcp.tool()
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


# ============================================================================
# Stock Screener Tools
# ============================================================================

@mcp.tool()
async def get_stock_screener(market: str = "all", sector: str = None,
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
async def get_top_gainers(market: str = "all", period: str = "1D", limit: int = 10) -> Dict[str, Any]:
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
async def get_top_losers(market: str = "all", period: str = "1D", limit: int = 10) -> Dict[str, Any]:
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
async def get_top_dividend_payers(market: str = "all", sector: str = None,
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
async def get_technical_signals(market: str = "all", signal_type: str = "oversold") -> Dict[str, Any]:
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
    return ScreenerService.get_technical_signals(market, signal_type)


# ============================================================================
# Option Screener Tools
# ============================================================================

@mcp.tool()
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
    return OptionScreenerService.get_option_screener(
        symbol, expiry, right, min_delta, max_delta, min_iv, max_iv, has_liquidity, limit
    )


@mcp.tool()
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
# Job Management Tools (LLM can manage data pipeline)
# ============================================================================

@mcp.tool()
async def list_jobs() -> Dict[str, Any]:
    """
    List all data loader jobs with their schedule, status, and last run info.
    Use this to understand what data pipelines exist and their health.

    Returns: List of jobs with name, cron schedule, active status, and last run details.
    """
    return JobService.list_jobs()


@mcp.tool()
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
async def trigger_job(job_name: str) -> Dict[str, Any]:
    """
    Manually trigger a data loader job to run immediately.
    Use this when data seems stale or you need fresh data.

    Parameters:
        job_name: Full or partial job name (e.g. 'Calculate Stock Metrics')

    Example: trigger_job("Extract Yahoo Prices") → runs the price extractor now
    """
    return JobService.trigger_job(job_name)


@mcp.tool()
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
async def get_job_status() -> Dict[str, Any]:
    """
    Get health overview of all data pipeline jobs.
    Shows total, healthy, warning, and error counts plus per-job details.

    Returns: Summary with counts + list of all jobs with last run status.
    """
    return JobService.get_job_status()


@mcp.tool()
async def run_pipeline_health_check() -> Dict[str, Any]:
    """
    Trigger a lightweight health check across all data loader jobs.
    Each job script is executed in 'test' mode (limiting symbols) 
    to verify connectivity, authentication and basic parsing.

    Use this when you want to verify that the whole pipeline is functional.
    """
    return JobService.run_pipeline_health_check()


# ============================================================================
# Resources
# ============================================================================

@mcp.resource("finance://status")
async def resource_status() -> Dict[str, Any]:
    """Get the current connection status, health, and server time from IB Gateway."""
    return await ib_conn.check_health()


@mcp.resource("finance://account/summary")
@require_connection
async def resource_account_summary() -> Dict[str, Any]:
    """Get the account summary including margin and liquidity data."""
    return await AccountService.get_summary()


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


# ============================================================================
# Local Database Tools (Pre-Cached)
# ============================================================================

@mcp.tool()
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
    """Initialize connection and start heartbeat."""
    await ib_conn.connect()
    await ib_conn.start_heartbeat()


def _handle_signal(sig, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    logger.info(f"[SIGNAL] Received {signal.Signals(sig).name}, shutting down...")
    loop = asyncio.get_event_loop()
    loop.create_task(ib_conn.shutdown())


if __name__ == "__main__":
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(f"[SERVER] Starting MCP Finance Server (transport={MCP_TRANSPORT}, host={MCP_HOST}, port={MCP_PORT})")

    try:
        mcp.run(transport=MCP_TRANSPORT)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.critical(f"Server crashed: {e}")
