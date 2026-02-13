#!/usr/bin/env python3
"""
Load Event Calendar — unified normalized events for LLM queries.

Sources:
- Corporate: earnings_events, earnings_calendar, dividends
- Market Structure (derived): option expirations, triple witching, index rebalance windows
- Manual feed: dataloader/data/manual_events.json (macro/monetary/geopolitical)
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import and_

from dataloader.database import SessionLocal, init_db
from dataloader.models import (
    Dividend,
    EarningsCalendar,
    EarningsEvent,
    MarketEvent,
    Stock,
)


CATEGORY_VALUES = {
    "corporate",
    "macro",
    "monetary_policy",
    "geopolitical",
    "market_structure",
}

IMPACT_VALUES = {"low", "medium", "high"}

MANUAL_EVENTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
    "manual_events.json",
)


def _dt_utc(value):
    if isinstance(value, datetime):
        return value
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None

    if parsed.tzinfo is not None:
        return parsed.astimezone(tz=None).replace(tzinfo=None)
    return parsed


def _date_to_dt(value: date, hour: int = 13):
    if not value:
        return None
    return datetime(value.year, value.month, value.day, hour, 0, 0)


def _event_id(parts):
    key = "|".join(str(p) for p in parts)
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:24]


def _normalize_impact(value, default="medium"):
    v = (value or default).lower().strip()
    return v if v in IMPACT_VALUES else default


def _is_market_hours(dt: datetime, market: str):
    if not dt:
        return False, False, False

    h = dt.hour
    # Simplified UTC windows
    if market == "OMX":
        # 08:00-16:30 UTC approx
        in_hours = 8 <= h < 17
    elif market in {"NASDAQ", "NYSE"}:
        # 14:00-21:00 UTC approx
        in_hours = 14 <= h < 21
    elif market == "B3":
        # 13:00-20:00 UTC approx
        in_hours = 13 <= h < 20
    else:
        in_hours = False

    pre = not in_hours and h < (8 if market == "OMX" else 14)
    after = not in_hours and not pre
    return in_hours, pre, after


def _upsert_event(session, payload):
    existing = session.query(MarketEvent).filter(MarketEvent.event_id == payload["event_id"]).first()
    if existing:
        for k, v in payload.items():
            setattr(existing, k, v)
        return False
    session.add(MarketEvent(**payload))
    return True


def _build_corporate_events(session, today: date, end_date: date):
    created = 0

    # Curated earnings events
    earnings = session.query(EarningsEvent, Stock).join(
        Stock, Stock.id == EarningsEvent.stock_id
    ).filter(
        EarningsEvent.event_date >= today,
        EarningsEvent.event_date <= end_date,
    ).all()

    for ev, stock in earnings:
        event_dt = ev.event_datetime or _date_to_dt(ev.event_date, hour=12)
        in_hours, pre, after = _is_market_hours(event_dt, stock.exchange)
        event = {
            "event_id": _event_id(["earnings", stock.symbol, ev.event_date]),
            "event_type": "earnings",
            "category": "corporate",
            "subtype": "quarterly_report",
            "event_datetime_utc": event_dt,
            "timezone": "UTC",
            "market": stock.exchange,
            "is_market_hours": in_hours,
            "is_pre_market": pre,
            "is_after_market": after,
            "ticker": stock.symbol,
            "sector": stock.sector,
            "country": stock.country,
            "region": "Europe" if stock.country == "Sweden" else None,
            "affected_markets": json.dumps([stock.exchange]),
            "expected_volatility_impact": "high",
            "systemic_risk_level": "medium",
            "is_recurring": True,
            "confidence_score": ev.quality_score if ev.quality_score is not None else 0.8,
            "expected_eps": ev.eps_estimate,
            "previous_eps": None,
            "expected_revenue": ev.revenue_estimate,
            "source": "earnings_events",
            "payload": json.dumps({
                "eps_actual": ev.eps_actual,
                "surprise_percent": ev.surprise_percent,
                "revenue_actual": ev.revenue_actual,
                "curated_source": ev.source,
            }),
        }
        if _upsert_event(session, event):
            created += 1

        call_dt = event_dt + timedelta(hours=1)
        in_hours, pre, after = _is_market_hours(call_dt, stock.exchange)
        call_event = {
            **event,
            "event_id": _event_id(["earnings_call", stock.symbol, ev.event_date]),
            "event_type": "earnings_call",
            "subtype": "conference_call",
            "event_datetime_utc": call_dt,
            "is_market_hours": in_hours,
            "is_pre_market": pre,
            "is_after_market": after,
            "expected_volatility_impact": "medium",
        }
        if _upsert_event(session, call_event):
            created += 1

    # Earnings calendar fallback
    cal_rows = session.query(EarningsCalendar, Stock).join(
        Stock, Stock.id == EarningsCalendar.stock_id
    ).filter(
        EarningsCalendar.earnings_date >= today,
        EarningsCalendar.earnings_date <= end_date,
    ).all()

    for cal, stock in cal_rows:
        event_dt = _date_to_dt(cal.earnings_date, hour=12)
        in_hours, pre, after = _is_market_hours(event_dt, stock.exchange)
        event = {
            "event_id": _event_id(["earnings_calendar", stock.symbol, cal.earnings_date]),
            "event_type": "earnings",
            "category": "corporate",
            "subtype": "calendar_event",
            "event_datetime_utc": event_dt,
            "timezone": "UTC",
            "market": stock.exchange,
            "is_market_hours": in_hours,
            "is_pre_market": pre,
            "is_after_market": after,
            "ticker": stock.symbol,
            "sector": stock.sector,
            "country": stock.country,
            "region": "Europe" if stock.country == "Sweden" else None,
            "affected_markets": json.dumps([stock.exchange]),
            "expected_volatility_impact": "high",
            "systemic_risk_level": "medium",
            "is_recurring": True,
            "confidence_score": 0.65,
            "expected_eps": cal.earnings_average,
            "expected_revenue": cal.revenue_average,
            "source": "earnings_calendar",
            "payload": json.dumps({
                "earnings_low": cal.earnings_low,
                "earnings_high": cal.earnings_high,
                "revenue_low": cal.revenue_low,
                "revenue_high": cal.revenue_high,
            }),
        }
        if _upsert_event(session, event):
            created += 1

    # Dividend ex-dates (and projected payment date proxy)
    div_rows = session.query(Dividend, Stock).join(
        Stock, Stock.id == Dividend.stock_id
    ).filter(
        Dividend.ex_date >= today,
        Dividend.ex_date <= end_date,
    ).all()

    for div, stock in div_rows:
        ex_dt = _date_to_dt(div.ex_date, hour=10)
        in_hours, pre, after = _is_market_hours(ex_dt, stock.exchange)
        ex_event = {
            "event_id": _event_id(["div_ex", stock.symbol, div.ex_date]),
            "event_type": "dividend_ex_date",
            "category": "corporate",
            "subtype": "dividend",
            "event_datetime_utc": ex_dt,
            "timezone": "UTC",
            "market": stock.exchange,
            "is_market_hours": in_hours,
            "is_pre_market": pre,
            "is_after_market": after,
            "ticker": stock.symbol,
            "sector": stock.sector,
            "country": stock.country,
            "region": "Europe" if stock.country == "Sweden" else None,
            "affected_markets": json.dumps([stock.exchange]),
            "expected_volatility_impact": "medium",
            "systemic_risk_level": "low",
            "is_recurring": True,
            "confidence_score": 0.85,
            "source": "dividends",
            "payload": json.dumps({
                "amount": div.amount,
                "dividend_yield": div.dividend_yield,
                "payout_ratio": div.payout_ratio,
            }),
        }
        if _upsert_event(session, ex_event):
            created += 1

        pay_dt = ex_dt + timedelta(days=30)
        in_hours, pre, after = _is_market_hours(pay_dt, stock.exchange)
        pay_event = {
            **ex_event,
            "event_id": _event_id(["div_pay", stock.symbol, div.ex_date]),
            "event_type": "dividend_payment_date",
            "subtype": "projected_payment_date",
            "event_datetime_utc": pay_dt,
            "is_market_hours": in_hours,
            "is_pre_market": pre,
            "is_after_market": after,
            "confidence_score": 0.4,
            "payload": json.dumps({
                "note": "Projected as ex-date + 30 days (proxy)",
                "amount": div.amount,
                "dividend_yield": div.dividend_yield,
            }),
        }
        if _upsert_event(session, pay_event):
            created += 1

    return created


def _third_friday(year: int, month: int):
    d = date(year, month, 1)
    # Find first Friday
    while d.weekday() != 4:
        d += timedelta(days=1)
    # third Friday
    return d + timedelta(days=14)


def _build_market_structure_events(session, today: date, end_date: date):
    created = 0

    # Option expiration + triple witching for next months
    d = date(today.year, today.month, 1)
    while d <= end_date:
        tf = _third_friday(d.year, d.month)
        if today <= tf <= end_date:
            for market in ["OMX", "NASDAQ", "NYSE"]:
                dt = _date_to_dt(tf, hour=15)
                in_hours, pre, after = _is_market_hours(dt, market)

                event = {
                    "event_id": _event_id(["op_exp", market, tf]),
                    "event_type": "option_expiration",
                    "category": "market_structure",
                    "subtype": "monthly",
                    "event_datetime_utc": dt,
                    "timezone": "UTC",
                    "market": market,
                    "is_market_hours": in_hours,
                    "is_pre_market": pre,
                    "is_after_market": after,
                    "ticker": None,
                    "sector": None,
                    "country": "Sweden" if market == "OMX" else "USA",
                    "region": "Europe" if market == "OMX" else "North America",
                    "affected_markets": json.dumps([market]),
                    "expected_volatility_impact": "medium",
                    "systemic_risk_level": "medium",
                    "is_recurring": True,
                    "confidence_score": 0.95,
                    "source": "derived_calendar",
                    "payload": json.dumps({"rule": "third_friday"}),
                }
                if _upsert_event(session, event):
                    created += 1

                if d.month in {3, 6, 9, 12}:
                    tw = {
                        **event,
                        "event_id": _event_id(["triple_witching", market, tf]),
                        "event_type": "triple_witching",
                        "subtype": "quarterly",
                        "expected_volatility_impact": "high",
                        "systemic_risk_level": "high",
                    }
                    if _upsert_event(session, tw):
                        created += 1

        # Next month
        if d.month == 12:
            d = date(d.year + 1, 1, 1)
        else:
            d = date(d.year, d.month + 1, 1)

    # Simple index rebalance marker (last business day each quarter)
    for month in [3, 6, 9, 12]:
        year = today.year
        for y in [year, year + 1]:
            d = date(y, month, 28)
            while d.month == month:
                d += timedelta(days=1)
            d -= timedelta(days=1)
            while d.weekday() >= 5:  # weekend
                d -= timedelta(days=1)

            if not (today <= d <= end_date):
                continue

            for market in ["OMX", "NASDAQ", "NYSE"]:
                dt = _date_to_dt(d, hour=15)
                in_hours, pre, after = _is_market_hours(dt, market)
                event = {
                    "event_id": _event_id(["index_rebalance", market, d]),
                    "event_type": "index_rebalance",
                    "category": "market_structure",
                    "subtype": "quarterly",
                    "event_datetime_utc": dt,
                    "timezone": "UTC",
                    "market": market,
                    "is_market_hours": in_hours,
                    "is_pre_market": pre,
                    "is_after_market": after,
                    "ticker": None,
                    "sector": None,
                    "country": "Sweden" if market == "OMX" else "USA",
                    "region": "Europe" if market == "OMX" else "North America",
                    "affected_markets": json.dumps([market]),
                    "expected_volatility_impact": "medium",
                    "systemic_risk_level": "medium",
                    "is_recurring": True,
                    "confidence_score": 0.6,
                    "source": "derived_calendar",
                    "payload": json.dumps({"note": "Quarterly rebalance window"}),
                }
                if _upsert_event(session, event):
                    created += 1

    return created


def _build_manual_events(session, today: date, end_date: date):
    if not os.path.exists(MANUAL_EVENTS_PATH):
        return 0

    created = 0
    with open(MANUAL_EVENTS_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    for item in raw:
        category = (item.get("category") or "macro").strip().lower()
        if category not in CATEGORY_VALUES:
            continue

        dt = _dt_utc(item.get("event_datetime_utc"))
        if not dt:
            continue

        if not (today <= dt.date() <= end_date):
            continue

        market = item.get("market") or "GLOBAL"
        in_hours, pre, after = _is_market_hours(dt, market)

        event_type = (item.get("event_type") or "unknown_event").strip().lower()
        payload = {
            "event_id": item.get("event_id") or _event_id(["manual", category, event_type, dt.isoformat(), item.get("ticker")]),
            "event_type": event_type,
            "category": category,
            "subtype": item.get("subtype"),
            "event_datetime_utc": dt,
            "timezone": item.get("timezone") or "UTC",
            "market": market,
            "is_market_hours": in_hours,
            "is_pre_market": pre,
            "is_after_market": after,
            "ticker": item.get("ticker"),
            "sector": item.get("sector"),
            "country": item.get("country"),
            "region": item.get("region"),
            "affected_markets": json.dumps(item.get("affected_markets") or ([market] if market else [])),
            "expected_volatility_impact": _normalize_impact(item.get("expected_volatility_impact"), default="medium"),
            "systemic_risk_level": _normalize_impact(item.get("systemic_risk_level"), default="medium"),
            "is_recurring": bool(item.get("is_recurring", False)),
            "confidence_score": float(item.get("confidence_score") or 0.7),
            "expected_eps": item.get("expected_eps"),
            "previous_eps": item.get("previous_eps"),
            "expected_revenue": item.get("expected_revenue"),
            "previous_value": item.get("previous_value"),
            "forecast_value": item.get("forecast_value"),
            "actual_value": item.get("actual_value"),
            "source": item.get("source") or "manual",
            "payload": json.dumps(item),
        }
        if _upsert_event(session, payload):
            created += 1

    return created


def _cleanup_stale(session, horizon_start: date, keep_days_past: int = 30):
    cutoff = datetime(horizon_start.year, horizon_start.month, horizon_start.day) - timedelta(days=keep_days_past)
    deleted = session.query(MarketEvent).filter(MarketEvent.event_datetime_utc < cutoff).delete()
    return deleted


def main(days_ahead=180, lookback_days=7, test=False):
    init_db()
    session = SessionLocal()

    try:
        start = date.today() - timedelta(days=max(0, int(lookback_days)))
        end = date.today() + timedelta(days=max(1, int(days_ahead)))

        if test:
            end = date.today() + timedelta(days=14)

        print(f"[EVENT CALENDAR] Building events from {start} to {end}...")

        created_corporate = _build_corporate_events(session, start, end)
        created_structure = _build_market_structure_events(session, start, end)
        created_manual = _build_manual_events(session, start, end)
        deleted_stale = _cleanup_stale(session, start)

        session.commit()

        total = created_corporate + created_structure + created_manual
        print(
            f"[EVENT CALENDAR] Created/updated={total} "
            f"(corporate={created_corporate}, structure={created_structure}, manual={created_manual}), "
            f"deleted_stale={deleted_stale}"
        )
        print(f"RECORDS_AFFECTED={total}")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days-ahead", type=int, default=180)
    parser.add_argument("--lookback-days", type=int, default=7)
    parser.add_argument("--test", action="store_true", help="Small-window test run")
    args = parser.parse_args()
    main(days_ahead=args.days_ahead, lookback_days=args.lookback_days, test=args.test)
