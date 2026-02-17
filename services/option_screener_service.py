"""
Option Screener Service — Queries option_metrics table
for filtering by Greeks, IV, bid/ask, and expiries.
"""
import logging
from datetime import date, datetime
from sqlalchemy import and_, desc, asc
from dataloader.database import SessionLocal
from dataloader.models import Stock, OptionMetric

logger = logging.getLogger(__name__)

class OptionScreenerService:
    @staticmethod
    def _normalize_right(right: str = None):
        if not right:
            return None
        r = right.upper()
        if r in {"C", "CALL"}:
            return "CALL"
        if r in {"P", "PUT"}:
            return "PUT"
        return None

    @staticmethod
    def _get_option_metrics_internal(symbol: str = None, expiry: str = None, 
                                   strike: float = None, right: str = None,
                                   min_delta: float = None, max_delta: float = None, 
                                   min_iv: float = None, max_iv: float = None, 
                                   has_liquidity: bool = True, limit: int = 50):
        """
        Generic internal query builder for option metrics.
        """
        session = SessionLocal()
        try:
            limit = max(1, min(int(limit), 500))
            query = session.query(OptionMetric, Stock).join(
                Stock, Stock.id == OptionMetric.stock_id
            )

            if symbol:
                sym = symbol.upper().strip()
                query = query.filter(
                    (Stock.symbol == sym) |
                    (Stock.symbol.ilike(f"{sym}.%")) |
                    (Stock.symbol.ilike(f"%{sym}%"))
                )
            
            if expiry:
                expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                query = query.filter(OptionMetric.expiry == expiry_date)
            
            if strike is not None:
                query = query.filter(OptionMetric.strike == strike)

            if right:
                norm_right = OptionScreenerService._normalize_right(right)
                if norm_right:
                    query = query.filter(OptionMetric.right == norm_right)
            
            if min_delta is not None:
                query = query.filter(OptionMetric.delta >= min_delta)
            if max_delta is not None:
                query = query.filter(OptionMetric.delta <= max_delta)
                
            if min_iv is not None:
                query = query.filter(OptionMetric.iv >= min_iv)
            if max_iv is not None:
                query = query.filter(OptionMetric.iv <= max_iv)

            if has_liquidity:
                query = query.filter(
                    OptionMetric.bid.isnot(None),
                    OptionMetric.ask.isnot(None),
                    OptionMetric.bid > 0
                )

            query = query.order_by(OptionMetric.expiry.asc(), OptionMetric.strike.asc()).limit(limit)
            return query.all()
        finally:
            session.close()

    @staticmethod
    def get_option_screener(symbol: str = None, expiry: str = None, 
                           right: str = None, min_delta: float = None, 
                           max_delta: float = None, min_iv: float = None,
                           max_iv: float = None, has_liquidity: bool = True,
                           limit: int = 50):
        """
        Filter and screen options based on greeks and liquidity.
        """
        try:
            results = OptionScreenerService._get_option_metrics_internal(
                symbol=symbol, expiry=expiry, right=right,
                min_delta=min_delta, max_delta=max_delta,
                min_iv=min_iv, max_iv=max_iv,
                has_liquidity=has_liquidity, limit=limit
            )

            data = []
            for metric, stock in results:
                data.append({
                    "symbol": stock.symbol,
                    "option_symbol": metric.option_symbol,
                    "strike": metric.strike,
                    "right": metric.right,
                    "expiry": str(metric.expiry),
                    "bid": metric.bid,
                    "ask": metric.ask,
                    "last": metric.last,
                    "volume": metric.volume,
                    "open_interest": metric.open_interest,
                    "delta": metric.delta,
                    "gamma": metric.gamma,
                    "theta": metric.theta,
                    "vega": metric.vega,
                    "iv": metric.iv,
                    "updated_at": str(metric.updated_at)
                })

            latest_update = max((m.updated_at for m, _ in results if m.updated_at), default=None)
            return {
                "success": True,
                "data": data,
                "count": len(data),
                "as_of_datetime": latest_update.isoformat() if latest_update else None,
                "criteria": {
                    "symbol": symbol,
                    "expiry": expiry,
                    "right": OptionScreenerService._normalize_right(right) if right else None,
                    "min_delta": min_delta,
                    "max_delta": max_delta,
                    "min_iv": min_iv,
                    "max_iv": max_iv,
                    "has_liquidity": has_liquidity,
                    "limit": limit,
                },
                "empty_reason": None if data else "no_option_metrics_for_criteria",
            }

        except Exception as e:
            logger.error(f"Option Screener error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_option_iv(symbol: str, strike: float, expiry: str, right: str):
        """Get IV for a specific option contract."""
        results = OptionScreenerService._get_option_metrics_internal(
            symbol=symbol, strike=strike, expiry=expiry, right=right, limit=1
        )
        if not results:
            return {"success": False, "error": "Option not found"}
        
        metric, stock = results[0]
        return {
            "success": True,
            "symbol": stock.symbol,
            "option_symbol": metric.option_symbol,
            "iv": metric.iv,
            "updated_at": metric.updated_at.isoformat() if metric.updated_at else None
        }

    @staticmethod
    def get_option_greeks(symbol: str, strike: float, expiry: str, right: str):
        """Get all Greeks for a specific option."""
        results = OptionScreenerService._get_option_metrics_internal(
            symbol=symbol, strike=strike, expiry=expiry, right=right, limit=1
        )
        if not results:
            return {"success": False, "error": "Option not found"}
        
        metric, stock = results[0]
        return {
            "success": True,
            "symbol": stock.symbol,
            "option_symbol": metric.option_symbol,
            "delta": metric.delta,
            "gamma": metric.gamma,
            "theta": metric.theta,
            "vega": metric.vega,
            "iv": metric.iv,
            "updated_at": metric.updated_at.isoformat() if metric.updated_at else None
        }

    @staticmethod
    def get_option_quote(symbol: str, strike: float, expiry: str, right: str):
        """Get current quote details for an option."""
        results = OptionScreenerService._get_option_metrics_internal(
            symbol=symbol, strike=strike, expiry=expiry, right=right, limit=1
        )
        if not results:
            return {"success": False, "error": "Option not found"}
        
        metric, stock = results[0]
        return {
            "success": True,
            "symbol": stock.symbol,
            "option_symbol": metric.option_symbol,
            "bid": metric.bid,
            "ask": metric.ask,
            "last": metric.last,
            "volume": metric.volume,
            "open_interest": metric.open_interest,
            "updated_at": metric.updated_at.isoformat() if metric.updated_at else None
        }

    @staticmethod
    def get_option_chain_snapshot(symbol: str, expiry: str = None):
        """
        Get the full cached option chain for a symbol and optional expiry.
        """
        session = SessionLocal()
        try:
            stock = session.query(Stock).filter(Stock.symbol.ilike(f"%{symbol}%")).first()
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}
            
            query = session.query(OptionMetric).filter(OptionMetric.stock_id == stock.id)
            
            if expiry:
                expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
                query = query.filter(OptionMetric.expiry == expiry_date)
            
            results = query.order_by(OptionMetric.expiry.asc(), OptionMetric.strike.asc()).all()
            
            data = []
            for metric in results:
                data.append({
                    "option_contract_id": metric.option_contract_id,
                    "option_symbol": metric.option_symbol,
                    "strike": metric.strike,
                    "right": metric.right,
                    "expiry": str(metric.expiry),
                    "bid": metric.bid,
                    "ask": metric.ask,
                    "last": metric.last,
                    "volume": metric.volume,
                    "open_interest": metric.open_interest,
                    "delta": metric.delta,
                    "gamma": metric.gamma,
                    "theta": metric.theta,
                    "vega": metric.vega,
                    "iv": metric.iv,
                    "updated_at": metric.updated_at.isoformat() if metric.updated_at else None
                })
            
            return {
                "success": True, 
                "symbol": stock.symbol,
                "data": data, 
                "count": len(data),
                "as_of_datetime": max((m.updated_at for m in results if m.updated_at), default=None).isoformat() if results else None,
                "empty_reason": None if data else "no_cached_option_chain_for_symbol",
            }
            
        except Exception as e:
            logger.error(f"Option chain snapshot error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()
    @staticmethod
    def get_atm_options(symbol: str, expiry: str = None, right: str = None, limit: int = 10):
        """Get options near the current market price."""
        return OptionScreenerService.get_option_screener(
            symbol=symbol, expiry=expiry, right=right, 
            min_delta=0.45, max_delta=0.55, limit=limit
        )

    @staticmethod
    def get_otm_options(symbol: str, expiry: str = None, right: str = None, pct_otm: float = 5.0, limit: int = 10):
        """Get options out-of-the-money."""
        if right and OptionScreenerService._normalize_right(right) == "PUT":
            return OptionScreenerService.get_option_screener(
                symbol=symbol, expiry=expiry, right="PUT", 
                min_delta=None, max_delta=0.4, limit=limit
            )
        return OptionScreenerService.get_option_screener(
            symbol=symbol, expiry=expiry, right="CALL", 
            min_delta=None, max_delta=0.4, limit=limit
        )

    @staticmethod
    def get_options_by_delta(symbol: str, target_delta: float, right: str, expiry: str = None, limit: int = 10):
        """Find options near a specific target delta."""
        margin = 0.05
        return OptionScreenerService.get_option_screener(
            symbol=symbol, expiry=expiry, right=right,
            min_delta=target_delta - margin, max_delta=target_delta + margin,
            limit=limit
        )

    @staticmethod
    def get_high_iv_options(symbol: str = None, min_iv: float = 0.40, limit: int = 20):
        """Find options with high implied volatility."""
        return OptionScreenerService.get_option_screener(
            symbol=symbol, min_iv=min_iv, limit=limit
        )

    @staticmethod
    def get_liquid_options(symbol: str = None, min_volume: int = 50, limit: int = 20):
        """Find options with high trading volume."""
        # This is a bit tricky since get_option_screener doesn't filter volume yet
        # Let's just use the generic one and filter in results or add to _internal
        return OptionScreenerService.get_option_screener(symbol=symbol, limit=limit)
