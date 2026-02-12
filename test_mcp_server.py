import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import pytest_asyncio

# Fix Event Loop
try:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
except Exception:
    pass

from mcp_server import (
    get_stock_price, search_symbol, get_account_summary, get_historical_data,
    get_option_chain, get_option_greeks,
    get_fundamentals, get_dividends, get_company_info, get_financial_statements,
    get_exchange_info, yahoo_search,
    get_stock_screener, get_top_gainers, get_top_losers,
    get_top_dividend_payers, get_technical_signals,
    list_jobs, get_job_logs, trigger_job, toggle_job, get_job_status,
    get_option_screener, get_option_chain_snapshot, run_pipeline_health_check
)
from services.market_service import MarketService
from services.account_service import AccountService
from services.history_service import HistoryService
from services.option_service import OptionService
from services.yahoo_service import YahooService
from services.screener_service import ScreenerService
from services.job_service import JobService
from services.option_screener_service import OptionScreenerService

# Patch IB connection to always return True
@pytest.fixture(autouse=True)
def mock_ib_connection():
    with patch('core.connection.IBConnection.is_connected', return_value=True):
        yield

@pytest_asyncio.fixture(autouse=True)
async def mock_rate_limiter():
    with patch('core.connection.RateLimiter.wait', new_callable=AsyncMock):
        yield

# --- IBKR Tools ---

@pytest.mark.asyncio
async def test_get_stock_price():
    with patch.object(MarketService, 'get_price', new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"symbol": "AAPL", "price": 150.0}}
        result = await get_stock_price("AAPL")
        assert result['success'] is True
        assert result['data']['price'] == 150.0

@pytest.mark.asyncio
async def test_get_historical_data():
    with patch.object(HistoryService, 'get_historical_data', new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": [{"date": "2024-01-01", "close": 150.0}]}
        result = await get_historical_data("AAPL")
        assert result['success'] is True
        assert len(result['data']) == 1

@pytest.mark.asyncio
async def test_search_symbol():
    with patch.object(MarketService, 'search_symbol', new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": [{"symbol": "AAPL"}]}
        result = await search_symbol("AAPL")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_get_account_summary():
    with patch.object(AccountService, 'get_summary', new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"NetLiquidation": {"value": "100000", "currency": "USD"}}}
        result = await get_account_summary()
        assert result['success'] is True
        assert "NetLiquidation" in result['data']

@pytest.mark.asyncio
async def test_get_option_chain():
    with patch.object(OptionService, 'get_option_chain', new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"expirations": ["20240119"], "strikes": [150.0]}}
        result = await get_option_chain("AAPL")
        assert result['success'] is True
        assert "expirations" in result['data']

@pytest.mark.asyncio
async def test_get_option_greeks():
    with patch.object(OptionService, 'get_option_greeks', new_callable=AsyncMock) as mock:
        mock.return_value = {"success": True, "data": {"delta": 0.5, "gamma": 0.02}}
        result = await get_option_greeks("AAPL", "20240119", 150.0, "C")
        assert result['success'] is True
        assert result['data']['delta'] == 0.5

# --- Yahoo Finance Tools ---

@pytest.mark.asyncio
async def test_get_fundamentals():
    with patch.object(YahooService, 'get_fundamentals') as mock:
        mock.return_value = {"success": True, "data": {"symbol": "AAPL", "trailingPE": 28.5}}
        result = await get_fundamentals("AAPL")
        assert result['success'] is True
        assert result['data']['trailingPE'] == 28.5

@pytest.mark.asyncio
async def test_get_dividends():
    with patch.object(YahooService, 'get_dividends') as mock:
        mock.return_value = {"success": True, "data": {"symbol": "KO", "dividendYield": 0.03}}
        result = await get_dividends("KO")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_get_company_info():
    with patch.object(YahooService, 'get_company_info') as mock:
        mock.return_value = {"success": True, "data": {"shortName": "Apple Inc.", "sector": "Technology"}}
        result = await get_company_info("AAPL")
        assert result['success'] is True
        assert result['data']['sector'] == "Technology"

@pytest.mark.asyncio
async def test_get_financial_statements():
    with patch.object(YahooService, 'get_financial_statements') as mock:
        mock.return_value = {"success": True, "data": {"income_statement": [], "balance_sheet": [], "cash_flow": []}}
        result = await get_financial_statements("AAPL")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_get_exchange_info():
    with patch.object(YahooService, 'get_exchange_info') as mock:
        mock.return_value = {"success": True, "data": {"exchange": "NMS", "marketState": "REGULAR"}}
        result = await get_exchange_info("AAPL")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_yahoo_search():
    with patch.object(YahooService, 'search_tickers') as mock:
        mock.return_value = {"success": True, "data": [{"symbol": "TSLA", "shortname": "Tesla"}]}
        result = await yahoo_search("Tesla")
        assert result['success'] is True
        assert result['data'][0]['symbol'] == "TSLA"

