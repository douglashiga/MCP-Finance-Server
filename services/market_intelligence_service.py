"""
Market Intelligence Service - local cached analytics compatible with finance-mcp style tools.

All methods read from local database tables/snapshots populated by loaders.
"""
import json
import math
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from dataloader.database import SessionLocal
from dataloader.models import (
    Stock,
    RealtimePrice,
    HistoricalPrice,
    Fundamental,
    Dividend,
    EarningsCalendar,
    StockMetrics,
    OptionMetric,
    CompanyProfile,
    RawYahooFundamental,
    StockIntelligenceSnapshot,
)

logger = logging.getLogger(__name__)


def _safe_float(v):
    try:
        if v is None:
            return None
        f = float(v)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except Exception:
        return None


def _loads_json(text_value: Optional[str], default):
    if not text_value:
        return default
    try:
        return json.loads(text_value)
    except Exception:
        return default


def _ema_series(values: List[float], period: int) -> List[float]:
    if len(values) < period:
        return []
    k = 2.0 / (period + 1)
    ema = values[0]
    out = [ema]
    for price in values[1:]:
        ema = (price * k) + (ema * (1.0 - k))
        out.append(ema)
    return out


def _std(values: List[float]) -> Optional[float]:
    if not values:
        return None
    m = sum(values) / len(values)
    var = sum((x - m) ** 2 for x in values) / len(values)
    return math.sqrt(var)


