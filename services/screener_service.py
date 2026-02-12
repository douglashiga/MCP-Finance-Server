"""
Stock Screener Service — Queries stock_metrics and market_movers tables
for top gainers, losers, dividend payers, and technical signals.
All data comes from the local database (pre-calculated by ELT jobs).
"""
import logging
from datetime import date
from sqlalchemy import and_, desc, asc
from dataloader.database import SessionLocal
from dataloader.models import Stock, StockMetrics, MarketMover, Dividend, Fundamental

logger = logging.getLogger(__name__)

# Map user-friendly market names to internal codes
MARKET_MAP = {
    "brazil": ["B3"],
    "b3": ["B3"],
    "sweden": ["OMX"],
    "omx": ["OMX"],
    "usa": ["NASDAQ", "NYSE"],
    "us": ["NASDAQ", "NYSE"],
    "nasdaq": ["NASDAQ"],
    "nyse": ["NYSE"],
    "all": ["B3", "OMX", "NASDAQ", "NYSE"],
}


def _resolve_market(market: str) -> list:
    """Resolve market name to list of exchange codes."""
    return MARKET_MAP.get(market.lower(), [market.upper()])


class ScreenerService:

    @staticmethod
    def get_stock_screener(market: str = "all", sector: str = None,
                           sort_by: str = "perf_1d", limit: int = 50):
        """
        Stock screener with filters. Returns stocks with all metrics.
        """
        session = SessionLocal()
        try:
            today = date.today()
            exchanges = _resolve_market(market)

            query = session.query(StockMetrics, Stock).join(
                Stock, Stock.id == StockMetrics.stock_id
            ).filter(
                Stock.exchange.in_(exchanges),
                StockMetrics.date == today
            )

            if sector:
                query = query.filter(Stock.sector.ilike(f"%{sector}%"))

            # Sort
            sort_map = {
                "perf_1d": StockMetrics.perf_1d,
                "perf_1w": StockMetrics.perf_1w,
                "perf_1m": StockMetrics.perf_1m,
                "perf_1y": StockMetrics.perf_1y,
                "rsi": StockMetrics.rsi_14,
                "volume": StockMetrics.avg_volume_10d,
                "volatility": StockMetrics.volatility_30d,
            }
            sort_col = sort_map.get(sort_by, StockMetrics.perf_1d)
            query = query.order_by(desc(sort_col)).limit(limit)

            results = query.all()

            data = []
            for metrics, stock in results:
                data.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "currency": stock.currency,
                    "perf_1d": metrics.perf_1d,
                    "perf_1w": metrics.perf_1w,
                    "perf_2w": metrics.perf_2w,
                    "perf_1m": metrics.perf_1m,
                    "perf_3m": metrics.perf_3m,
                    "perf_1y": metrics.perf_1y,
                    "perf_ytd": metrics.perf_ytd,
                    "rsi_14": metrics.rsi_14,
                    "macd": metrics.macd,
                    "macd_signal": metrics.macd_signal,
                    "ema_20": metrics.ema_20,
                    "ema_50": metrics.ema_50,
                    "sma_200": metrics.sma_200,
                    "avg_volume_10d": metrics.avg_volume_10d,
                    "volume_ratio": metrics.volume_ratio,
                    "volatility_30d": metrics.volatility_30d,
                    "high_52w": metrics.high_52w,
                    "low_52w": metrics.low_52w,
                    "distance_52w_high": metrics.distance_52w_high,
                    "distance_52w_low": metrics.distance_52w_low,
                })

            return {"success": True, "data": data, "count": len(data), "market": market}

        except Exception as e:
            logger.error(f"Screener error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_top_movers(market: str = "all", period: str = "1D",
                       category: str = "top_gainers", limit: int = 10):
        """
        Get top gainers, losers, or most active stocks.
        category: 'top_gainers', 'top_losers', 'most_active'
        """
        session = SessionLocal()
        try:
            exchanges = _resolve_market(market)

            results = session.query(MarketMover, Stock).join(
                Stock, Stock.id == MarketMover.stock_id
            ).filter(
                MarketMover.market.in_(exchanges),
                MarketMover.period == period.upper(),
                MarketMover.category == category,
            ).order_by(MarketMover.rank).limit(limit).all()

            data = []
            for mover, stock in results:
                data.append({
                    "rank": mover.rank,
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "value": mover.value,
                    "currency": stock.currency,
                })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "period": period,
                "category": category,
            }

        except Exception as e:
            logger.error(f"Top movers error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_top_dividend_payers(market: str = "all", sector: str = None, limit: int = 10):
        """Get stocks with highest dividend yields."""
        session = SessionLocal()
        try:
            exchanges = _resolve_market(market)

            query = session.query(Fundamental, Stock).join(
                Stock, Stock.id == Fundamental.stock_id
            ).filter(
                Stock.exchange.in_(exchanges),
                Fundamental.dividend_yield.isnot(None),
                Fundamental.dividend_yield > 0,
            )

            if sector:
                query = query.filter(Stock.sector.ilike(f"%{sector}%"))

            results = query.order_by(
                desc(Fundamental.dividend_yield)
            ).limit(limit).all()

            data = []
            for fund, stock in results:
                data.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "dividend_yield": fund.dividend_yield,
                    "pe_ratio": fund.pe_ratio,
                    "market_cap": fund.market_cap,
                    "currency": stock.currency,
                })

            return {"success": True, "data": data, "count": len(data), "market": market}

        except Exception as e:
            logger.error(f"Dividend payers error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_technical_signals(market: str = "all", signal_type: str = "oversold"):
        """
        Find stocks with specific technical signals.
        signal_type: 'oversold' (RSI<30), 'overbought' (RSI>70),
                     'golden_cross' (EMA20 > SMA200), 'death_cross' (EMA20 < SMA200)
        """
        session = SessionLocal()
        try:
            today = date.today()
            exchanges = _resolve_market(market)

            query = session.query(StockMetrics, Stock).join(
                Stock, Stock.id == StockMetrics.stock_id
            ).filter(
                Stock.exchange.in_(exchanges),
                StockMetrics.date == today,
            )

            if signal_type == "oversold":
                query = query.filter(StockMetrics.rsi_14 < 30).order_by(asc(StockMetrics.rsi_14))
            elif signal_type == "overbought":
                query = query.filter(StockMetrics.rsi_14 > 70).order_by(desc(StockMetrics.rsi_14))
            elif signal_type == "golden_cross":
                query = query.filter(
                    StockMetrics.ema_20.isnot(None),
                    StockMetrics.sma_200.isnot(None),
                    StockMetrics.ema_20 > StockMetrics.sma_200
                )
            elif signal_type == "death_cross":
                query = query.filter(
                    StockMetrics.ema_20.isnot(None),
                    StockMetrics.sma_200.isnot(None),
                    StockMetrics.ema_20 < StockMetrics.sma_200
                )
            elif signal_type == "high_volume":
                query = query.filter(StockMetrics.volume_ratio > 2.0).order_by(desc(StockMetrics.volume_ratio))
            elif signal_type == "near_52w_high":
                query = query.filter(StockMetrics.distance_52w_high > -5).order_by(desc(StockMetrics.distance_52w_high))
            elif signal_type == "near_52w_low":
                query = query.filter(StockMetrics.distance_52w_low < 5).order_by(asc(StockMetrics.distance_52w_low))

            results = query.limit(20).all()

            data = []
            for metrics, stock in results:
                entry = {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "rsi_14": metrics.rsi_14,
                    "ema_20": metrics.ema_20,
                    "sma_200": metrics.sma_200,
                    "volume_ratio": metrics.volume_ratio,
                    "perf_1d": metrics.perf_1d,
                }
                data.append(entry)

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "signal": signal_type,
                "market": market,
            }

        except Exception as e:
            logger.error(f"Technical signals error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()
