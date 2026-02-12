#!/usr/bin/env python3
"""
Update Market Movers — Identifies top gainers, losers, and most active stocks.
Populates market_movers table for fast queries.
Runs every 5 minutes during market hours, and hourly outside hours.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, date
from sqlalchemy import and_
from dataloader.database import SessionLocal
from dataloader.models import Stock, StockMetrics, MarketMover, RealtimePrice


MARKETS = {
    "B3": ["SA"],           # Brazilian stocks
    "OMX": ["ST"],          # Swedish stocks  
    "NASDAQ": [],           # Will filter by exchange
    "NYSE": []              # Will filter by exchange
}

PERIODS = ["1D", "1W", "1M"]
TOP_N = 10


def get_stocks_by_market(session, market):
    """Get all stocks for a specific market."""
    if market in ["NASDAQ", "NYSE"]:
        return session.query(Stock).filter(Stock.exchange == market).all()
    else:
        # Filter by symbol suffix
        suffixes = MARKETS.get(market, [])
        stocks = []
        for suffix in suffixes:
            stocks.extend(
                session.query(Stock).filter(
                    Stock.symbol.like(f"%.{suffix}")
                ).all()
            )
        return stocks


def update_top_gainers(session, market, period, today):
    """Find top N gainers for a market/period."""
    stocks = get_stocks_by_market(session, market)
    stock_ids = [s.id for s in stocks]
    
    if not stock_ids:
        return 0
    
    # Get performance field
    perf_field = {
        "1D": StockMetrics.perf_1d,
        "1W": StockMetrics.perf_1w,
        "1M": StockMetrics.perf_1m
    }.get(period)
    
    if not perf_field:
        return 0
    
    # Query top gainers
    top_gainers = session.query(
        StockMetrics.stock_id,
        perf_field
    ).filter(
        and_(
            StockMetrics.stock_id.in_(stock_ids),
            StockMetrics.date == today,
            perf_field.isnot(None)
        )
    ).order_by(perf_field.desc()).limit(TOP_N).all()
    
    # Delete old entries
    session.query(MarketMover).filter(
        and_(
            MarketMover.market == market,
            MarketMover.period == period,
            MarketMover.category == "top_gainers"
        )
    ).delete()
    
    # Insert new rankings
    for rank, (stock_id, performance) in enumerate(top_gainers, 1):
        mover = MarketMover(
            market=market,
            period=period,
            category="top_gainers",
            rank=rank,
            stock_id=stock_id,
            value=performance
        )
        session.add(mover)
    
    return len(top_gainers)


def update_top_losers(session, market, period, today):
    """Find top N losers (worst performers) for a market/period."""
    stocks = get_stocks_by_market(session, market)
    stock_ids = [s.id for s in stocks]
    
    if not stock_ids:
        return 0
    
    # Get performance field
    perf_field = {
        "1D": StockMetrics.perf_1d,
        "1W": StockMetrics.perf_1w,
        "1M": StockMetrics.perf_1m
    }.get(period)
    
    if not perf_field:
        return 0
    
    # Query top losers (ascending order)
    top_losers = session.query(
        StockMetrics.stock_id,
        perf_field
    ).filter(
        and_(
            StockMetrics.stock_id.in_(stock_ids),
            StockMetrics.date == today,
            perf_field.isnot(None)
        )
    ).order_by(perf_field.asc()).limit(TOP_N).all()
    
    # Delete old entries
    session.query(MarketMover).filter(
        and_(
            MarketMover.market == market,
            MarketMover.period == period,
            MarketMover.category == "top_losers"
        )
    ).delete()
    
    # Insert new rankings
    for rank, (stock_id, performance) in enumerate(top_losers, 1):
        mover = MarketMover(
            market=market,
            period=period,
            category="top_losers",
            rank=rank,
            stock_id=stock_id,
            value=performance
        )
        session.add(mover)
    
    return len(top_losers)


def update_most_active(session, market, today):
    """Find most active stocks by volume."""
    stocks = get_stocks_by_market(session, market)
    stock_ids = [s.id for s in stocks]
    
    if not stock_ids:
        return 0
    
    # Query most active by volume
    most_active = session.query(
        StockMetrics.stock_id,
        StockMetrics.avg_volume_10d
    ).filter(
        and_(
            StockMetrics.stock_id.in_(stock_ids),
            StockMetrics.date == today,
            StockMetrics.avg_volume_10d.isnot(None)
        )
    ).order_by(StockMetrics.avg_volume_10d.desc()).limit(TOP_N).all()
    
    # Delete old entries
    session.query(MarketMover).filter(
        and_(
            MarketMover.market == market,
            MarketMover.period == "1D",  # Volume is always 1D
            MarketMover.category == "most_active"
        )
    ).delete()
    
    # Insert new rankings
    for rank, (stock_id, volume) in enumerate(most_active, 1):
        mover = MarketMover(
            market=market,
            period="1D",
            category="most_active",
            rank=rank,
            stock_id=stock_id,
            value=volume
        )
        session.add(mover)
    
    return len(most_active)


def main():
    session = SessionLocal()
    count = 0
    today = date.today()
    
    try:
        print(f"[UPDATE MOVERS] Updating market movers for {today}...")
        
        for market in MARKETS.keys():
            print(f"\n  Processing market: {market}")
            
            # Top gainers and losers for each period
            for period in PERIODS:
                gainers = update_top_gainers(session, market, period, today)
                losers = update_top_losers(session, market, period, today)
                print(f"    {period}: {gainers} gainers, {losers} losers")
                count += gainers + losers
            
            # Most active (1D only)
            active = update_most_active(session, market, today)
            print(f"    Most Active: {active} stocks")
            count += active
        
        session.commit()
        print(f"\n[UPDATE MOVERS] Updated {count} market mover entries")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
