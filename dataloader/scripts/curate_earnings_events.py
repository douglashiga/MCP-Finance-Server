#!/usr/bin/env python3
"""
Curate Earnings Events — deduplicates raw earnings events into curated earnings_events
and synchronizes legacy tables historical_earnings / earnings_calendar.
"""
import sys
import os
from datetime import date, datetime
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import (
    RawEarningsEvent,
    EarningsEvent,
    HistoricalEarnings,
    EarningsCalendar,
)


SOURCE_PRIORITY = {
    "ibkr": 1.0,
    "yahoo": 0.7,
    "scrape": 0.5,
}


def _quality_score(row: RawEarningsEvent) -> float:
    fields = [
        row.eps_estimate,
        row.eps_actual,
        row.surprise_percent,
        row.revenue_estimate,
        row.revenue_actual,
        row.event_datetime,
        row.period_ending,
    ]
    completeness = sum(1 for f in fields if f is not None) / len(fields)
    source_weight = SOURCE_PRIORITY.get((row.source or "").lower(), 0.3)
    recency = row.fetched_at.timestamp() / 1e10 if row.fetched_at else 0.0
    return completeness * 0.7 + source_weight * 0.25 + recency * 0.05


def main():
    init_db()
    session = SessionLocal()
    curated_count = 0

    try:
        raw_rows = session.query(RawEarningsEvent).order_by(
            RawEarningsEvent.stock_id.asc(),
            RawEarningsEvent.event_date.asc(),
            RawEarningsEvent.fetched_at.desc(),
        ).all()

        grouped = defaultdict(list)
        for row in raw_rows:
            grouped[(row.stock_id, row.event_date)].append(row)

        for (stock_id, event_date), rows in grouped.items():
            best = max(rows, key=_quality_score)
            score = _quality_score(best)

            existing = session.query(EarningsEvent).filter(
                EarningsEvent.stock_id == stock_id,
                EarningsEvent.event_date == event_date,
            ).first()

            if existing:
                existing.event_datetime = best.event_datetime
                existing.period_ending = best.period_ending
                existing.eps_estimate = best.eps_estimate
                existing.eps_actual = best.eps_actual
                existing.surprise_percent = best.surprise_percent
                existing.revenue_estimate = best.revenue_estimate
                existing.revenue_actual = best.revenue_actual
                existing.source = best.source
                existing.quality_score = score
                existing.curated_at = datetime.utcnow()
            else:
                session.add(EarningsEvent(
                    stock_id=stock_id,
                    event_date=event_date,
                    event_datetime=best.event_datetime,
                    period_ending=best.period_ending,
                    eps_estimate=best.eps_estimate,
                    eps_actual=best.eps_actual,
                    surprise_percent=best.surprise_percent,
                    revenue_estimate=best.revenue_estimate,
                    revenue_actual=best.revenue_actual,
                    source=best.source,
                    quality_score=score,
                    curated_at=datetime.utcnow(),
                ))
            curated_count += 1

        today = date.today()

        # Sync historical earnings from curated table (past/present events)
        past_rows = session.query(EarningsEvent).filter(EarningsEvent.event_date <= today).all()
        for row in past_rows:
            hist = session.query(HistoricalEarnings).filter(
                HistoricalEarnings.stock_id == row.stock_id,
                HistoricalEarnings.date == row.event_date,
            ).first()
            if hist:
                hist.period_ending = row.period_ending
                hist.eps_estimate = row.eps_estimate
                hist.eps_actual = row.eps_actual
                hist.surprise_percent = row.surprise_percent
            else:
                session.add(HistoricalEarnings(
                    stock_id=row.stock_id,
                    date=row.event_date,
                    period_ending=row.period_ending,
                    eps_estimate=row.eps_estimate,
                    eps_actual=row.eps_actual,
                    surprise_percent=row.surprise_percent,
                ))

        # Sync earnings calendar with nearest upcoming event per stock
        upcoming_rows = session.query(EarningsEvent).filter(EarningsEvent.event_date > today).order_by(
            EarningsEvent.stock_id.asc(),
            EarningsEvent.event_date.asc(),
        ).all()
        nearest = {}
        for row in upcoming_rows:
            if row.stock_id not in nearest:
                nearest[row.stock_id] = row

        for stock_id, row in nearest.items():
            cal = session.query(EarningsCalendar).filter(EarningsCalendar.stock_id == stock_id).first()
            if cal:
                cal.earnings_date = row.event_date
                cal.earnings_average = row.eps_estimate
                cal.revenue_average = row.revenue_estimate
                cal.updated_at = datetime.utcnow()
            else:
                session.add(EarningsCalendar(
                    stock_id=stock_id,
                    earnings_date=row.event_date,
                    earnings_average=row.eps_estimate,
                    revenue_average=row.revenue_estimate,
                    updated_at=datetime.utcnow(),
                ))

        session.commit()
        print(f"[CURATE EARNINGS] Curated {curated_count} stock/date events")
        print(f"RECORDS_AFFECTED={curated_count}")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
