import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

def _get_yf():
    """Lazy import yfinance to avoid pandas import at module load time."""
    import yfinance as yf
    return yf


class YahooService:
    """
    Complementary data provider using Yahoo Finance.
    Used for fundamentals, dividends, exchange info, and company profiles
    that IBKR does not provide or charges extra for.
    
    NOTE: yfinance is imported lazily to avoid startup failures
    if pandas is not available or incompatible.
    """

    @staticmethod
    def get_price(symbol: str) -> Dict[str, Any]:
        """Get current price data from Yahoo Finance (free, no subscription needed)."""
        logger.info(f"[YAHOO:PRICE] {symbol}")
        try:
            yf = _get_yf()
            ticker = yf.Ticker(symbol)
            info = ticker.info

            price = info.get("currentPrice") or info.get("regularMarketPrice")
            prev_close = info.get("regularMarketPreviousClose") or info.get("previousClose")

            data = {
                "symbol": symbol,
                "shortName": info.get("shortName"),
                "price": float(price) if price else None,
                "previousClose": float(prev_close) if prev_close else None,
                "open": float(info["regularMarketOpen"]) if info.get("regularMarketOpen") else None,
                "dayHigh": float(info["dayHigh"]) if info.get("dayHigh") else None,
                "dayLow": float(info["dayLow"]) if info.get("dayLow") else None,
                "volume": int(info["volume"]) if info.get("volume") else None,
                "bid": float(info["bid"]) if info.get("bid") else None,
                "ask": float(info["ask"]) if info.get("ask") else None,
                "marketCap": info.get("marketCap"),
                "exchange": info.get("exchange"),
                "currency": info.get("currency"),
                "marketState": info.get("marketState"),
                "source": "yahoo_finance",
            }
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"[YAHOO:PRICE] Error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_fundamentals(symbol: str) -> Dict[str, Any]:
        """Get fundamental data from local database (populated by ELT pipeline)."""
        from dataloader.database import SessionLocal
        from dataloader.models import Stock, Fundamental
        
        logger.info(f"[YAHOO:FUNDAMENTALS] {symbol} from local DB")
        
        session = SessionLocal()
        try:
            stock = session.query(Stock).filter_by(symbol=symbol).first()
            
            if not stock:
                logger.info(f"[FUNDAMENTALS] Stock {symbol} not found in local DB")
                return {"success": False, "error": f"Stock {symbol} not found in database"}
            
            # Get latest fundamental record
            fundamental = session.query(Fundamental).filter_by(
                stock_id=stock.id
            ).order_by(Fundamental.fetched_at.desc()).first()
            
            if not fundamental:
                logger.info(f"[FUNDAMENTALS] No fundamental data for {symbol}")
                return {"success": False, "error": f"No fundamental data available for {symbol}"}
            
            data = {
                "symbol": symbol,
                "shortName": stock.name,
                "sector": stock.sector,
                "industry": stock.industry,
                "marketCap": fundamental.market_cap,
                "enterpriseValue": fundamental.enterprise_value,
                "trailingPE": fundamental.trailing_pe,
                "forwardPE": fundamental.forward_pe,
                "trailingEps": fundamental.trailing_eps,
                "forwardEps": fundamental.forward_eps,
                "pegRatio": fundamental.peg_ratio,
                "priceToBook": fundamental.price_to_book,
                "revenue": fundamental.revenue,
                "grossMargins": fundamental.gross_margin,
                "profitMargins": fundamental.net_margin,
                "returnOnEquity": fundamental.roe,
                "debtToEquity": fundamental.debt_to_equity,
                "freeCashflow": fundamental.free_cash_flow,
                "fetched_at": fundamental.fetched_at.isoformat() if fundamental.fetched_at else None,
                "source": "local_database",
            }
            return {"success": True, "data": data}
        finally:
            session.close()

    @staticmethod
    def get_dividends(symbol: str) -> Dict[str, Any]:
        """Get dividend history from local database (populated by ELT pipeline)."""
        from dataloader.database import SessionLocal
        from dataloader.models import Stock, Dividend
        
        logger.info(f"[YAHOO:DIVIDENDS] {symbol} from local DB")
        
        session = SessionLocal()
        try:
            stock = session.query(Stock).filter_by(symbol=symbol).first()
            
            if not stock:
                logger.info(f"[DIVIDENDS] Stock {symbol} not found in local DB")
                return {"success": False, "error": f"Stock {symbol} not found in database"}
            
            # Get dividend history
            dividends = session.query(Dividend).filter_by(
                stock_id=stock.id
            ).order_by(Dividend.ex_date.desc()).limit(20).all()
            
            history = []
            for div in dividends:
                history.append({
                    "date": div.ex_date.isoformat() if div.ex_date else None,
                    "amount": div.amount,
                })
            
            # Get latest dividend yield
            latest_div = dividends[0] if dividends else None
            
            data = {
                "symbol": symbol,
                "dividendYield": latest_div.dividend_yield if latest_div else None,
                "payoutRatio": latest_div.payout_ratio if latest_div else None,
                "history": history,
                "source": "local_database",
            }
            return {"success": True, "data": data}
        finally:
            session.close()

    @staticmethod
    def get_company_info(symbol: str) -> Dict[str, Any]:
        """Get company profile from local database snapshot tables."""
        from dataloader.database import SessionLocal
        from dataloader.models import Stock, CompanyProfile, RawYahooFundamental

        logger.info(f"[YAHOO:COMPANY] {symbol} from local DB")

        session = SessionLocal()
        try:
            stock = session.query(Stock).filter_by(symbol=symbol).first()
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found in database"}

            profile = session.query(CompanyProfile).filter_by(stock_id=stock.id).first()
            raw = session.query(RawYahooFundamental).filter_by(symbol=stock.symbol).order_by(
                RawYahooFundamental.fetched_at.desc()
            ).first()
            raw_info = {}
            if raw and raw.data:
                try:
                    import json
                    raw_info = json.loads(raw.data)
                except Exception:
                    raw_info = {}

            data = {
                "symbol": stock.symbol,
                "shortName": raw_info.get("shortName") or stock.name,
                "longName": raw_info.get("longName") or stock.name,
                "sector": stock.sector,
                "industry": stock.industry,
                "country": (profile.country if profile else None) or stock.country,
                "city": profile.city if profile else raw_info.get("city"),
                "website": profile.website if profile else raw_info.get("website"),
                "longBusinessSummary": profile.business_summary if profile else raw_info.get("longBusinessSummary"),
                "fullTimeEmployees": profile.employees if profile else raw_info.get("fullTimeEmployees"),
                "exchange": stock.exchange,
                "quoteType": "EQUITY",
                "source": "local_database",
            }
            return {"success": True, "data": data}
        finally:
            session.close()

    @staticmethod
    def get_financial_statements(symbol: str) -> Dict[str, Any]:
        """Get financial statements from local cached intelligence snapshot."""
        from services.market_intelligence_service import MarketIntelligenceService

        logger.info(f"[YAHOO:FINANCIALS] {symbol} from local DB")
        return MarketIntelligenceService.get_financial_statements(symbol, statement_type="all")

    @staticmethod
    def get_exchange_info(symbol: str) -> Dict[str, Any]:
        """Get exchange information: timezone, hours, market state."""
        logger.info(f"[YAHOO:EXCHANGE] {symbol}")
        try:
            yf = _get_yf()
            ticker = yf.Ticker(symbol)
            info = ticker.info

            data = {
                "symbol": symbol,
                "exchange": info.get("exchange"),
                "exchangeTimezoneName": info.get("exchangeTimezoneName"),
                "exchangeTimezoneShortName": info.get("exchangeTimezoneShortName"),
                "gmtOffSetMilliseconds": info.get("gmtOffSetMilliseconds"),
                "market": info.get("market"),
                "marketState": info.get("marketState"),
            }
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"[YAHOO:EXCHANGE] Error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def search_tickers(query: str) -> Dict[str, Any]:
        """Search for tickers by name, sector, or keyword."""
        logger.info(f"[YAHOO:SEARCH] {query}")
        try:
            yf = _get_yf()
            search = yf.Search(query)
            results = []

            if hasattr(search, 'quotes') and search.quotes:
                for q in search.quotes[:15]:
                    results.append({
                        "symbol": q.get("symbol"),
                        "shortname": q.get("shortname"),
                        "longname": q.get("longname"),
                        "exchange": q.get("exchange"),
                        "quoteType": q.get("quoteType"),
                        "sector": q.get("sector"),
                        "industry": q.get("industry"),
                    })

            return {"success": True, "data": results}
        except Exception as e:
            logger.error(f"[YAHOO:SEARCH] Error: {e}")
            return {"success": False, "error": str(e)}
    @staticmethod
    def get_dividend_yield(symbol: str) -> Dict[str, Any]:
        """Get only the current dividend yield."""
        res = YahooService.get_dividends(symbol)
        if not res.get("success"): return res
        return {
            "success": True,
            "symbol": symbol,
            "dividendYield": res["data"].get("dividendYield"),
            "payoutRatio": res["data"].get("payoutRatio")
        }

    @staticmethod
    def get_dividend_history(symbol: str, period: str = "5y") -> Dict[str, Any]:
        """Get dividend history for a period."""
        # Current get_dividends already returns history, but we can limit/filter here if needed
        return YahooService.get_dividends(symbol)
