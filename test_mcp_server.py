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
    get_exchange_info, yahoo_search
)
from services.market_service import MarketService
from services.account_service import AccountService
from services.history_service import HistoryService
from services.option_service import OptionService
from services.yahoo_service import YahooService

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
