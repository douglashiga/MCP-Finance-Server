#!/usr/bin/env python3
"""
Seed script — Initializes the database, runs the stock list loader,
and registers all data loader jobs with default cron schedules.
Run with: python -m dataloader.seed
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataloader.database import init_db, SessionLocal
from dataloader.models import Job


# Pre-configured jobs (ELT Architecture)
DEFAULT_JOBS = [
    # ===== EXTRACTORS (Fetch raw data from APIs) =====
    {
        "name": "Extract Yahoo Prices",
        "description": "Fetches current prices from Yahoo Finance and stores raw JSON",
        "script_path": "extract_yahoo_prices.py",
        "cron_expression": "* * * * *",  # Every minute
        "timeout_seconds": 300,
        "affected_tables": "raw_yahoo_prices",
    },
    {
        "name": "Extract Yahoo Fundamentals",
        "description": "Fetches fundamental data from Yahoo Finance and stores raw JSON",
        "script_path": "extract_yahoo_fundamentals.py",
        "cron_expression": "0 6 * * *",  # Daily at 6 AM
        "timeout_seconds": 600,
        "affected_tables": "raw_yahoo_fundamentals",
    },
    {
        "name": "Extract IBKR Prices",
        "description": "Fetches real-time prices from IB Gateway and stores raw JSON",
        "script_path": "extract_ibkr_prices.py",
        "cron_expression": "*/2 * * * *",  # Every 2 minutes (requires IB Gateway connection)
        "timeout_seconds": 300,
        "affected_tables": "raw_ibkr_prices",
    },
    {
        "name": "Extract Option Metrics - B3",
        "description": "Fetches option chains, Greeks, and bid/ask for B3 market (5 weeks range)",
        "script_path": "extract_option_metrics.py --market B3",
        "cron_expression": "*/15 * * * *",  # Every 15 minutes during market hours
        "timeout_seconds": 600,
        "affected_tables": "option_metrics",
    },
    {
        "name": "Extract Option Metrics - US",
        "description": "Fetches option chains, Greeks, and bid/ask for US market (5 weeks range)",
        "script_path": "extract_option_metrics.py --market US",
        "cron_expression": "*/30 * * * *",  # Every 30 minutes
        "timeout_seconds": 1200,
        "affected_tables": "option_metrics",
    },
    {
        "name": "Extract Option Metrics - OMX",
        "description": "Fetches option chains, Greeks, and bid/ask for OMX market (5 weeks range)",
        "script_path": "extract_option_metrics.py --market OMX",
        "cron_expression": "0 * * * *",  # Hourly
        "timeout_seconds": 600,
        "affected_tables": "option_metrics",
    },
    
    # ===== TRANSFORMERS (Normalize raw data into domain tables) =====
    {
        "name": "Transform Prices",
        "description": "Normalizes raw price data into realtime_prices table",
        "script_path": "transform_prices.py",
        "cron_expression": "*/2 * * * *",  # Every 2 minutes (after extract)
        "timeout_seconds": 120,
        "affected_tables": "realtime_prices",
    },
    {
        "name": "Transform IBKR Prices",
        "description": "Normalizes raw IBKR price data into realtime_prices table (merges with Yahoo)",
        "script_path": "transform_ibkr_prices.py",
        "cron_expression": "*/3 * * * *",  # Every 3 minutes (after IBKR extract)
        "timeout_seconds": 120,
        "affected_tables": "realtime_prices",
    },
    {
        "name": "Transform Fundamentals",
        "description": "Normalizes raw fundamental data into fundamentals table",
        "script_path": "transform_fundamentals.py",
        "cron_expression": "30 6 * * *",  # Daily at 6:30 AM (after extract)
        "timeout_seconds": 300,
        "affected_tables": "fundamentals",
    },
    
    # ===== LEGACY LOADERS (Keep for historical/dividend data) =====
    {
        "name": "Stock List Loader",
        "description": "Loads the list of stocks (OMXS30, B3, Nasdaq Stockholm) and their index memberships",
        "script_path": "load_stock_list.py",
        "cron_expression": "0 5 * * 0",  # Weekly on Sunday at 5 AM
        "timeout_seconds": 120,
    },
    {
        "name": "Dividends Loader",
        "description": "Fetches 5-year dividend history and current yield for all stocks",
        "script_path": "load_dividends.py",
        "cron_expression": "0 7 * * 1",  # Weekly on Monday at 7 AM
        "timeout_seconds": 600,
    },
    {
        "name": "Historical Prices Loader",
        "description": "Fetches 12 months of daily OHLCV price data for all stocks",
        "script_path": "load_historical_prices.py",
        "cron_expression": "30 6 * * 1-5",  # Weekdays at 6:30 AM
        "timeout_seconds": 900,
    },
    {
        "name": "Index Performance Loader",
        "description": "Fetches daily data for Ibovespa, OMXS30, and OMXSPI indices (5 years)",
        "script_path": "load_index_performance.py",
        "cron_expression": "0 8 * * 1",  # Weekly on Monday at 8 AM
        "timeout_seconds": 300,
    },
    
    # ===== ANALYTICS (Stock Screener Support) =====
    {
        "name": "Calculate Stock Metrics",
        "description": "Calculates technical indicators (RSI, MACD, EMA) and performance metrics for all stocks",
        "script_path": "calculate_stock_metrics.py",
        "cron_expression": "0 7 * * *",  # Daily at 7 AM (after fundamentals)
        "timeout_seconds": 1800,  # 30 minutes for all stocks
        "affected_tables": "stock_metrics",
    },
    {
        "name": "Update Market Movers",
        "description": "Updates top gainers, losers, and most active stocks by market",
        "script_path": "update_market_movers.py",
        "cron_expression": "*/5 * * * *",  # Every 5 minutes
        "timeout_seconds": 300,
        "affected_tables": "market_movers",
    },
    {
        "name": "Pipeline Health Check",
        "description": "Runs lightweight tests for all loaders to ensure data pipeline is healthy",
        "script_path": "pipeline_health_check.py",
        "cron_expression": "0 */4 * * *",  # Every 4 hours
        "timeout_seconds": 600,
    },
]


def main():
    print("=" * 60)
    print("  DataLoader — Seed Script")
    print("=" * 60)
    
    # 1. Initialize database
    print("\n[1/3] Initializing database...")
    init_db()
    print("  ✓ Tables created")
    
    # 2. Register jobs
    print("\n[2/3] Registering data loader jobs...")
    session = SessionLocal()
    try:
        for job_data in DEFAULT_JOBS:
            existing = session.query(Job).filter_by(name=job_data["name"]).first()
            if not existing:
                session.add(Job(**job_data))
                print(f"  ✓ Registered: {job_data['name']} (cron: {job_data['cron_expression']})")
            else:
                print(f"  → Already exists: {job_data['name']}")
        session.commit()
    finally:
        session.close()
    
    # 3. Run stock list loader to seed initial data
    print("\n[3/3] Loading initial stock list...")
    from dataloader.scripts.load_stock_list import main as load_stocks
    load_stocks()
    
    # 4. Trigger initial data loading (Warm Start)
    print("\n[BONUS] Warming up database with initial data...")
    try:
        from dataloader.scripts.extract_yahoo_prices import main as extract_prices
        from dataloader.scripts.transform_prices import main as transform_prices
        from dataloader.scripts.load_historical_prices import main as load_historical
        from dataloader.scripts.calculate_stock_metrics import main as calculate_metrics
        from dataloader.scripts.update_market_movers import main as update_movers
        
        print("  → Fetching current prices...")
        extract_prices()
        transform_prices()
        
        print("  → Fetching historical data (required for metrics)...")
        load_historical()
        
        print("  → Calculating technical metrics & movers...")
        calculate_metrics()
        update_movers()
        
        print("  ✓ Initial data and metrics loaded")
    except Exception as e:
        print(f"  ⚠️  Warm up partially failed: {e}")

    print("\n" + "=" * 60)
    print("  ✓ Seed complete! Start the server with:")
    print("    python -m dataloader.app")
    print("    or: python -m dataloader")
    print("  Then open http://localhost:8001")
    print("=" * 60)


if __name__ == "__main__":
    main()
