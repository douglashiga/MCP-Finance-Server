"""
Classification Service — normalized sector/subsector and company profile queries.
"""
import logging
from datetime import date
from sqlalchemy import func
from dataloader.database import SessionLocal
from dataloader.models import (
    Stock,
    SectorTaxonomy,
    IndustryTaxonomy,
    SubIndustryTaxonomy,
    StockClassificationSnapshot,
    CompanyProfile,
    EarningsEvent,
)

logger = logging.getLogger(__name__)

MARKET_MAP = {
    "brazil": ["B3"],
    "b3": ["B3"],
    "sweden": ["OMX"],
    "omx": ["OMX"],
    "usa": ["NASDAQ", "NYSE"],
    "us": ["NASDAQ", "NYSE"],
    "nasdaq": ["NASDAQ"],
    "nyse": ["NYSE"],
    "all": ["B3", "OMX", "NASDAQ", "NYSE"],
}


def _resolve_market(market: str):
    return MARKET_MAP.get((market or "sweden").lower(), [market.upper()])


class ClassificationService:
    @staticmethod
    def get_companies_by_sector(market: str = "sweden", sector: str = None, industry: str = None,
                                subindustry: str = None, limit: int = 50):
        session = SessionLocal()
        try:
            limit = max(1, min(int(limit), 200))
            exchanges = _resolve_market(market)

            q = session.query(
                Stock,
                StockClassificationSnapshot,
                SectorTaxonomy,
                IndustryTaxonomy,
                SubIndustryTaxonomy,
                CompanyProfile,
            ).join(
                StockClassificationSnapshot,
                (StockClassificationSnapshot.stock_id == Stock.id) &
                (StockClassificationSnapshot.is_current == True),
            ).outerjoin(
                SectorTaxonomy, SectorTaxonomy.code == StockClassificationSnapshot.sector_code
            ).outerjoin(
                IndustryTaxonomy, IndustryTaxonomy.code == StockClassificationSnapshot.industry_code
            ).outerjoin(
                SubIndustryTaxonomy, SubIndustryTaxonomy.code == StockClassificationSnapshot.subindustry_code
            ).outerjoin(
                CompanyProfile, CompanyProfile.stock_id == Stock.id
            ).filter(
                Stock.exchange.in_(exchanges)
            )

            if sector:
                q = q.filter(
                    (SectorTaxonomy.name.ilike(f"%{sector}%")) |
                    (StockClassificationSnapshot.raw_sector.ilike(f"%{sector}%"))
                )
            if industry:
                q = q.filter(
                    (IndustryTaxonomy.name.ilike(f"%{industry}%")) |
                    (StockClassificationSnapshot.raw_industry.ilike(f"%{industry}%"))
                )
            if subindustry:
                q = q.filter(
                    (SubIndustryTaxonomy.name.ilike(f"%{subindustry}%")) |
                    (StockClassificationSnapshot.raw_subindustry.ilike(f"%{subindustry}%"))
                )

            rows = q.order_by(Stock.symbol.asc()).limit(limit).all()
            data = []
            for stock, snap, sec, ind, sub, profile in rows:
                data.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "country": stock.country,
                    "sector": sec.name if sec else snap.raw_sector or stock.sector,
                    "industry": ind.name if ind else snap.raw_industry or stock.industry,
                    "subindustry": sub.name if sub else snap.raw_subindustry,
                    "core_business": profile.core_business if profile else None,
                    "source": snap.source,
                    "confidence": snap.confidence,
                    "as_of": snap.as_of.isoformat() if snap.as_of else None,
                })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "market": market,
                "criteria": {
                    "market": market,
                    "sector": sector,
                    "industry": industry,
                    "subindustry": subindustry,
                    "limit": limit,
                },
                "empty_reason": None if data else "no_companies_for_classification",
            }
        except Exception as e:
            logger.error(f"Classification query error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_company_core_business(symbol: str):
        session = SessionLocal()
        try:
            stock = session.query(Stock).filter(
                (Stock.symbol == symbol) | (Stock.symbol.ilike(f"{symbol}.%"))
            ).first()
            if not stock:
                return {"success": False, "error": f"Stock {symbol} not found"}

            profile = session.query(CompanyProfile).filter(CompanyProfile.stock_id == stock.id).first()
            snap = session.query(StockClassificationSnapshot).filter(
                StockClassificationSnapshot.stock_id == stock.id,
                StockClassificationSnapshot.is_current == True,
            ).first()

            return {
                "success": True,
                "data": {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "sector": snap.raw_sector if snap else stock.sector,
                    "industry": snap.raw_industry if snap else stock.industry,
                    "core_business": profile.core_business if profile else None,
                    "business_summary": profile.business_summary if profile else None,
                    "website": profile.website if profile else None,
                    "updated_at": profile.updated_at.isoformat() if profile and profile.updated_at else None,
                }
            }
        except Exception as e:
            logger.error(f"Core business query error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_earnings_events(symbol: str = None, market: str = "sweden", upcoming_only: bool = False, limit: int = 20):
        session = SessionLocal()
        try:
            limit = max(1, min(int(limit), 200))
            exchanges = _resolve_market(market)
            today = date.today()

            q = session.query(EarningsEvent, Stock).join(
                Stock, Stock.id == EarningsEvent.stock_id
            ).filter(
                Stock.exchange.in_(exchanges)
            )

            if symbol:
                q = q.filter((Stock.symbol == symbol) | (Stock.symbol.ilike(f"{symbol}.%")))
            if upcoming_only:
                q = q.filter(EarningsEvent.event_date >= today)

            rows = q.order_by(EarningsEvent.event_date.asc() if upcoming_only else EarningsEvent.event_date.desc()).limit(limit).all()

            data = []
            for ev, stock in rows:
                data.append({
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "event_date": ev.event_date.isoformat() if ev.event_date else None,
                    "event_datetime": ev.event_datetime.isoformat() if ev.event_datetime else None,
                    "eps_estimate": ev.eps_estimate,
                    "eps_actual": ev.eps_actual,
                    "surprise_percent": ev.surprise_percent,
                    "revenue_estimate": ev.revenue_estimate,
                    "revenue_actual": ev.revenue_actual,
                    "source": ev.source,
                    "quality_score": ev.quality_score,
                    "curated_at": ev.curated_at.isoformat() if ev.curated_at else None,
                })

            return {
                "success": True,
                "data": data,
                "count": len(data),
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "upcoming_only": upcoming_only,
                    "limit": limit,
                },
                "empty_reason": None if data else "no_earnings_events_for_criteria",
            }
        except Exception as e:
            logger.error(f"Earnings events query error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()
