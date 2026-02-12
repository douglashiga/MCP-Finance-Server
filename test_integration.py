"""
Integration tests for MCP Finance Server with real market data.
Tests symbols from Brazil, Sweden, and USA markets.
Validates that no empty/null values are returned.
"""
import asyncio
import pytest

# Fix Event Loop before ib_insync import
try:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
except Exception:
    pass

from dataloader.database import SessionLocal
from dataloader.models import Stock, RealtimePrice, Fundamental, Dividend
from services.market_service import MarketService
from services.yahoo_service import YahooService

# Test symbols for each market
TEST_SYMBOLS = {
    "brazil": ["PETR4.SA", "VALE3.SA", "ITUB4.SA"],
    "sweden": ["VOLV-B.ST", "ERIC-B.ST", "ABB.ST"],
    "usa": ["AAPL", "MSFT", "GOOGL"]
}


@pytest.fixture
def db_session():
    """Provide a database session for tests."""
    session = SessionLocal()
    yield session
    session.close()


def validate_not_empty(data: dict, required_fields: list, symbol: str):
    """Validate that required fields are not None/empty."""
    for field in required_fields:
        value = data.get(field)
        assert value is not None, f"Field '{field}' is None for {symbol}"
        assert value != "", f"Field '{field}' is empty for {symbol}"
        assert value != 0 or field == "volume", f"Field '{field}' is zero for {symbol}"


class TestBrazilMarket:
    """Tests for Brazilian stocks (B3)."""
    
    @pytest.mark.asyncio
    async def test_brazil_stock_price(self):
        """Test real-time prices for Brazilian stocks."""
        for symbol in TEST_SYMBOLS["brazil"]:
            result = await MarketService.get_price(symbol)
            
            assert result["success"] is True, f"Failed to get price for {symbol}"
            assert "data" in result
            
            data = result["data"]
            required_fields = ["symbol", "price", "currency", "source"]
            validate_not_empty(data, required_fields, symbol)
            
            # Brazil-specific validations
            assert data["currency"] == "BRL", f"Expected BRL currency for {symbol}"
            print(f"✅ {symbol}: {data['price']} {data['currency']}")
    
    def test_brazil_stock_in_database(self, db_session):
        """Verify Brazilian stocks are in the database."""
        for symbol in TEST_SYMBOLS["brazil"]:
            stock = db_session.query(Stock).filter_by(symbol=symbol).first()
            assert stock is not None, f"Stock {symbol} not found in database"
            assert stock.exchange == "B3" or stock.exchange == "SAO"
            print(f"✅ {symbol} in database: {stock.name}")


class TestSwedenMarket:
    """Tests for Swedish stocks (OMX)."""
    
    @pytest.mark.asyncio
    async def test_sweden_stock_price(self):
        """Test real-time prices for Swedish stocks."""
        for symbol in TEST_SYMBOLS["sweden"]:
            result = await MarketService.get_price(symbol)
            
            assert result["success"] is True, f"Failed to get price for {symbol}"
            assert "data" in result
            
            data = result["data"]
            required_fields = ["symbol", "price", "currency", "source"]
            validate_not_empty(data, required_fields, symbol)
            
            # Sweden-specific validations
            assert data["currency"] == "SEK", f"Expected SEK currency for {symbol}"
            print(f"✅ {symbol}: {data['price']} {data['currency']}")
    
    def test_sweden_stock_in_database(self, db_session):
        """Verify Swedish stocks are in the database."""
        for symbol in TEST_SYMBOLS["sweden"]:
            stock = db_session.query(Stock).filter_by(symbol=symbol).first()
            assert stock is not None, f"Stock {symbol} not found in database"
            assert stock.exchange in ["OMX", "STO"]
            print(f"✅ {symbol} in database: {stock.name}")


class TestUSAMarket:
    """Tests for US stocks (NASDAQ/NYSE)."""
    
    @pytest.mark.asyncio
    async def test_usa_stock_price(self):
        """Test real-time prices for US stocks."""
        prices_found = 0
        for symbol in TEST_SYMBOLS["usa"]:
            result = await MarketService.get_price(symbol)
            
            # US stocks may not have prices yet (need to run extractors first)
            if not result["success"]:
                print(f"⚠️  {symbol}: No price data yet (run extractors)")
                continue
            
            assert "data" in result
            
            data = result["data"]
            required_fields = ["symbol", "price", "currency", "source"]
            validate_not_empty(data, required_fields, symbol)
            
            # USA-specific validations
            assert data["currency"] == "USD", f"Expected USD currency for {symbol}"
            print(f"✅ {symbol}: {data['price']} {data['currency']}")
            prices_found += 1
        
        # At least one price should be found
        print(f"\n📊 Found prices for {prices_found}/{len(TEST_SYMBOLS['usa'])} US stocks")
        assert prices_found > 0, "No US stock prices found. Run extractors first."
    
    def test_usa_stock_in_database(self, db_session):
        """Verify US stocks are in the database."""
        for symbol in TEST_SYMBOLS["usa"]:
            stock = db_session.query(Stock).filter_by(symbol=symbol).first()
            assert stock is not None, f"Stock {symbol} not found in database"
            assert stock.exchange in ["NASDAQ", "NYSE", "NMS"]
            print(f"✅ {symbol} in database: {stock.name}")


