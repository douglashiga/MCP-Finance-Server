#!/usr/bin/env python3
"""
Load Earnings — Fetches earnings history + upcoming calendar events from Yahoo and stores raw events.
Also performs compatibility sync into historical_earnings and earnings_calendar.
"""
import sys
import os
import argparse
import time
import json
import math
from datetime import datetime, timedelta, date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, HistoricalEarnings, EarningsCalendar, RawEarningsEvent


def _to_float(value):
    if value is None:
        return None
    try:
        val = float(value)
        if math.isnan(val) or math.isinf(val):
            return None
        return val
    except (TypeError, ValueError):
        return None


def _to_date(value):
    if value is None:
        return None
    if hasattr(value, "date"):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _to_datetime(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        if hasattr(value, "to_pydatetime"):
            return value.to_pydatetime()
    except Exception:
        pass
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def fetch_earnings_data(symbol: str, years: int = 10):
    """Fetch raw historical and upcoming earnings events."""
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    cutoff = datetime.utcnow().date() - timedelta(days=years * 365)

    historical_events = []
    upcoming_events = []

    # Primary source: earnings dates API
    try:
        limit = max(40, years * 8)
        df = ticker.get_earnings_dates(limit=limit)
        if df is not None and not df.empty:
            for idx, row in df.iterrows():
                evt_dt = _to_datetime(idx)
                evt_date = _to_date(evt_dt)
                if not evt_date:
                    continue
                if evt_date < cutoff:
                    continue

                event = {
                    "event_date": evt_date,
                    "event_datetime": evt_dt,
                    "period_ending": None,
                    "eps_estimate": _to_float(row.get("EPS Estimate")),
                    "eps_actual": _to_float(row.get("Reported EPS")),
                    "surprise_percent": _to_float(row.get("Surprise(%)")),
                    "revenue_estimate": _to_float(row.get("Revenue Estimate")),
                    "revenue_actual": _to_float(row.get("Revenue Actual")),
                    "payload": json.dumps({
                        "source": "get_earnings_dates",
                        "row": {k: (None if _to_float(v) is None and not isinstance(v, (str, int, float)) else v)
                                for k, v in row.to_dict().items()}
                    }, default=str),
                }
                if evt_date <= datetime.utcnow().date():
                    historical_events.append(event)
                else:
                    upcoming_events.append(event)
    except Exception as e:
        print(f"  ⚠️  Error fetching get_earnings_dates for {symbol}: {e}")

    # Secondary source: calendar (often only upcoming)
    try:
        cal = ticker.calendar
        if cal is not None:
            if isinstance(cal, dict):
                e_dates = cal.get("Earnings Date")
                primary = e_dates[0] if isinstance(e_dates, list) and e_dates else e_dates
                evt_date = _to_date(primary)
                evt_dt = _to_datetime(primary)
                if evt_date:
                    upcoming_events.append({
                        "event_date": evt_date,
                        "event_datetime": evt_dt,
                        "period_ending": None,
                        "eps_estimate": _to_float(cal.get("Earnings Average")),
                        "eps_actual": None,
                        "surprise_percent": None,
                        "revenue_estimate": _to_float(cal.get("Revenue Average")),
                        "revenue_actual": None,
                        "payload": json.dumps({"source": "calendar_dict", "calendar": cal}, default=str),
                    })
            elif hasattr(cal, "index"):
                try:
                    e_date_row = cal.loc["Earnings Date"]
                    e_val = e_date_row.iloc[0] if hasattr(e_date_row, "iloc") else e_date_row[0]
                    evt_date = _to_date(e_val)
                    evt_dt = _to_datetime(e_val)
                    if evt_date:
                        upcoming_events.append({
                            "event_date": evt_date,
                            "event_datetime": evt_dt,
                            "period_ending": None,
                            "eps_estimate": _to_float(cal.loc["Earnings Average"].iloc[0]) if "Earnings Average" in cal.index else None,
                            "eps_actual": None,
                            "surprise_percent": None,
                            "revenue_estimate": _to_float(cal.loc["Revenue Average"].iloc[0]) if "Revenue Average" in cal.index else None,
                            "revenue_actual": None,
                            "payload": json.dumps({"source": "calendar_df"}, default=str),
                        })
                except Exception:
                    pass
    except Exception:
        pass

    return historical_events, upcoming_events


def main(years=None):
    if years is None:
        parser = argparse.ArgumentParser()
        parser.add_argument("--years", type=int, default=10, help="Number of years of history to fetch")
        args, _ = parser.parse_known_args()
        years = args.years

    init_db()
    session = SessionLocal()
    count_hist = 0
    count_cal = 0
    count_raw = 0
    errors = 0

    try:
        stocks = session.query(Stock).all()
        total = len(stocks)
        print(f"[EARNINGS] Fetching {years}-year data for {total} stocks...")

        today = datetime.utcnow().date()

        for i, stock in enumerate(stocks, 1):
            try:
                print(f"  [{i}/{total}] {stock.symbol}...", end=" ", flush=True)
                hist_events, upcoming_events = fetch_earnings_data(stock.symbol, years=years)

                # Store raw events (append-only)
                raw_seen = set()
                for ev in hist_events + upcoming_events:
                    raw_key = (ev["event_date"], ev.get("eps_estimate"), ev.get("eps_actual"), ev.get("event_datetime"))
                    if raw_key in raw_seen:
                        continue
                    raw_seen.add(raw_key)

                    session.add(RawEarningsEvent(
                        stock_id=stock.id,
                        source="yahoo",
                        event_type="history" if ev["event_date"] <= today else "upcoming",
                        event_date=ev["event_date"],
                        event_datetime=ev.get("event_datetime"),
                        period_ending=ev.get("period_ending"),
                        eps_estimate=ev.get("eps_estimate"),
                        eps_actual=ev.get("eps_actual"),
                        surprise_percent=ev.get("surprise_percent"),
                        revenue_estimate=ev.get("revenue_estimate"),
                        revenue_actual=ev.get("revenue_actual"),
                        payload=ev.get("payload"),
                        fetched_at=datetime.utcnow(),
                    ))
                    count_raw += 1

                # Compatibility sync: historical_earnings
                for h in hist_events:
                    existing = session.query(HistoricalEarnings).filter_by(
                        stock_id=stock.id,
                        date=h["event_date"]
                    ).first()
                    if existing:
                        existing.eps_estimate = h.get("eps_estimate")
                        existing.eps_actual = h.get("eps_actual")
                        existing.surprise_percent = h.get("surprise_percent")
                        existing.period_ending = h.get("period_ending")
                    else:
                        session.add(HistoricalEarnings(
                            stock_id=stock.id,
                            date=h["event_date"],
                            period_ending=h.get("period_ending"),
                            eps_estimate=h.get("eps_estimate"),
                            eps_actual=h.get("eps_actual"),
                            surprise_percent=h.get("surprise_percent"),
                        ))
                        count_hist += 1

                # Compatibility sync: earnings_calendar (nearest upcoming)
                upcoming_sorted = sorted([u for u in upcoming_events if u["event_date"] > today], key=lambda x: x["event_date"])
                if upcoming_sorted:
                    nxt = upcoming_sorted[0]
                    existing_cal = session.query(EarningsCalendar).filter_by(stock_id=stock.id).first()
                    if existing_cal:
                        existing_cal.earnings_date = nxt["event_date"]
                        existing_cal.earnings_average = nxt.get("eps_estimate")
                        existing_cal.revenue_average = nxt.get("revenue_estimate")
                        existing_cal.updated_at = datetime.utcnow()
                    else:
                        session.add(EarningsCalendar(
                            stock_id=stock.id,
                            earnings_date=nxt["event_date"],
                            earnings_average=nxt.get("eps_estimate"),
                            revenue_average=nxt.get("revenue_estimate"),
                            updated_at=datetime.utcnow(),
                        ))
                    count_cal += 1

                print(f"OK ({len(hist_events)} hist, {len(upcoming_events)} upc)")
                time.sleep(0.5)

            except Exception as e:
                print(f"ERROR: {e}")
                errors += 1
                continue

        session.commit()
        total_affected = count_hist + count_cal + count_raw
        print(f"\n[EARNINGS] Done: {count_hist} history rows, {count_cal} calendar updates, {count_raw} raw rows, {errors} errors")
        print(f"RECORDS_AFFECTED={total_affected}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
