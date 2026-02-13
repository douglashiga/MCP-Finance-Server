#!/usr/bin/env python3
"""
Enrich Company Profiles — builds canonical business summary/core business text per stock.
"""
import sys
import os
import json
import re
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, RawYahooFundamental, CompanyProfile


def _latest_map(rows, key_attr="symbol"):
    out = {}
    for row in rows:
        key = getattr(row, key_attr)
        if key not in out:
            out[key] = row
    return out


def _extract_core_business(summary: str, industry: str = None) -> str:
    if summary:
        # First sentence heuristic.
        sentence = re.split(r"(?<=[.!?])\s+", summary.strip())[0].strip()
        if sentence:
            return sentence[:400]
    if industry:
        return f"Operates primarily in the {industry} industry."
    return "Core business summary unavailable."


def main():
    init_db()
    session = SessionLocal()
    count = 0

    try:
        stocks = session.query(Stock).all()
        raw_rows = session.query(RawYahooFundamental).order_by(
            RawYahooFundamental.symbol, RawYahooFundamental.fetched_at.desc()
        ).all()
        latest_yahoo = _latest_map(raw_rows, key_attr="symbol")

        for stock in stocks:
            raw = latest_yahoo.get(stock.symbol)
            if not raw:
                continue

            try:
                payload = json.loads(raw.data or "{}")
            except Exception:
                payload = {}

            summary = payload.get("longBusinessSummary") or payload.get("shortBusinessSummary")
            industry = payload.get("industry") or stock.industry

            profile = session.query(CompanyProfile).filter(CompanyProfile.stock_id == stock.id).first()
            if not profile:
                profile = CompanyProfile(stock_id=stock.id)
                session.add(profile)

            profile.source = "yahoo"
            profile.website = payload.get("website")
            profile.country = payload.get("country") or stock.country
            profile.city = payload.get("city")
            profile.employees = payload.get("fullTimeEmployees")
            profile.business_summary = summary
            profile.core_business = _extract_core_business(summary, industry)
            profile.updated_at = datetime.utcnow()
            count += 1

        session.commit()
        print(f"[ENRICH COMPANY PROFILES] Updated {count} company profiles")
        print(f"RECORDS_AFFECTED={count}")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