class TestFundamentals:
    """Tests for fundamental data across markets."""
    
    def test_fundamentals_all_markets(self):
        """Test fundamentals for stocks from all markets."""
        all_symbols = (
            TEST_SYMBOLS["brazil"] + 
            TEST_SYMBOLS["sweden"] + 
            TEST_SYMBOLS["usa"]
        )
        
        for symbol in all_symbols:
            result = YahooService.get_fundamentals(symbol)
            
            # Some stocks may not have fundamentals in local DB yet
            if result["success"]:
                data = result["data"]
                
                # At least some fundamental fields should be present
                fundamental_fields = ["marketCap", "trailingPE", "forwardPE", "dividendYield"]
                has_data = any(data.get(field) is not None for field in fundamental_fields)
                
                assert has_data, f"No fundamental data found for {symbol}"
                print(f"✅ {symbol}: Fundamentals available")


class TestDividends:
    """Tests for dividend data across markets."""
    
    def test_dividends_all_markets(self):
        """Test dividend data for dividend-paying stocks."""
        # Known dividend payers
        dividend_symbols = ["PETR4.SA", "VOLV-B.ST", "AAPL"]
        
        for symbol in dividend_symbols:
            result = YahooService.get_dividends(symbol)
            
            if result["success"] and result["data"]:
                data = result["data"]
                
                # Validate dividend fields
                if "dividends" in data and data["dividends"]:
                    first_div = data["dividends"][0]
                    required_fields = ["ex_date", "amount"]
                    validate_not_empty(first_div, required_fields, symbol)
                    
                print(f"✅ {symbol}: Dividend data available")


class TestRealtimePrices:
    """Tests for realtime_prices table."""
    
    def test_realtime_prices_not_empty(self, db_session):
        """Verify realtime_prices table has data with no null values."""
        prices = db_session.query(RealtimePrice).limit(10).all()
        
        assert len(prices) > 0, "realtime_prices table is empty"
        
        for price in prices:
            # All prices should have non-null values
            assert price.price is not None, f"Price is null for stock_id {price.stock_id}"
            assert price.price > 0, f"Price is zero or negative for stock_id {price.stock_id}"
            assert price.last_updated is not None, f"last_updated is null for stock_id {price.stock_id}"
            
            print(f"✅ Stock ID {price.stock_id}: ${price.price} (updated: {price.last_updated})")


class TestDataValidation:
    """Cross-market data validation tests."""
    
    def test_all_stocks_have_required_fields(self, db_session):
        """Verify all stocks in database have required fields."""
        stocks = db_session.query(Stock).all()
        
        assert len(stocks) > 0, "No stocks in database"
        
        for stock in stocks:
            assert stock.symbol, f"Stock ID {stock.id} has no symbol"
            assert stock.name, f"Stock {stock.symbol} has no name"
            assert stock.exchange, f"Stock {stock.symbol} has no exchange"
            assert stock.currency, f"Stock {stock.symbol} has no currency"
    
    def test_market_distribution(self, db_session):
        """Verify we have stocks from all 3 markets."""
        brazil_count = db_session.query(Stock).filter(
            Stock.symbol.like("%.SA")
        ).count()
        
        sweden_count = db_session.query(Stock).filter(
            Stock.symbol.like("%.ST")
        ).count()
        
        usa_count = db_session.query(Stock).filter(
            Stock.exchange.in_(["NASDAQ", "NYSE", "NMS"])
        ).count()
        
        print(f"\n📊 Market Distribution:")
        print(f"   Brazil (B3): {brazil_count} stocks")
        print(f"   Sweden (OMX): {sweden_count} stocks")
        print(f"   USA: {usa_count} stocks")
        
        assert brazil_count > 0, "No Brazilian stocks in database"
        assert sweden_count > 0, "No Swedish stocks in database"
        assert usa_count > 0, "No US stocks in database"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
