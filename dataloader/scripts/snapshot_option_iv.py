#!/usr/bin/env python3
"""
Snapshot Option IV — builds a daily IV history snapshot from option_metrics.
Stores ATM and distribution stats to support IV-vs-history analysis.
"""
import argparse
import math
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import and_, func

from dataloader.database import SessionLocal, init_db
from dataloader.models import OptionIVSnapshot, OptionMetric, RealtimePrice, HistoricalPrice


def _to_float(value):
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def _percentile(values, p: float):
    if not values:
        return None
    arr = sorted(float(v) for v in values)
    if len(arr) == 1:
        return arr[0]
    p = max(0.0, min(100.0, float(p)))
    rank = (p / 100.0) * (len(arr) - 1)
    low = int(math.floor(rank))
    high = int(math.ceil(rank))
    if low == high:
        return arr[low]
    weight = rank - low
    return arr[low] * (1.0 - weight) + arr[high] * weight


def _get_spot_price(session, stock_id: int):
    realtime = session.query(RealtimePrice).filter(RealtimePrice.stock_id == stock_id).first()
    if realtime and _to_float(realtime.price):
        return float(realtime.price)

    latest_hist = session.query(HistoricalPrice).filter(
        HistoricalPrice.stock_id == stock_id,
        HistoricalPrice.close.isnot(None),
    ).order_by(HistoricalPrice.date.desc()).first()

    if latest_hist and _to_float(latest_hist.close):
        return float(latest_hist.close)

    return None


def _nearest_expiry(metrics):
    if not metrics:
        return None
    expiries = sorted({m.expiry for m in metrics if m.expiry})
    return expiries[0] if expiries else None


def _select_chain(metrics, target_expiry):
    if not target_expiry:
        return []
    puts = [m for m in metrics if m.expiry == target_expiry and (m.right or "").upper() == "PUT" and _to_float(m.iv)]
    if puts:
        return puts
    return [m for m in metrics if m.expiry == target_expiry and _to_float(m.iv)]


def main(test: bool = False):
    init_db()
    session = SessionLocal()
    updated = 0

    try:
        as_of_dt = session.query(func.max(OptionMetric.updated_at)).scalar()
        if not as_of_dt:
            print("[SNAPSHOT OPTION IV] No option_metrics data. Skipping.")
            print("RECORDS_AFFECTED=0")
            return

        as_of_date = as_of_dt.date()
        today = date.today()

        stock_ids_query = session.query(OptionMetric.stock_id).filter(
            OptionMetric.iv.isnot(None),
            OptionMetric.expiry >= today,
        ).distinct()

        if test:
            stock_ids_query = stock_ids_query.limit(2)

        stock_ids = [row[0] for row in stock_ids_query.all()]
        print(f"[SNAPSHOT OPTION IV] Processing {len(stock_ids)} stocks...")

        for stock_id in stock_ids:
            metrics = session.query(OptionMetric).filter(
                OptionMetric.stock_id == stock_id,
                OptionMetric.iv.isnot(None),
                OptionMetric.expiry >= today,
            ).all()

            if not metrics:
                continue

            nearest_expiry = _nearest_expiry(metrics)
            chain = _select_chain(metrics, nearest_expiry)
            if not chain:
                continue

            iv_values = sorted([_to_float(m.iv) for m in chain if _to_float(m.iv) is not None])
            if not iv_values:
                continue

            spot = _get_spot_price(session, stock_id)
            if spot is not None:
                atm_row = min(chain, key=lambda m: abs(float(m.strike or 0.0) - spot))
            else:
                median_strike = _percentile([float(m.strike or 0.0) for m in chain], 50)
                atm_row = min(chain, key=lambda m: abs(float(m.strike or 0.0) - median_strike))

            atm_iv = _to_float(atm_row.iv)
            median_iv = _to_float(_percentile(iv_values, 50))
            p25_iv = _to_float(_percentile(iv_values, 25))
            p75_iv = _to_float(_percentile(iv_values, 75))

            existing = session.query(OptionIVSnapshot).filter(
                and_(
                    OptionIVSnapshot.stock_id == stock_id,
                    OptionIVSnapshot.snapshot_date == as_of_date,
                )
            ).first()

            if existing:
                existing.snapshot_datetime = as_of_dt
                existing.atm_iv = atm_iv
                existing.median_iv = median_iv
                existing.p25_iv = p25_iv
                existing.p75_iv = p75_iv
                existing.sample_size = len(iv_values)
                existing.source = "option_metrics"
            else:
                session.add(OptionIVSnapshot(
                    stock_id=stock_id,
                    snapshot_date=as_of_date,
                    snapshot_datetime=as_of_dt,
                    atm_iv=atm_iv,
                    median_iv=median_iv,
                    p25_iv=p25_iv,
                    p75_iv=p75_iv,
                    sample_size=len(iv_values),
                    source="option_metrics",
                ))
            updated += 1

        session.commit()
        print(f"[SNAPSHOT OPTION IV] Upserted {updated} snapshots")
        print(f"RECORDS_AFFECTED={updated}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run in test mode (2 stocks)")
    args = parser.parse_args()
    main(test=args.test)
