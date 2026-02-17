"""
Stock Screener Service — queries stock_metrics, market_movers, fundamentals and dividends.
All data comes from the local database (pre-calculated by ELT jobs).
"""
import logging
from sqlalchemy import and_, desc, asc, func
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

# Defaults for LLM-friendly calls
DEFAULT_LIMIT = 10
MAX_LIMIT = 100
DEFAULT_SIGNAL_LIMIT = 20
DEFAULT_MARKET = "sweden"
DEFAULT_PERIOD = "1D"
DEFAULT_SIGNAL = "oversold"


def _resolve_market(market: str) -> list:
    """Resolve market name to list of exchange codes."""
    return MARKET_MAP.get((market or DEFAULT_MARKET).lower(), [market.upper()])


def _normalize_limit(limit: int, default: int = DEFAULT_LIMIT) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), MAX_LIMIT))


class ScreenerService:
    @staticmethod
    def _latest_metrics_date(session):
        return session.query(func.max(StockMetrics.date)).scalar()

    @staticmethod
    def _latest_fundamental_subquery(session):
        return session.query(
            Fundamental.stock_id.label("stock_id"),
            func.max(Fundamental.fetched_at).label("max_fetched_at")
        ).group_by(Fundamental.stock_id).subquery()

    @staticmethod
    def _latest_dividend_subquery(session):
        return session.query(
            Dividend.stock_id.label("stock_id"),
            func.max(Dividend.ex_date).label("max_ex_date")
        ).group_by(Dividend.stock_id).subquery()

    @staticmethod
    def get_stock_screener(market: str = DEFAULT_MARKET, sector: str = None,
                           sort_by: str = "perf_1d", limit: int = 50):
        """Stock screener with filters. Returns stocks with all metrics."""
        session = SessionLocal()
        try:
            exchanges = _resolve_market(market)
            market = market or DEFAULT_MARKET
            normalized_limit = _normalize_limit(limit, default=50)
            as_of_date = ScreenerService._latest_metrics_date(session)
            if not as_of_date:
                return {
                    "success": True,
                    "data": [],
                    "count": 0,
                    "market": market,
                    "as_of_date": None,
                    "criteria": {"market": market, "sector": sector, "sort_by": sort_by, "limit": normalized_limit},
                    "empty_reason": "no_metrics_data_available",
                }

            query = session.query(StockMetrics, Stock).join(
                Stock, Stock.id == StockMetrics.stock_id
            ).filter(
                Stock.exchange.in_(exchanges),
                StockMetrics.date == as_of_date
            )

            if sector:
                query = query.filter(Stock.sector.ilike(f"%{sector}%"))

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
            query = query.order_by(desc(sort_col)).limit(normalized_limit)

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

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "as_of_date": as_of_date.isoformat(),
                "criteria": {"market": market, "sector": sector, "sort_by": sort_by, "limit": normalized_limit},
                "empty_reason": None if data else "no_matches_for_criteria",
                "defaults": {"sort_by": "perf_1d", "limit": 50},
            }

        except Exception as e:
            logger.error(f"Screener error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_top_movers(market: str = DEFAULT_MARKET, period: str = DEFAULT_PERIOD,
                       category: str = "top_gainers", limit: int = DEFAULT_LIMIT):
        """Get top gainers, losers, or most active stocks."""
        session = SessionLocal()
        try:
            market = market or DEFAULT_MARKET
            exchanges = _resolve_market(market)
            limit = _normalize_limit(limit)
            period = (period or DEFAULT_PERIOD).upper()
            category = category or "top_gainers"

            results = session.query(MarketMover, Stock).join(
                Stock, Stock.id == MarketMover.stock_id
            ).filter(
                MarketMover.market.in_(exchanges),
                MarketMover.period == period,
                MarketMover.category == category,
            ).order_by(MarketMover.rank).limit(limit).all()

            data = []
            latest_calculated = None
            for mover, stock in results:
                latest_calculated = mover.calculated_at if not latest_calculated else max(latest_calculated, mover.calculated_at)
                data.append({
                    "rank": mover.rank,
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "value": mover.value,
                    "metric_name": "activity_value" if category == "most_active" else "performance_pct",
                    "metric_value": mover.value,
                    "currency": stock.currency,
                    "calculated_at": mover.calculated_at.isoformat() if mover.calculated_at else None,
                })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "period": period,
                "category": category,
                "as_of_datetime": latest_calculated.isoformat() if latest_calculated else None,
                "criteria": {"market": market, "period": period, "category": category, "limit": limit},
                "empty_reason": None if data else "no_market_mover_data_for_criteria",
                "defaults": {"period": DEFAULT_PERIOD, "limit": DEFAULT_LIMIT},
            }

        except Exception as e:
            logger.error(f"Top movers error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_top_dividend_payers(market: str = DEFAULT_MARKET, sector: str = None, limit: int = DEFAULT_LIMIT):
        """Get stocks with highest latest dividend yield from dividends table."""
        session = SessionLocal()
        try:
            market = market or DEFAULT_MARKET
            exchanges = _resolve_market(market)
            limit = _normalize_limit(limit)

            latest_dividend_sq = ScreenerService._latest_dividend_subquery(session)
            latest_fund_sq = ScreenerService._latest_fundamental_subquery(session)

            query = session.query(Dividend, Stock, Fundamental).join(
                latest_dividend_sq,
                and_(
                    latest_dividend_sq.c.stock_id == Dividend.stock_id,
                    latest_dividend_sq.c.max_ex_date == Dividend.ex_date,
                ),
            ).join(
                Stock, Stock.id == Dividend.stock_id
            ).outerjoin(
                latest_fund_sq,
                latest_fund_sq.c.stock_id == Stock.id,
            ).outerjoin(
                Fundamental,
                and_(
                    Fundamental.stock_id == latest_fund_sq.c.stock_id,
                    Fundamental.fetched_at == latest_fund_sq.c.max_fetched_at,
                ),
            ).filter(
                Stock.exchange.in_(exchanges),
                Dividend.dividend_yield.isnot(None),
                Dividend.dividend_yield > 0,
            )

            if sector:
                query = query.filter(Stock.sector.ilike(f"%{sector}%"))

            results = query.order_by(desc(Dividend.dividend_yield)).limit(limit).all()
            data = []
            latest_ex_date = None
            for div, stock, fund in results:
                latest_ex_date = div.ex_date if not latest_ex_date else max(latest_ex_date, div.ex_date)
                data.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "currency": stock.currency,
                    "dividend_yield": div.dividend_yield,
                    "metric_name": "dividend_yield",
                    "metric_value": div.dividend_yield,
                    "payout_ratio": div.payout_ratio,
                    "ex_date": div.ex_date.isoformat() if div.ex_date else None,
                    "trailing_pe": fund.trailing_pe if fund else None,
                    "market_cap": fund.market_cap if fund else None,
                })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "as_of_date": latest_ex_date.isoformat() if latest_ex_date else None,
                "criteria": {"market": market, "sector": sector, "limit": limit},
                "empty_reason": None if data else "no_dividend_data_for_criteria",
                "defaults": {"limit": DEFAULT_LIMIT},
            }

        except Exception as e:
            logger.error(f"Dividend payers error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_technical_signals(market: str = DEFAULT_MARKET, signal_type: str = DEFAULT_SIGNAL,
                              limit: int = DEFAULT_SIGNAL_LIMIT):
        """
        Find stocks with specific technical signals.
        signal_type: oversold, overbought, golden_cross, death_cross, high_volume,
                     near_52w_high, near_52w_low
        """
        session = SessionLocal()
        try:
            as_of_date = ScreenerService._latest_metrics_date(session)
            market = market or DEFAULT_MARKET
            limit = _normalize_limit(limit, default=DEFAULT_SIGNAL_LIMIT)
            if not as_of_date:
                return {
                    "success": True,
                    "data": [],
                    "count": 0,
                    "signal": signal_type,
                    "market": market,
                    "as_of_date": None,
                    "criteria": {"market": market, "signal_type": signal_type, "limit": limit},
                    "empty_reason": "no_metrics_data_available",
                }

            exchanges = _resolve_market(market)

            query = session.query(StockMetrics, Stock).join(
                Stock, Stock.id == StockMetrics.stock_id
            ).filter(
                Stock.exchange.in_(exchanges),
                StockMetrics.date == as_of_date,
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
                ).order_by(desc(StockMetrics.perf_1d))
            elif signal_type == "death_cross":
                query = query.filter(
                    StockMetrics.ema_20.isnot(None),
                    StockMetrics.sma_200.isnot(None),
                    StockMetrics.ema_20 < StockMetrics.sma_200
                ).order_by(asc(StockMetrics.perf_1d))
            elif signal_type == "high_volume":
                query = query.filter(StockMetrics.volume_ratio > 2.0).order_by(desc(StockMetrics.volume_ratio))
            elif signal_type == "near_52w_high":
                query = query.filter(StockMetrics.distance_52w_high > -5).order_by(desc(StockMetrics.distance_52w_high))
            elif signal_type == "near_52w_low":
                query = query.filter(StockMetrics.distance_52w_low < 5).order_by(asc(StockMetrics.distance_52w_low))

            results = query.limit(limit).all()
            data = []
            for metrics, stock in results:
                data.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "rsi_14": metrics.rsi_14,
                    "ema_20": metrics.ema_20,
                    "sma_200": metrics.sma_200,
                    "volume_ratio": metrics.volume_ratio,
                    "perf_1d": metrics.perf_1d,
                    "distance_52w_high": metrics.distance_52w_high,
                    "distance_52w_low": metrics.distance_52w_low,
                })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "signal": signal_type,
                "market": market,
                "as_of_date": as_of_date.isoformat(),
                "criteria": {"market": market, "signal_type": signal_type, "limit": limit},
                "empty_reason": None if data else "no_matches_for_signal",
                "defaults": {"signal_type": DEFAULT_SIGNAL, "limit": DEFAULT_SIGNAL_LIMIT},
            }

        except Exception as e:
            logger.error(f"Technical signals error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_rsi_leaders(market: str = DEFAULT_MARKET, direction: str = "high", limit: int = DEFAULT_LIMIT):
        """Get highest or lowest RSI stocks."""
        session = SessionLocal()
        try:
            as_of_date = ScreenerService._latest_metrics_date(session)
            market = market or DEFAULT_MARKET
            limit = _normalize_limit(limit)
            direction = (direction or "high").lower()
            if not as_of_date:
                return {
                    "success": True,
                    "data": [],
                    "count": 0,
                    "market": market,
                    "as_of_date": None,
                    "criteria": {"market": market, "direction": direction, "limit": limit},
                    "empty_reason": "no_metrics_data_available",
                }

            exchanges = _resolve_market(market)

            query = session.query(StockMetrics, Stock).join(
                Stock, Stock.id == StockMetrics.stock_id
            ).filter(
                Stock.exchange.in_(exchanges),
                StockMetrics.date == as_of_date,
                StockMetrics.rsi_14.isnot(None),
            )
            query = query.order_by(desc(StockMetrics.rsi_14) if direction == "high" else asc(StockMetrics.rsi_14))

            rows = query.limit(limit).all()
            data = [{
                "symbol": stock.symbol,
                "name": stock.name,
                "exchange": stock.exchange,
                "sector": stock.sector,
                "rsi_14": metrics.rsi_14,
                "perf_1d": metrics.perf_1d,
                "volume_ratio": metrics.volume_ratio,
            } for metrics, stock in rows]

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "direction": direction,
                "as_of_date": as_of_date.isoformat(),
                "criteria": {"market": market, "direction": direction, "limit": limit},
                "empty_reason": None if data else "no_rsi_data_for_criteria",
                "defaults": {"direction": "high", "limit": DEFAULT_LIMIT},
            }
        except Exception as e:
            logger.error(f"RSI leaders error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_fundamental_leaders(market: str = DEFAULT_MARKET, metric: str = "market_cap",
                                limit: int = DEFAULT_LIMIT, sector: str = None):
        """
        Rank stocks by latest fundamental metrics.
        Supported metric: market_cap, trailing_pe, forward_pe, roe, net_margin, revenue, free_cash_flow, debt_to_equity
        """
        session = SessionLocal()
        try:
            market = market or DEFAULT_MARKET
            exchanges = _resolve_market(market)
            limit = _normalize_limit(limit)
            latest_fund_sq = ScreenerService._latest_fundamental_subquery(session)

            metric_map = {
                "market_cap": Fundamental.market_cap,
                "trailing_pe": Fundamental.trailing_pe,
                "forward_pe": Fundamental.forward_pe,
                "roe": Fundamental.roe,
                "net_margin": Fundamental.net_margin,
                "revenue": Fundamental.revenue,
                "free_cash_flow": Fundamental.free_cash_flow,
                "debt_to_equity": Fundamental.debt_to_equity,
            }
            order_col = metric_map.get(metric, Fundamental.market_cap)
            metric = metric if metric in metric_map else "market_cap"
            order_direction = asc(order_col) if metric in {"trailing_pe", "forward_pe", "debt_to_equity"} else desc(order_col)

            query = session.query(Fundamental, Stock).join(
                latest_fund_sq,
                and_(
                    latest_fund_sq.c.stock_id == Fundamental.stock_id,
                    latest_fund_sq.c.max_fetched_at == Fundamental.fetched_at,
                ),
            ).join(
                Stock, Stock.id == Fundamental.stock_id
            ).filter(
                Stock.exchange.in_(exchanges),
                order_col.isnot(None),
            )

            if sector:
                query = query.filter(Stock.sector.ilike(f"%{sector}%"))

            rows = query.order_by(order_direction).limit(limit).all()

            data = []
            latest_fetch = None
            for fund, stock in rows:
                latest_fetch = fund.fetched_at if not latest_fetch else max(latest_fetch, fund.fetched_at)
                data.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": stock.sector,
                    "currency": stock.currency,
                    "metric": metric,
                    "metric_name": metric,
                    "metric_value": getattr(fund, metric),
                    "value": getattr(fund, metric if metric in metric_map else "market_cap"),
                    "market_cap": fund.market_cap,
                    "trailing_pe": fund.trailing_pe,
                    "forward_pe": fund.forward_pe,
                    "roe": fund.roe,
                    "net_margin": fund.net_margin,
                    "debt_to_equity": fund.debt_to_equity,
                    "free_cash_flow": fund.free_cash_flow,
                    "fetched_at": fund.fetched_at.isoformat() if fund.fetched_at else None,
                })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "metric": metric,
                "as_of_datetime": latest_fetch.isoformat() if latest_fetch else None,
                "criteria": {"market": market, "metric": metric, "limit": limit, "sector": sector},
                "empty_reason": None if data else "no_fundamental_data_for_criteria",
                "defaults": {"metric": "market_cap", "limit": DEFAULT_LIMIT},
            }
        except Exception as e:
            logger.error(f"Fundamental leaders error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()
    @staticmethod
    def get_oversold_stocks(market: str = DEFAULT_MARKET, limit: int = DEFAULT_LIMIT):
        """Get stocks with RSI < 30."""
        return ScreenerService.get_technical_signals(market=market, signal_type="oversold", limit=limit)

    @staticmethod
    def get_overbought_stocks(market: str = DEFAULT_MARKET, limit: int = DEFAULT_LIMIT):
        """Get stocks with RSI > 70."""
        return ScreenerService.get_technical_signals(market=market, signal_type="overbought", limit=limit)

    @staticmethod
    def get_low_pe_stocks(market: str = DEFAULT_MARKET, limit: int = DEFAULT_LIMIT, sector: str = None):
        """Get stocks with lowest Trailing PE."""
        return ScreenerService.get_fundamental_leaders(market=market, metric="trailing_pe", limit=limit, sector=sector)

    @staticmethod
    def get_high_market_cap_stocks(market: str = DEFAULT_MARKET, limit: int = DEFAULT_LIMIT, sector: str = None):
        """Get stocks with highest Market Cap."""
        return ScreenerService.get_fundamental_leaders(market=market, metric="market_cap", limit=limit, sector=sector)