class MarketIntelligenceService:
    @staticmethod
    def _resolve_stock(session, symbol: str):
        sym = symbol.upper().strip()
        exact = session.query(Stock).filter(Stock.symbol == sym).first()
        if exact:
            return exact

        return session.query(Stock).filter(
            (Stock.symbol.ilike(f"{sym}.%")) |
            (Stock.symbol.ilike(f"%{sym}%"))
        ).order_by(Stock.symbol.asc()).first()

    @staticmethod
    def _latest_snapshot(session, stock_id: int):
        return session.query(StockIntelligenceSnapshot).filter(
            StockIntelligenceSnapshot.stock_id == stock_id
        ).order_by(StockIntelligenceSnapshot.fetched_at.desc()).first()

    @staticmethod
    def _period_to_days(period: str) -> Optional[int]:
        mapping = {
            "1mo": 31,
            "3mo": 93,
            "6mo": 186,
            "1y": 366,
            "2y": 731,
            "5y": 1826,
            "10y": 3652,
            "max": None,
        }
        return mapping.get((period or "1y").lower(), 366)

    @staticmethod
    def get_news(symbol: str, limit: int = 10) -> Dict[str, Any]:
        session = SessionLocal()
        try:
            limit = max(1, min(int(limit), 100))
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            snapshot = MarketIntelligenceService._latest_snapshot(session, stock.id)
            news = _loads_json(snapshot.news_json, []) if snapshot else []

            news = sorted(news, key=lambda x: x.get("provider_publish_time") or 0, reverse=True)
            data = news[:limit]
            return {
                "success": True,
                "symbol": stock.symbol,
                "news_count": len(news),
                "news": data,
                "as_of_datetime": snapshot.fetched_at.isoformat() if snapshot and snapshot.fetched_at else None,
                "source": "local_database",
                "empty_reason": None if data else "no_cached_news_for_symbol",
            }
        except Exception as e:
            logger.error(f"News query error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_institutional_holders(symbol: str, limit: int = 50) -> Dict[str, Any]:
        session = SessionLocal()
        try:
            limit = max(1, min(int(limit), 200))
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            snapshot = MarketIntelligenceService._latest_snapshot(session, stock.id)
            if not snapshot:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "institutional_holders": [],
                    "major_holders": {},
                    "empty_reason": "no_cached_holders_for_symbol",
                    "source": "local_database",
                }

            holders = _loads_json(snapshot.institutional_holders_json, [])
            major = _loads_json(snapshot.major_holders_json, {})
            holders = holders[:limit]

            return {
                "success": True,
                "symbol": stock.symbol,
                "institutional_holders": holders,
                "major_holders": major,
                "as_of_datetime": snapshot.fetched_at.isoformat() if snapshot.fetched_at else None,
                "source": "local_database",
                "empty_reason": None if holders or major else "no_cached_holders_for_symbol",
            }
        except Exception as e:
            logger.error(f"Institutional holders query error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_analyst_recommendations(symbol: str, limit: int = 50) -> Dict[str, Any]:
        session = SessionLocal()
        try:
            limit = max(1, min(int(limit), 300))
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            snapshot = MarketIntelligenceService._latest_snapshot(session, stock.id)
            if not snapshot:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "recommendations": [],
                    "upgrades_downgrades": [],
                    "empty_reason": "no_cached_recommendations_for_symbol",
                    "source": "local_database",
                }

            recommendations = _loads_json(snapshot.analyst_recommendations_json, [])
            upgrades = _loads_json(snapshot.upgrades_downgrades_json, [])

            recommendations = sorted(recommendations, key=lambda x: x.get("date") or "", reverse=True)[:limit]
            upgrades = sorted(upgrades, key=lambda x: x.get("date") or "", reverse=True)[:limit]

            return {
                "success": True,
                "symbol": stock.symbol,
                "recommendations": recommendations,
                "upgrades_downgrades": upgrades,
                "as_of_datetime": snapshot.fetched_at.isoformat() if snapshot.fetched_at else None,
                "source": "local_database",
                "empty_reason": None if recommendations or upgrades else "no_cached_recommendations_for_symbol",
            }
        except Exception as e:
            logger.error(f"Analyst recommendations query error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_financial_statements(symbol: str, statement_type: str = "all") -> Dict[str, Any]:
        valid = {
            "all",
            "income",
            "balance",
            "cashflow",
            "quarterly_income",
            "quarterly_balance",
            "quarterly_cashflow",
        }

        stype = (statement_type or "all").lower().strip()
        if stype not in valid:
            return {"success": False, "error": f"Invalid statement_type: {statement_type}"}

        session = SessionLocal()
        try:
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            snapshot = MarketIntelligenceService._latest_snapshot(session, stock.id)
            statements = _loads_json(snapshot.financial_statements_json, {}) if snapshot else {}

            response = {
                "success": True,
                "symbol": stock.symbol,
                "statement_type": stype,
                "income_statement": statements.get("income_statement", {}) if stype in {"all", "income"} else {},
                "balance_sheet": statements.get("balance_sheet", {}) if stype in {"all", "balance"} else {},
                "cash_flow": statements.get("cash_flow", {}) if stype in {"all", "cashflow"} else {},
                "quarterly_income_statement": statements.get("quarterly_income_statement", {}) if stype in {"all", "quarterly_income"} else {},
                "quarterly_balance_sheet": statements.get("quarterly_balance_sheet", {}) if stype in {"all", "quarterly_balance"} else {},
                "quarterly_cash_flow": statements.get("quarterly_cash_flow", {}) if stype in {"all", "quarterly_cashflow"} else {},
                "as_of_datetime": snapshot.fetched_at.isoformat() if snapshot and snapshot.fetched_at else None,
                "source": "local_database",
            }

            has_any = any(bool(response[k]) for k in [
                "income_statement", "balance_sheet", "cash_flow",
                "quarterly_income_statement", "quarterly_balance_sheet", "quarterly_cash_flow",
            ])
            response["empty_reason"] = None if has_any else "no_cached_financial_statements_for_symbol"
            return response
        except Exception as e:
            logger.error(f"Financial statements query error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_dividend_history(symbol: str, period: str = "2y") -> Dict[str, Any]:
        session = SessionLocal()
        try:
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            p = (period or "2y").lower().strip()
            if p == "1y":
                cutoff = date.today() - timedelta(days=365)
            elif p == "2y":
                cutoff = date.today() - timedelta(days=730)
            elif p == "5y":
                cutoff = date.today() - timedelta(days=1825)
            else:
                cutoff = None

            q = session.query(Dividend).filter(Dividend.stock_id == stock.id)
            if cutoff:
                q = q.filter(Dividend.ex_date >= cutoff)
            rows = q.order_by(Dividend.ex_date.asc()).all()

            history = [{
                "date": d.ex_date.isoformat() if d.ex_date else None,
                "dividend": _safe_float(d.amount),
            } for d in rows]

            amounts = [x["dividend"] for x in history if x.get("dividend") is not None]
            total_dividends = sum(amounts) if amounts else 0.0
            avg_dividend = (total_dividends / len(amounts)) if amounts else 0.0

            last = rows[-1] if rows else None
            return {
                "success": True,
                "symbol": stock.symbol,
                "period": p,
                "timestamp": datetime.utcnow().isoformat(),
                "dividend_history": history,
                "summary": {
                    "total_dividends": total_dividends,
                    "dividend_count": len(history),
                    "avg_dividend": avg_dividend,
                    "last_dividend": _safe_float(last.amount) if last else 0,
                    "last_dividend_date": last.ex_date.isoformat() if last and last.ex_date else None,
                    "last_dividend_yield": _safe_float(last.dividend_yield) if last else None,
                },
                "source": "local_database",
                "empty_reason": None if history else "no_dividend_history_for_symbol",
            }
        except Exception as e:
            logger.error(f"Dividend history query error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_options_data(symbol: str, expiration_date: str = None) -> Dict[str, Any]:
        session = SessionLocal()
        try:
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            query = session.query(OptionMetric).filter(OptionMetric.stock_id == stock.id)
            rows = query.order_by(OptionMetric.expiry.asc(), OptionMetric.strike.asc()).all()
            if not rows:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "message": "No options data available",
                    "expiration_dates": [],
                    "options_chain": {},
                    "empty_reason": "no_option_metrics_for_symbol",
                    "source": "local_database",
                }

            expirations = sorted({r.expiry for r in rows if r.expiry})
            if expiration_date:
                try:
                    target_exp = datetime.strptime(expiration_date, "%Y-%m-%d").date()
                except ValueError:
                    return {"success": False, "error": "expiration_date must be YYYY-MM-DD"}
                process_exp = [target_exp]
            else:
                process_exp = expirations[:5]

            latest_spot = session.query(RealtimePrice).filter(
                RealtimePrice.stock_id == stock.id
            ).order_by(RealtimePrice.last_updated.desc()).first()
            spot = latest_spot.price if latest_spot and latest_spot.price else None

            chain = {}
            max_updated = None
            for exp in process_exp:
                exp_rows = [r for r in rows if r.expiry == exp]
                calls = []
                puts = []

                for opt in exp_rows:
                    row = {
                        "strike": _safe_float(opt.strike),
                        "last_price": _safe_float(opt.last),
                        "bid": _safe_float(opt.bid),
                        "ask": _safe_float(opt.ask),
                        "change": None,
                        "percent_change": None,
                        "volume": opt.volume,
                        "open_interest": opt.open_interest,
                        "implied_volatility": _safe_float(opt.iv),
                        "in_the_money": bool((spot is not None) and ((opt.right == "CALL" and opt.strike <= spot) or (opt.right == "PUT" and opt.strike >= spot))),
                        "contract_symbol": opt.option_symbol,
                        "last_trade_date": opt.updated_at.isoformat() if opt.updated_at else None,
                    }

                    if opt.right == "CALL":
                        calls.append(row)
                    else:
                        puts.append(row)

                    if opt.updated_at and (max_updated is None or opt.updated_at > max_updated):
                        max_updated = opt.updated_at

                chain[exp.isoformat()] = {
                    "calls": calls,
                    "puts": puts,
                    "call_count": len(calls),
                    "put_count": len(puts),
                }

            return {
                "success": True,
                "symbol": stock.symbol,
                "timestamp": datetime.utcnow().isoformat(),
                "expiration_dates": [d.isoformat() for d in expirations],
                "options_chain": chain,
                "as_of_datetime": max_updated.isoformat() if max_updated else None,
                "source": "local_database",
            }
        except Exception as e:
            logger.error(f"Options data query error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_technical_analysis(symbol: str, period: str = "1y") -> Dict[str, Any]:
        session = SessionLocal()
        try:
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            days = MarketIntelligenceService._period_to_days(period)
            q = session.query(HistoricalPrice).filter(HistoricalPrice.stock_id == stock.id)
            if days is not None:
                cutoff = date.today() - timedelta(days=days)
                q = q.filter(HistoricalPrice.date >= cutoff)

            hist_rows = q.order_by(HistoricalPrice.date.asc()).all()
            closes = [float(r.close) for r in hist_rows if r.close and r.close > 0]
            highs = [float(r.high) for r in hist_rows if r.high]
            lows = [float(r.low) for r in hist_rows if r.low]
            volumes = [float(r.volume) for r in hist_rows if r.volume is not None]

            if len(closes) < 30:
                return {
                    "success": False,
                    "error": f"Insufficient historical data for technical analysis of {stock.symbol}",
                }

            sma20 = (sum(closes[-20:]) / 20.0) if len(closes) >= 20 else None
            sma50 = (sum(closes[-50:]) / 50.0) if len(closes) >= 50 else None
            sma200 = (sum(closes[-200:]) / 200.0) if len(closes) >= 200 else None

            ema12_series = _ema_series(closes, 12)
            ema26_series = _ema_series(closes, 26)
            ema12 = ema12_series[-1] if ema12_series else None
            ema26 = ema26_series[-1] if ema26_series else None

            deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
            recent_deltas = deltas[-14:] if len(deltas) >= 14 else deltas
            gains = [d for d in recent_deltas if d > 0]
            losses = [-d for d in recent_deltas if d < 0]
            avg_gain = (sum(gains) / len(recent_deltas)) if recent_deltas else 0.0
            avg_loss = (sum(losses) / len(recent_deltas)) if recent_deltas else 0.0
            if avg_loss == 0:
                rsi = 100.0
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            min_macd_len = min(len(ema12_series), len(ema26_series))
            macd_series = []
            if min_macd_len > 0:
                offset12 = len(ema12_series) - min_macd_len
                offset26 = len(ema26_series) - min_macd_len
                for i in range(min_macd_len):
                    macd_series.append(ema12_series[offset12 + i] - ema26_series[offset26 + i])

            signal_series = _ema_series(macd_series, 9) if len(macd_series) >= 9 else []
            macd_line = macd_series[-1] if macd_series else None
            signal_line = signal_series[-1] if signal_series else None
            histogram = (macd_line - signal_line) if (macd_line is not None and signal_line is not None) else None

            last20 = closes[-20:] if len(closes) >= 20 else closes
            bb_mid = (sum(last20) / len(last20)) if last20 else None
            bb_std = _std(last20)
            bb_upper = (bb_mid + (2 * bb_std)) if (bb_mid is not None and bb_std is not None) else None
            bb_lower = (bb_mid - (2 * bb_std)) if (bb_mid is not None and bb_std is not None) else None

            current_price = closes[-1]
            if bb_upper is not None and current_price > bb_upper:
                bb_position = "above_upper"
            elif bb_lower is not None and current_price < bb_lower:
                bb_position = "below_lower"
            else:
                bb_position = "middle"

            vol_sma_20 = (sum(volumes[-20:]) / 20.0) if len(volumes) >= 20 else None
            vol_ratio = (volumes[-1] / vol_sma_20) if (volumes and vol_sma_20 and vol_sma_20 > 0) else None

            recent_lows = lows[-50:] if len(lows) >= 50 else lows
            recent_highs = highs[-50:] if len(highs) >= 50 else highs
            support = min(recent_lows) if recent_lows else None
            resistance = max(recent_highs) if recent_highs else None

            return {
                "success": True,
                "symbol": stock.symbol,
                "period": period,
                "timestamp": datetime.utcnow().isoformat(),
                "indicators": {
                    "moving_averages": {
                        "sma_20": sma20,
                        "sma_50": sma50,
                        "sma_200": sma200,
                        "ema_12": ema12,
                        "ema_26": ema26,
                    },
                    "rsi": {
                        "current": rsi,
                        "signal": "oversold" if rsi < 30 else "overbought" if rsi > 70 else "neutral",
                    },
                    "macd": {
                        "macd_line": macd_line,
                        "signal_line": signal_line,
                        "histogram": histogram,
                        "signal": "bullish" if (histogram is not None and histogram > 0) else "bearish",
                    },
                    "bollinger_bands": {
                        "upper_band": bb_upper,
                        "middle_band": bb_mid,
                        "lower_band": bb_lower,
                        "position": bb_position,
                    },
                    "volume": {
                        "volume_sma_20": vol_sma_20,
                        "volume_ratio": vol_ratio,
                    },
                    "support_resistance": {
                        "support_level": support,
                        "resistance_level": resistance,
                        "current_price": current_price,
                    },
                },
                "source": "local_database",
            }
        except Exception as e:
            logger.error(f"Technical analysis error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_sector_performance(symbols: List[str]) -> Dict[str, Any]:
        if not symbols:
            return {"success": False, "error": "symbols cannot be empty"}

        session = SessionLocal()
        try:
            out = {
                "timestamp": datetime.utcnow().isoformat(),
                "symbols": symbols,
                "performance": {},
                "source": "local_database",
            }

            for requested_symbol in symbols:
                symbol_key = requested_symbol.upper().strip()
                stock = MarketIntelligenceService._resolve_stock(session, symbol_key)
                if not stock:
                    out["performance"][symbol_key] = {"error": "Stock not found"}
                    continue

                hist = session.query(HistoricalPrice).filter(
                    HistoricalPrice.stock_id == stock.id,
                    HistoricalPrice.close.isnot(None),
                ).order_by(HistoricalPrice.date.asc()).all()

                if len(hist) < 2:
                    out["performance"][stock.symbol] = {"error": "Insufficient historical data"}
                    continue

                closes = [float(r.close) for r in hist if r.close and r.close > 0]
                if len(closes) < 2:
                    out["performance"][stock.symbol] = {"error": "Insufficient historical data"}
                    continue

                current_price = closes[-1]
                start_price = closes[0]
                ytd_return = ((current_price - start_price) / start_price) * 100 if start_price > 0 else None

                rets = []
                for i in range(1, len(closes)):
                    prev = closes[i - 1]
                    cur = closes[i]
                    if prev > 0:
                        rets.append((cur / prev) - 1)
                vol = (_std(rets) * math.sqrt(252) * 100) if rets else None

                fund = session.query(Fundamental).filter(
                    Fundamental.stock_id == stock.id
                ).order_by(Fundamental.fetched_at.desc()).first()

                out["performance"][stock.symbol] = {
                    "company_name": stock.name,
                    "sector": stock.sector,
                    "current_price": current_price,
                    "ytd_return_percent": round(ytd_return, 2) if ytd_return is not None else None,
                    "volatility_percent": round(vol, 2) if vol is not None else None,
                    "market_cap": fund.market_cap if fund else None,
                    "pe_ratio": fund.trailing_pe if fund else None,
                    "beta": None,
                }

            return {"success": True, **out}
        except Exception as e:
            logger.error(f"Sector performance error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_comprehensive_stock_info(symbol: str) -> Dict[str, Any]:
        session = SessionLocal()
        try:
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            realtime = session.query(RealtimePrice).filter(
                RealtimePrice.stock_id == stock.id
            ).order_by(RealtimePrice.last_updated.desc()).first()

            fundamental = session.query(Fundamental).filter(
                Fundamental.stock_id == stock.id
            ).order_by(Fundamental.fetched_at.desc()).first()

            metrics = session.query(StockMetrics).filter(
                StockMetrics.stock_id == stock.id
            ).order_by(StockMetrics.date.desc()).first()

            latest_div = session.query(Dividend).filter(
                Dividend.stock_id == stock.id
            ).order_by(Dividend.ex_date.desc()).first()

            earnings = session.query(EarningsCalendar).filter(
                EarningsCalendar.stock_id == stock.id
            ).first()

            profile = session.query(CompanyProfile).filter(
                CompanyProfile.stock_id == stock.id
            ).first()

            snapshot = MarketIntelligenceService._latest_snapshot(session, stock.id)
            analyst_targets = _loads_json(snapshot.analyst_price_targets_json, {}) if snapshot else {}

            raw = session.query(RawYahooFundamental).filter(
                RawYahooFundamental.symbol == stock.symbol
            ).order_by(RawYahooFundamental.fetched_at.desc()).first()
            raw_info = _loads_json(raw.data, {}) if raw else {}

            return {
                "success": True,
                "symbol": stock.symbol,
                "timestamp": datetime.utcnow().isoformat(),
                "basic_info": {
                    "company_name": stock.name,
                    "short_name": raw_info.get("shortName") or stock.name,
                    "sector": stock.sector,
                    "industry": stock.industry,
                    "website": profile.website if profile else raw_info.get("website"),
                    "business_summary": profile.business_summary if profile else raw_info.get("longBusinessSummary"),
                    "employees": profile.employees if profile else raw_info.get("fullTimeEmployees"),
                    "city": profile.city if profile else raw_info.get("city"),
                    "country": profile.country if profile else stock.country,
                },
                "market_data": {
                    "market_cap": fundamental.market_cap if fundamental else None,
                    "enterprise_value": fundamental.enterprise_value if fundamental else None,
                    "current_price": realtime.price if realtime else None,
                    "previous_close": raw_info.get("regularMarketPreviousClose"),
                    "open": realtime.open if realtime else None,
                    "day_high": realtime.high if realtime else None,
                    "day_low": realtime.low if realtime else None,
                    "volume": realtime.volume if realtime else None,
                    "avg_volume_10days": metrics.avg_volume_10d if metrics else None,
                    "52_week_high": metrics.high_52w if metrics else None,
                    "52_week_low": metrics.low_52w if metrics else None,
                    "beta": raw_info.get("beta"),
                },
                "financial_metrics": {
                    "trailing_pe": fundamental.trailing_pe if fundamental else None,
                    "forward_pe": fundamental.forward_pe if fundamental else None,
                    "peg_ratio": fundamental.peg_ratio if fundamental else None,
                    "price_to_book": fundamental.price_to_book if fundamental else None,
                    "profit_margins": fundamental.net_margin if fundamental else None,
                    "operating_margins": fundamental.operating_margin if fundamental else None,
                    "return_on_equity": fundamental.roe if fundamental else None,
                    "return_on_assets": fundamental.roa if fundamental else None,
                    "debt_to_equity": fundamental.debt_to_equity if fundamental else None,
                    "current_ratio": fundamental.current_ratio if fundamental else None,
                },
                "dividend_info": {
                    "dividend_yield": latest_div.dividend_yield if latest_div else None,
                    "dividend_rate": latest_div.amount if latest_div else None,
                    "ex_dividend_date": latest_div.ex_date.isoformat() if latest_div and latest_div.ex_date else None,
                    "payout_ratio": latest_div.payout_ratio if latest_div else None,
                },
                "revenue_earnings": {
                    "total_revenue": fundamental.revenue if fundamental else None,
                    "revenue_growth": fundamental.revenue_growth if fundamental else None,
                    "trailing_eps": fundamental.trailing_eps if fundamental else None,
                    "forward_eps": fundamental.forward_eps if fundamental else None,
                    "next_earnings_date": earnings.earnings_date.isoformat() if earnings and earnings.earnings_date else None,
                    "next_earnings_avg": earnings.earnings_average if earnings else None,
                },
                "cash_flow": {
                    "total_cash": fundamental.total_cash if fundamental else None,
                    "total_debt": fundamental.total_debt if fundamental else None,
                    "free_cashflow": fundamental.free_cash_flow if fundamental else None,
                },
                "analyst_info": {
                    "recommendation_key": raw_info.get("recommendationKey"),
                    "recommendation_mean": raw_info.get("recommendationMean"),
                    "number_of_analyst_opinions": raw_info.get("numberOfAnalystOpinions"),
                    "target_high_price": analyst_targets.get("high"),
                    "target_low_price": analyst_targets.get("low"),
                    "target_mean_price": analyst_targets.get("mean"),
                    "target_median_price": analyst_targets.get("median"),
                },
                "as_of": {
                    "realtime": realtime.last_updated.isoformat() if realtime and realtime.last_updated else None,
                    "fundamentals": fundamental.fetched_at.isoformat() if fundamental and fundamental.fetched_at else None,
                    "intelligence": snapshot.fetched_at.isoformat() if snapshot and snapshot.fetched_at else None,
                    "metrics": metrics.date.isoformat() if metrics and metrics.date else None,
                },
                "source": "local_database",
            }

        except Exception as e:
            logger.error(f"Comprehensive stock info error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_historical_data_cached(symbol: str, period: str = "1y", interval: str = "1d") -> Dict[str, Any]:
        if interval not in {"1d", "1wk", "1mo"}:
            return {"success": False, "error": "Unsupported interval for local cache. Use 1d, 1wk or 1mo."}

        session = SessionLocal()
        try:
            stock = MarketIntelligenceService._resolve_stock(session, symbol)
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            days = MarketIntelligenceService._period_to_days(period)
            query = session.query(HistoricalPrice).filter(HistoricalPrice.stock_id == stock.id)
            if days is not None:
                query = query.filter(HistoricalPrice.date >= (date.today() - timedelta(days=days)))

            rows = query.order_by(HistoricalPrice.date.asc()).all()
            if not rows:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "period": period,
                    "interval": interval,
                    "data": [],
                    "summary": {"total_records": 0},
                    "empty_reason": "no_cached_historical_prices_for_symbol",
                    "source": "local_database",
                }

            data = []
            for r in rows:
                data.append({
                    "date": r.date.isoformat() if r.date else None,
                    "open": _safe_float(r.open),
                    "high": _safe_float(r.high),
                    "low": _safe_float(r.low),
                    "close": _safe_float(r.close),
                    "volume": r.volume,
                })

            return {
                "success": True,
                "symbol": stock.symbol,
                "period": period,
                "interval": interval,
                "data": data,
                "summary": {
                    "total_records": len(data),
                    "start_date": data[0]["date"],
                    "end_date": data[-1]["date"],
                    "price_range": {
                        "highest": max(d["high"] for d in data if d["high"] is not None),
                        "lowest": min(d["low"] for d in data if d["low"] is not None),
                        "avg_volume": int(sum(d["volume"] for d in data if d["volume"] is not None) / max(1, len([d for d in data if d["volume"] is not None]))),
                    },
                },
                "source": "local_database",
            }
        except Exception as e:
            logger.error(f"Historical cached query error for {symbol}: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()
