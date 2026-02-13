#!/usr/bin/env python3
"""
Load Reference Data — populates normalized exchanges and market index universe tables.
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import Exchange, MarketIndex


DEFAULT_EXCHANGES = [
    {
        "code": "B3",
        "name": "B3 - Brasil Bolsa Balcao",
        "country": "Brazil",
        "currency": "BRL",
        "yahoo_suffix": ".SA",
        "ib_primary_exchange": "BOVESPA",
        "timezone": "America/Sao_Paulo",
    },
    {
        "code": "OMX",
        "name": "Nasdaq Stockholm",
        "country": "Sweden",
        "currency": "SEK",
        "yahoo_suffix": ".ST",
        "ib_primary_exchange": "SFB",
        "timezone": "Europe/Stockholm",
    },
    {
        "code": "NASDAQ",
        "name": "NASDAQ",
        "country": "USA",
        "currency": "USD",
        "yahoo_suffix": "",
        "ib_primary_exchange": None,
        "timezone": "America/New_York",
    },
    {
        "code": "NYSE",
        "name": "New York Stock Exchange",
        "country": "USA",
        "currency": "USD",
        "yahoo_suffix": "",
        "ib_primary_exchange": None,
        "timezone": "America/New_York",
    },
]


DEFAULT_MARKET_INDICES = [
    {"symbol": "^BVSP", "name": "Ibovespa", "exchange_code": "B3"},
    {"symbol": "^OMX", "name": "OMXS30", "exchange_code": "OMX"},
    {"symbol": "^OMXSPI", "name": "OMX Stockholm PI", "exchange_code": "OMX"},
]


def main():
    init_db()
    session = SessionLocal()
    created = 0

    try:
        for item in DEFAULT_EXCHANGES:
            existing = session.query(Exchange).filter(Exchange.code == item["code"]).first()
            if existing:
                existing.name = item["name"]
                existing.country = item["country"]
                existing.currency = item["currency"]
                existing.yahoo_suffix = item["yahoo_suffix"]
                existing.ib_primary_exchange = item["ib_primary_exchange"]
                existing.timezone = item["timezone"]
                existing.is_active = True
                existing.updated_at = datetime.utcnow()
            else:
                session.add(Exchange(**item))
                created += 1

        for idx in DEFAULT_MARKET_INDICES:
            existing = session.query(MarketIndex).filter(MarketIndex.symbol == idx["symbol"]).first()
            if existing:
                existing.name = idx["name"]
                existing.exchange_code = idx["exchange_code"]
                existing.is_active = True
                existing.updated_at = datetime.utcnow()
            else:
                session.add(MarketIndex(**idx))
                created += 1

        session.commit()
        print(f"[REFERENCE DATA] Upsert complete. New records: {created}")
        print(f"RECORDS_AFFECTED={created}")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
