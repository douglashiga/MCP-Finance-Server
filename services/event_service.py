"""
Event Service — normalized event calendar queries for LLM-friendly workflows.
"""
import json
import logging
from datetime import date, datetime, timedelta

from dataloader.database import SessionLocal
from dataloader.models import MarketEvent

logger = logging.getLogger(__name__)

DEFAULT_MARKET = "sweden"
DEFAULT_LIMIT = 50
MAX_LIMIT = 300

MARKET_MAP = {
    "brazil": ["B3"],
    "b3": ["B3"],
    "sweden": ["OMX"],
    "omx": ["OMX"],
    "usa": ["NASDAQ", "NYSE"],
    "us": ["NASDAQ", "NYSE"],
    "nasdaq": ["NASDAQ"],
    "nyse": ["NYSE"],
    "all": ["B3", "OMX", "NASDAQ", "NYSE", "GLOBAL"],
}

IMPACT_ORDER = {"low": 1, "medium": 2, "high": 3}


class EventService:
    @staticmethod
    def _resolve_market(market: str):
        return MARKET_MAP.get((market or DEFAULT_MARKET).lower(), [market.upper()])

    @staticmethod
    def _limit(value, default=DEFAULT_LIMIT):
        if value is None:
            return default
        return max(1, min(int(value), MAX_LIMIT))

    @staticmethod
    def _to_list(value):
        if not value:
            return []
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return [str(value)]

    @staticmethod
    def _serialize(event: MarketEvent):
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "category": event.category,
            "subtype": event.subtype,
            "event_datetime_utc": event.event_datetime_utc.isoformat() if event.event_datetime_utc else None,
            "timezone": event.timezone,
            "market": event.market,
            "is_market_hours": event.is_market_hours,
            "is_pre_market": event.is_pre_market,
            "is_after_market": event.is_after_market,
            "ticker": event.ticker,
            "sector": event.sector,
            "country": event.country,
            "region": event.region,
            "affected_markets": EventService._to_list(event.affected_markets),
            "expected_volatility_impact": event.expected_volatility_impact,
            "systemic_risk_level": event.systemic_risk_level,
            "is_recurring": event.is_recurring,
            "confidence_score": event.confidence_score,
            "expected_eps": event.expected_eps,
            "previous_eps": event.previous_eps,
            "expected_revenue": event.expected_revenue,
            "previous_value": event.previous_value,
            "forecast_value": event.forecast_value,
            "actual_value": event.actual_value,
            "source": event.source,
        }

    @staticmethod
    def get_event_calendar(
        market: str = DEFAULT_MARKET,
        category: str = None,
        event_type: str = None,
        ticker: str = None,
        start_date: str = None,
        end_date: str = None,
        min_volatility_impact: str = "low",
        limit: int = DEFAULT_LIMIT,
    ):
        session = SessionLocal()
        try:
            exchanges = EventService._resolve_market(market)
            limit = EventService._limit(limit)

            start = datetime.fromisoformat(start_date) if start_date else datetime.utcnow() - timedelta(days=1)
            end = datetime.fromisoformat(end_date) if end_date else datetime.utcnow() + timedelta(days=180)

            q = session.query(MarketEvent).filter(
                MarketEvent.event_datetime_utc >= start,
                MarketEvent.event_datetime_utc <= end,
            )

            if market and market.lower() != "all":
                q = q.filter(MarketEvent.market.in_(exchanges))

            if category:
                q = q.filter(MarketEvent.category == category)
            if event_type:
                q = q.filter(MarketEvent.event_type == event_type)
            if ticker:
                t = ticker.upper().strip()
                q = q.filter(MarketEvent.ticker.ilike(f"%{t}%"))

            min_level = IMPACT_ORDER.get((min_volatility_impact or "low").lower(), 1)
            rows = q.order_by(MarketEvent.event_datetime_utc.asc()).limit(limit * 3).all()

            data = []
            for ev in rows:
                lvl = IMPACT_ORDER.get((ev.expected_volatility_impact or "low").lower(), 1)
                if lvl < min_level:
                    continue
                data.append(EventService._serialize(ev))
                if len(data) >= limit:
                    break

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "criteria": {
                    "market": market,
                    "category": category,
                    "event_type": event_type,
                    "ticker": ticker,
                    "start_date": start.isoformat(),
                    "end_date": end.isoformat(),
                    "min_volatility_impact": min_volatility_impact,
                    "limit": limit,
                },
                "empty_reason": None if data else "no_events_for_criteria",
            }
        except Exception as e:
            logger.error(f"Event calendar query error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_events_by_category(category: str, **kwargs):
        return EventService.get_event_calendar(category=category, **kwargs)

    @staticmethod
    def get_wheel_event_risk_window(
        ticker: str,
        market: str = DEFAULT_MARKET,
        days_ahead: int = 14,
        limit: int = 100,
    ):
        session = SessionLocal()
        try:
            exchanges = EventService._resolve_market(market)
            limit = EventService._limit(limit, default=100)

            now = datetime.utcnow()
            end = now + timedelta(days=max(1, int(days_ahead)))

            t = ticker.upper().strip()
            rows = session.query(MarketEvent).filter(
                MarketEvent.event_datetime_utc >= now,
                MarketEvent.event_datetime_utc <= end,
            ).filter(
                (MarketEvent.market.in_(exchanges)) |
                (MarketEvent.ticker.ilike(f"%{t}%"))
            ).order_by(MarketEvent.event_datetime_utc.asc()).limit(limit).all()

            data = []
            for ev in rows:
                vol = IMPACT_ORDER.get((ev.expected_volatility_impact or "low").lower(), 1)
                sys = IMPACT_ORDER.get((ev.systemic_risk_level or "low").lower(), 1)
                days_left = max(0.0, (ev.event_datetime_utc - now).total_seconds() / 86400.0)
                proximity = 3.0 if days_left <= 1 else (2.0 if days_left <= 3 else 1.0)
                score = round((vol * 0.6 + sys * 0.4) * proximity, 3)

                item = EventService._serialize(ev)
                item["days_until_event"] = round(days_left, 3)
                item["wheel_risk_score"] = score
                data.append(item)

            data.sort(key=lambda x: (-x["wheel_risk_score"], x["event_datetime_utc"] or ""))

            return {
                "success": True,
                "ticker": ticker,
                "market": market,
                "risk_window_days": int(days_ahead),
                "data": data,
                "count": len(data),
                "criteria": {
                    "ticker": ticker,
                    "market": market,
                    "days_ahead": days_ahead,
                    "limit": limit,
                },
                "empty_reason": None if data else "no_events_in_risk_window",
            }
        except Exception as e:
            logger.error(f"Wheel event risk query error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()
