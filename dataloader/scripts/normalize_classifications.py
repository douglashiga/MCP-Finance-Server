#!/usr/bin/env python3
"""
Normalize Classifications — builds canonical sector/industry/subindustry taxonomy snapshots
from raw IBKR contract metadata and Yahoo fundamentals.
"""
import sys
import os
import re
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import (
    Stock,
    RawYahooFundamental,
    RawIBKRContract,
    SectorTaxonomy,
    IndustryTaxonomy,
    SubIndustryTaxonomy,
    StockClassificationSnapshot,
)


SECTOR_ALIASES = {
    "basic materials": "Materials",
    "communication services": "Communication Services",
    "consumer cyclical": "Consumer Discretionary",
    "consumer defensive": "Consumer Staples",
    "consumer staples": "Consumer Staples",
    "consumer discretionary": "Consumer Discretionary",
    "financial services": "Financials",
    "healthcare": "Healthcare",
    "industrials": "Industrials",
    "real estate": "Real Estate",
    "technology": "Technology",
    "utilities": "Utilities",
    "energy": "Energy",
    "materials": "Materials",
    "telecom": "Communication Services",
}


def _slug(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (text or "").strip().lower()).strip("-")
    return cleaned or "unknown"


def _clean_name(value: str, fallback: str = "Unknown") -> str:
    if not value:
        return fallback
    v = str(value).strip()
    return v if v else fallback


def _canonical_sector(raw: str) -> str:
    if not raw:
        return "Unknown"
    key = raw.strip().lower()
    return SECTOR_ALIASES.get(key, raw.strip().title())


def _latest_map(rows, key_attr="symbol"):
    out = {}
    for row in rows:
        key = getattr(row, key_attr)
        if key not in out:
            out[key] = row
    return out


def _upsert_taxonomy(session, sector_name, industry_name, subindustry_name):
    sector_name = _canonical_sector(_clean_name(sector_name))
    industry_name = _clean_name(industry_name)
    subindustry_name = _clean_name(subindustry_name)

    sector_code = _slug(sector_name)
    sector = session.query(SectorTaxonomy).filter(SectorTaxonomy.code == sector_code).first()
    if not sector:
        sector = SectorTaxonomy(code=sector_code, name=sector_name, is_active=True)
        session.add(sector)
    else:
        sector.name = sector_name
        sector.is_active = True

    industry_code = f"{sector_code}:{_slug(industry_name)}"
    industry = session.query(IndustryTaxonomy).filter(IndustryTaxonomy.code == industry_code).first()
    if not industry:
        industry = IndustryTaxonomy(code=industry_code, sector_code=sector_code, name=industry_name, is_active=True)
        session.add(industry)
    else:
        industry.name = industry_name
        industry.sector_code = sector_code
        industry.is_active = True

    subindustry_code = f"{industry_code}:{_slug(subindustry_name)}"
    subindustry = session.query(SubIndustryTaxonomy).filter(SubIndustryTaxonomy.code == subindustry_code).first()
    if not subindustry:
        subindustry = SubIndustryTaxonomy(
            code=subindustry_code,
            industry_code=industry_code,
            name=subindustry_name,
            is_active=True,
        )
        session.add(subindustry)
    else:
        subindustry.name = subindustry_name
        subindustry.industry_code = industry_code
        subindustry.is_active = True

    return sector_code, industry_code, subindustry_code, sector_name, industry_name


def main():
    init_db()
    session = SessionLocal()
    updated = 0

    try:
        stocks = session.query(Stock).all()

        yahoo_rows = session.query(RawYahooFundamental).order_by(
            RawYahooFundamental.symbol, RawYahooFundamental.fetched_at.desc()
        ).all()
        yahoo_latest = _latest_map(yahoo_rows, key_attr="symbol")

        ib_rows = session.query(RawIBKRContract).order_by(
            RawIBKRContract.symbol, RawIBKRContract.fetched_at.desc()
        ).all()
        ib_latest = _latest_map(ib_rows, key_attr="symbol")

        for stock in stocks:
            yahoo = yahoo_latest.get(stock.symbol)
            ib = ib_latest.get(stock.symbol)

            y_data = {}
            if yahoo:
                try:
                    y_data = json.loads(yahoo.data or "{}")
                except Exception:
                    y_data = {}

            i_data = {}
            if ib:
                try:
                    i_data = json.loads(ib.data or "{}")
                except Exception:
                    i_data = {}

            ib_sector = i_data.get("category")
            ib_industry = i_data.get("industry")
            ib_subindustry = i_data.get("subcategory")
            y_sector = y_data.get("sector")
            y_industry = y_data.get("industry")

            raw_sector = ib_sector or y_sector or "Unknown"
            raw_industry = ib_industry or y_industry or "Unknown"
            raw_subindustry = ib_subindustry or raw_industry or "Unknown"

            source = "ibkr" if (ib_sector or ib_industry) else ("yahoo" if (y_sector or y_industry) else "merged")
            confidence = 0.9 if source == "ibkr" else (0.7 if source == "yahoo" else 0.2)

            sector_code, industry_code, subindustry_code, canon_sector, canon_industry = _upsert_taxonomy(
                session, raw_sector, raw_industry, raw_subindustry
            )

            current = session.query(StockClassificationSnapshot).filter(
                StockClassificationSnapshot.stock_id == stock.id,
                StockClassificationSnapshot.is_current == True,
            ).first()

            if current:
                unchanged = (
                    current.source == source
                    and current.raw_sector == raw_sector
                    and current.raw_industry == raw_industry
                    and current.raw_subindustry == raw_subindustry
                    and current.sector_code == sector_code
                    and current.industry_code == industry_code
                    and current.subindustry_code == subindustry_code
                )
                if unchanged:
                    # Keep current snapshot unchanged; still sync legacy fields.
                    stock.sector = canon_sector
                    stock.industry = canon_industry
                    continue

                current.is_current = False

            snap = StockClassificationSnapshot(
                stock_id=stock.id,
                source=source,
                as_of=datetime.utcnow(),
                is_current=True,
                raw_sector=raw_sector,
                raw_industry=raw_industry,
                raw_subindustry=raw_subindustry,
                sector_code=sector_code,
                industry_code=industry_code,
                subindustry_code=subindustry_code,
                confidence=confidence,
            )
            session.add(snap)

            # Backward compatibility for existing tables/tools.
            stock.sector = canon_sector
            stock.industry = canon_industry
            updated += 1

        session.commit()
        print(f"[NORMALIZE CLASSIFICATIONS] Updated {updated} stock classification snapshots")
        print(f"RECORDS_AFFECTED={updated}")
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
