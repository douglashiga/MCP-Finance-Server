#!/usr/bin/env python3
"""
Seed script — Initializes the database, runs the stock list loader,
and registers all data loader jobs with default cron schedules.
Run with: python -m dataloader.seed
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataloader.database import init_db, SessionLocal
from dataloader.models import Job, StockMetrics, MarketMover


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
        "name": "Extract IBKR Instruments",
        "description": "Fetches raw IBKR contract details and option sec-def params",
        "script_path": "extract_ibkr_instruments.py",
        "cron_expression": "15 */6 * * *",  # Every 6 hours
        "timeout_seconds": 900,
        "affected_tables": "raw_ibkr_contracts,raw_ibkr_option_params",
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
    {
        "name": "Snapshot Option IV",
        "description": "Builds daily IV snapshots (ATM/percentiles) from option_metrics",
        "script_path": "snapshot_option_iv.py",
        "cron_expression": "10 */2 * * *",  # Every 2 hours after options loaders
        "timeout_seconds": 300,
        "affected_tables": "option_iv_snapshots",
    },
    {
        "name": "Load Event Calendar",
        "description": "Builds normalized events across corporate/macro/monetary/geopolitical/market structure",
        "script_path": "load_event_calendar.py --days-ahead 180 --lookback-days 14",
        "cron_expression": "20 */2 * * *",  # Every 2 hours
        "timeout_seconds": 600,
        "affected_tables": "market_events",
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
    {
        "name": "Normalize Classifications",
        "description": "Normalizes sector/industry/subindustry from IBKR+Yahoo into canonical taxonomy",
        "script_path": "normalize_classifications.py",
        "cron_expression": "45 6 * * *",  # Daily after fundamentals
        "timeout_seconds": 300,
        "affected_tables": "sector_taxonomy,industry_taxonomy,subindustry_taxonomy,stock_classification_snapshots",
    },
    {
        "name": "Enrich Company Profiles",
        "description": "Builds company profile and core business text from raw fundamentals",
        "script_path": "enrich_company_profiles.py",
        "cron_expression": "50 6 * * *",  # Daily
        "timeout_seconds": 300,
        "affected_tables": "company_profiles",
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
        "name": "Reference Data Loader",
        "description": "Upserts normalized exchange and market index reference tables",
        "script_path": "load_reference_data.py",
        "cron_expression": "30 4 * * 0",  # Weekly on Sunday at 4:30 AM
        "timeout_seconds": 120,
        "affected_tables": "exchanges,market_indices",
    },
    {
        "name": "Dividends Loader",
        "description": "Fetches 1-year dividend history and current yield (Monthly update)",
        "script_path": "load_dividends.py --years 1",
        "cron_expression": "0 7 * * 1",  # Weekly on Monday at 7 AM
        "timeout_seconds": 600,
    },
    {
        "name": "Earnings Loader",
        "description": "Fetches 1-year earnings history and upcoming calendar (Incremental update)",
        "script_path": "load_earnings.py --years 1",
        "cron_expression": "0 8 * * 1-5",  # Weekdays at 8 AM
        "timeout_seconds": 600,
    },
    {
        "name": "Curate Earnings Events",
        "description": "Deduplicates raw earnings events and syncs curated/legacy earnings tables",
        "script_path": "curate_earnings_events.py",
        "cron_expression": "15 8 * * 1-5",  # After earnings loader
        "timeout_seconds": 300,
        "affected_tables": "raw_earnings_events,earnings_events,historical_earnings,earnings_calendar",
    },
    {
        "name": "Historical Prices Loader",
        "description": "Fetches 1 month of daily OHLCV price data for all stocks (Incremental update)",
        "script_path": "load_historical_prices.py --period 1mo",
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--warmup", action="store_true", help="Run heavy initial data warmup jobs")
    args = parser.parse_args()

    print("=" * 60)
    print("  DataLoader — Seed Script")
    print("=" * 60)
    
    # 1. Initialize database
    print("\n[1/3] Initializing database...")
    init_db()
    print("  ✓ Tables created")
    
    # 2. Register or sync jobs
    print("\n[2/3] Registering data loader jobs...")
    session = SessionLocal()
    try:
        created = 0
        updated = 0
        for job_data in DEFAULT_JOBS:
            existing = session.query(Job).filter_by(name=job_data["name"]).first()
            if not existing:
                session.add(Job(**job_data))
                created += 1
                print(f"  ✓ Registered: {job_data['name']} (cron: {job_data['cron_expression']})")
            else:
                changed = False
                for field in ["description", "script_path", "cron_expression", "timeout_seconds", "affected_tables"]:
                    new_value = job_data.get(field)
                    if getattr(existing, field) != new_value:
                        setattr(existing, field, new_value)
                        changed = True

                # Preserve operator choice for is_active; only set default when null.
                if existing.is_active is None:
                    existing.is_active = True
                    changed = True

                if changed:
                    updated += 1
                    print(f"  ↻ Synced: {job_data['name']}")
                else:
                    print(f"  → Unchanged: {job_data['name']}")
        session.commit()
        print(f"  ✓ Jobs synced (created={created}, updated={updated})")
    finally:
        session.close()
    
    # 3. Run stock list loader to seed initial data
    print("\n[3/3] Loading initial stock list...")
    from dataloader.scripts.load_reference_data import main as load_reference_data
    from dataloader.scripts.load_stock_list import main as load_stocks
    load_reference_data()
    load_stocks()
    
    # 4. Trigger initial data loading (Warm Start)
    if not args.warmup:
        print("\n[BONUS] Warmup skipped (use --warmup to run initial heavy loaders).")
    else:
        print("\n[BONUS] Warming up database with initial data...")
        try:
            from dataloader.scripts.extract_yahoo_prices import main as extract_prices
            from dataloader.scripts.transform_prices import main as transform_prices
            from dataloader.scripts.load_historical_prices import main as load_historical
            from dataloader.scripts.calculate_stock_metrics import main as calculate_metrics
            from dataloader.scripts.update_market_movers import main as update_movers
            from dataloader.scripts.normalize_classifications import main as normalize_classifications
            from dataloader.scripts.enrich_company_profiles import main as enrich_company_profiles
            from dataloader.scripts.curate_earnings_events import main as curate_earnings_events
            from dataloader.scripts.load_event_calendar import main as load_event_calendar

            print("  → Fetching current prices...")
            extract_prices()
            transform_prices()

            print("  → Fetching historical pricing (5-year initial load)...")
            load_historical(period="5y")

            print("  → Fetching dividends (5-year initial load)...")
            from dataloader.scripts.load_dividends import main as load_divs
            load_divs(years=5)

            print("  → Fetching earnings & calendar (10-year initial load)...")
            from dataloader.scripts.load_earnings import main as load_earnings
            load_earnings(years=10)
            curate_earnings_events()

            print("  → Normalizing sectors/industries and enriching company profiles...")
            normalize_classifications()
            enrich_company_profiles()

            print("  → Calculating technical metrics & movers...")
            calculate_metrics()
            update_movers()

            print("  → Building normalized event calendar...")
            load_event_calendar(days_ahead=180, lookback_days=14)

            # Validate screener baseline
            verify_session = SessionLocal()
            try:
                metrics_count = verify_session.query(StockMetrics).count()
                movers_count = verify_session.query(MarketMover).count()
            finally:
                verify_session.close()

            if metrics_count == 0 or movers_count == 0:
                print("  ⚠️  Screener baseline is empty after warm-up. Running fallback load...")
                print("  → Fetching historical pricing (1-year fallback)...")
                load_historical(period="1y")
                print("  → Recalculating metrics and market movers...")
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