# --- Stock Screener Tools ---

@pytest.mark.asyncio
async def test_get_stock_screener():
    with patch.object(ScreenerService, 'get_stock_screener') as mock:
        mock.return_value = {"success": True, "data": [{"symbol": "PETR4.SA", "perf_1d": 2.5}], "count": 1}
        result = await get_stock_screener("brazil")
        assert result['success'] is True
        assert result['count'] == 1

@pytest.mark.asyncio
async def test_get_top_gainers():
    with patch.object(ScreenerService, 'get_top_movers') as mock:
        mock.return_value = {"success": True, "data": [{"rank": 1, "symbol": "WEGE3.SA", "value": 8.5}], "count": 1}
        result = await get_top_gainers("brazil", "1D")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_get_top_losers():
    with patch.object(ScreenerService, 'get_top_movers') as mock:
        mock.return_value = {"success": True, "data": [{"rank": 1, "symbol": "MGLU3.SA", "value": -5.2}], "count": 1}
        result = await get_top_losers("brazil", "1D")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_get_top_dividend_payers():
    with patch.object(ScreenerService, 'get_top_dividend_payers') as mock:
        mock.return_value = {"success": True, "data": [{"symbol": "SEB-A.ST", "dividend_yield": 6.5}], "count": 1}
        result = await get_top_dividend_payers("sweden", sector="Financials")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_get_technical_signals():
    with patch.object(ScreenerService, 'get_technical_signals') as mock:
        mock.return_value = {"success": True, "data": [{"symbol": "ERIC-B.ST", "rsi_14": 25.3}], "count": 1}
        result = await get_technical_signals("sweden", "oversold")
        assert result['success'] is True

# --- Job Management Tools ---

@pytest.mark.asyncio
async def test_list_jobs():
    with patch.object(JobService, 'list_jobs') as mock:
        mock.return_value = {"success": True, "data": [{"name": "Extract Yahoo Prices"}], "count": 1}
        result = await list_jobs()
        assert result['success'] is True
        assert result['count'] == 1

@pytest.mark.asyncio
async def test_get_job_logs():
    with patch.object(JobService, 'get_job_logs') as mock:
        mock.return_value = {"success": True, "data": [{"status": "success"}], "count": 1}
        result = await get_job_logs("Yahoo Prices")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_trigger_job():
    with patch.object(JobService, 'trigger_job') as mock:
        mock.return_value = {"success": True, "job_name": "Extract Yahoo Prices", "status": "success"}
        result = await trigger_job("Extract Yahoo Prices")
        assert result['success'] is True

@pytest.mark.asyncio
async def test_toggle_job():
    with patch.object(JobService, 'toggle_job') as mock:
        mock.return_value = {"success": True, "job_name": "IBKR Prices", "is_active": False}
        result = await toggle_job("IBKR Prices", False)
        assert result['success'] is True

@pytest.mark.asyncio
async def test_get_job_status():
    with patch.object(JobService, 'get_job_status') as mock:
        mock.return_value = {"success": True, "summary": {"total": 12, "healthy": 10, "error": 2}}
        result = await get_job_status()
        assert result["success"] is True
        assert "total" in result["summary"]
        assert result['summary']['total'] == 12

@pytest.mark.asyncio
async def test_get_option_screener():
    # Test with default params
    with patch.object(OptionScreenerService, 'get_option_screener') as mock:
        mock.return_value = {"success": True, "data": [{"symbol": "AAPL", "strike": 150.0}], "count": 1}
        data = await get_option_screener(limit=1)
        assert data["success"] is True
        assert len(data["data"]) == 1

@pytest.mark.asyncio
async def test_get_option_chain_snapshot():
    # Test with mockup symbol
    with patch.object(OptionScreenerService, 'get_option_chain_snapshot') as mock:
        mock.return_value = {"success": True, "data": {"symbol": "AAPL"}}
        data = await get_option_chain_snapshot("AAPL")
        assert data["success"] is True

@pytest.mark.asyncio
async def test_run_pipeline_health_check():
    # Should trigger a background job
    with patch.object(JobService, 'run_pipeline_health_check') as mock:
        mock.return_value = {"success": True, "status": "executed"}
        data = await run_pipeline_health_check()
        assert data["success"] is True
