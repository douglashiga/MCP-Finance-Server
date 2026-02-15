#!/usr/bin/env python3
"""
Seed script — Initializes the database, runs the stock list loader,
and registers all data loader jobs with default cron schedules.
Run with: python -m dataloader.seed
"""
import sys
import os
import argparse
import shlex
import subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataloader.database import init_db, SessionLocal
from dataloader.models import Job, StockMetrics, MarketMover

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")


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
    {
        "name": "Load Market Intelligence",
        "description": "Loads local news, institutional holders, analyst recommendations, and financial statements snapshots",
        "script_path": "load_market_intelligence.py --news-limit 25",
        "cron_expression": "40 7 * * 1-5",  # Weekdays at 7:40 AM
        "timeout_seconds": 1200,
        "affected_tables": "stock_intelligence_snapshots",
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
    
    # ===== MASTER DATA (ELT Stock Loading) =====
    {
        "name": "Load B3 Stocks",
        "description": "Extracts raw B3 stock list from GitHub API into raw_b3_stocks",
        "script_path": "load_stocks_b3.py",
        "cron_expression": "0 5 * * 0",  # Weekly
        "timeout_seconds": 300,
        "affected_tables": "raw_b3_stocks",
    },
    {
        "name": "Load US Stocks",
        "description": "Extracts raw US stock list from Nasdaq FTP into raw_us_stocks",
        "script_path": "load_stocks_us.py",
        "cron_expression": "5 5 * * 0",  # Weekly
        "timeout_seconds": 600,
        "affected_tables": "raw_us_stocks",
    },
    {
        "name": "Load OMX Stocks",
        "description": "Extracts raw OMX stock list (static) into raw_omx_stocks",
        "script_path": "load_stocks_omx.py",
        "cron_expression": "10 5 * * 0",  # Weekly
        "timeout_seconds": 120,
        "affected_tables": "raw_omx_stocks",
    },
    {
        "name": "Transform Stocks",
        "description": "Normalizes raw stocks from all sources into main stocks table",
        "script_path": "transform_stocks.py",
        "cron_expression": "15 5 * * 0",  # Weekly after extraction
        "timeout_seconds": 600,
        "affected_tables": "stocks,index_components",
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


# Ordered first-load plan (strictly serial execution).
# Master data first, then computational/derived tables.
FIRST_LOAD_STEPS = [
    # ===== MASTER DATA =====
    {"phase": "MASTER", "name": "Reference Data Loader", "command": "load_reference_data.py", "timeout": 180},
    {"phase": "MASTER", "name": "Load B3 Stocks", "command": "load_stocks_b3.py", "timeout": 300},
    {"phase": "MASTER", "name": "Load US Stocks", "command": "load_stocks_us.py", "timeout": 600},
    {"phase": "MASTER", "name": "Load OMX Stocks", "command": "load_stocks_omx.py", "timeout": 120},
    {"phase": "MASTER", "name": "Transform Stocks", "command": "transform_stocks.py", "timeout": 600},
    
    {"phase": "MASTER", "name": "Extract Yahoo Fundamentals", "command": "extract_yahoo_fundamentals.py", "timeout": 1800},
    {"phase": "MASTER", "name": "Transform Fundamentals", "command": "transform_fundamentals.py", "timeout": 900},
    {"phase": "MASTER", "name": "Normalize Classifications", "command": "normalize_classifications.py", "timeout": 900},
    {"phase": "MASTER", "name": "Enrich Company Profiles", "command": "enrich_company_profiles.py", "timeout": 900},
    {"phase": "MASTER", "name": "Historical Prices Loader (5y)", "command": "load_historical_prices.py --period 5y", "timeout": 5400},
    {"phase": "MASTER", "name": "Dividends Loader (5y)", "command": "load_dividends.py --years 5", "timeout": 1800},
    {"phase": "MASTER", "name": "Earnings Loader (10y)", "command": "load_earnings.py --years 10", "timeout": 2400},
    {"phase": "MASTER", "name": "Curate Earnings Events", "command": "curate_earnings_events.py", "timeout": 900},
    {"phase": "MASTER", "name": "Extract Yahoo Prices", "command": "extract_yahoo_prices.py", "timeout": 900},
    {"phase": "MASTER", "name": "Transform Prices", "command": "transform_prices.py", "timeout": 600},
    {"phase": "MASTER", "name": "Index Performance Loader", "command": "load_index_performance.py", "timeout": 900},

    # ===== IB-DEPENDENT (still serial) =====
    {"phase": "IB", "name": "Extract IBKR Instruments", "command": "extract_ibkr_instruments.py", "timeout": 1800, "ib_required": True},
    {"phase": "IB", "name": "Extract IBKR Prices", "command": "extract_ibkr_prices.py", "timeout": 1200, "ib_required": True},
    {"phase": "IB", "name": "Transform IBKR Prices", "command": "transform_ibkr_prices.py", "timeout": 900, "ib_required": True},
    {"phase": "IB", "name": "Extract Option Metrics - OMX", "command": "extract_option_metrics.py --market OMX", "timeout": 2400, "ib_required": True},
    {"phase": "IB", "name": "Extract Option Metrics - US", "command": "extract_option_metrics.py --market US", "timeout": 3000, "ib_required": True},
    {"phase": "IB", "name": "Extract Option Metrics - B3", "command": "extract_option_metrics.py --market B3", "timeout": 2400, "ib_required": True},
    {"phase": "IB", "name": "Snapshot Option IV", "command": "snapshot_option_iv.py", "timeout": 900},

    # ===== COMPUTATIONAL / DERIVED =====
    {"phase": "COMPUTE", "name": "Calculate Stock Metrics", "command": "calculate_stock_metrics.py", "timeout": 3600},
    {"phase": "COMPUTE", "name": "Update Market Movers", "command": "update_market_movers.py", "timeout": 1200},
    {"phase": "COMPUTE", "name": "Load Event Calendar", "command": "load_event_calendar.py --days-ahead 180 --lookback-days 14", "timeout": 1200},
    {"phase": "COMPUTE", "name": "Load Market Intelligence", "command": "load_market_intelligence.py --news-limit 25", "timeout": 2400},
]


def _run_script_command(command: str, timeout: int = 1800):
    """
    Run a dataloader script command synchronously (serial mode).
    Returns dict with success, records_affected, stdout_tail, stderr_tail.
    """
    parts = shlex.split(command)
    if not parts:
        return {
            "success": False,
            "records_affected": None,
            "stdout_tail": "",
            "stderr_tail": "Invalid empty command",
            "exit_code": 1,
        }

    script_file = parts[0]
    script_args = parts[1:]
    script_path = script_file if os.path.isabs(script_file) else os.path.join(SCRIPTS_DIR, script_file)

    if not os.path.exists(script_path):
        return {
            "success": False,
            "records_affected": None,
            "stdout_tail": "",
            "stderr_tail": f"Script not found: {script_path}",
            "exit_code": 1,
        }

    try:
        proc = subprocess.run(
            [sys.executable, script_path, *script_args],
            cwd=PROJECT_ROOT,
            env={**os.environ, "PYTHONPATH": PROJECT_ROOT},
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        records_affected = None
        for line in stdout.splitlines():
            if line.startswith("RECORDS_AFFECTED="):
                try:
                    records_affected = int(line.split("=", 1)[1].strip())
                except Exception:
                    records_affected = None

        return {
            "success": proc.returncode == 0,
            "records_affected": records_affected,
            "stdout_tail": "\n".join(stdout.splitlines()[-10:]),
            "stderr_tail": "\n".join(stderr.splitlines()[-10:]),
            "exit_code": proc.returncode,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "records_affected": None,
            "stdout_tail": "",
            "stderr_tail": f"Timeout after {timeout}s",
            "exit_code": -1,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--warmup",
        action="store_true",
        help="Deprecated flag. Full first-load now runs by default in serial mode.",
    )
    parser.add_argument(
        "--skip-first-load",
        action="store_true",
        help="Only initialize DB and sync jobs, skip first-load execution.",
    )
    parser.add_argument(
        "--skip-ib",
        action="store_true",
        help="Skip IB-dependent first-load steps (IBKR prices/instruments/options).",
    )
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
    
    # 3. First-load orchestration (serial only)
    if args.warmup:
        print("\n[3/3] Note: --warmup is deprecated. Running full first load (serial) by default.")

    if args.skip_first_load:
        print("\n[3/3] First load skipped by --skip-first-load.")
    else:
        print("\n[3/3] Running FULL first load (serial, no parallel jobs)...")
        current_phase = None
        failures = []
        completed = 0

        for step in FIRST_LOAD_STEPS:
            if step.get("ib_required") and args.skip_ib:
                print(f"  ↷ Skipped IB step: {step['name']} (--skip-ib)")
                continue

            if step["phase"] != current_phase:
                current_phase = step["phase"]
                print(f"\n  [{current_phase}]")

            print(f"  → {step['name']} ...")
            result = _run_script_command(step["command"], timeout=step.get("timeout", 1800))
            if result["success"]:
                completed += 1
                records = result.get("records_affected")
                if records is not None:
                    print(f"    ✓ OK (records={records})")
                else:
                    print("    ✓ OK")
            else:
                failures.append((step["name"], result))
                print(f"    ⚠️  Failed (exit={result.get('exit_code')})")
                if result.get("stderr_tail"):
                    print(f"       stderr: {result['stderr_tail']}")

        # Validate screener baseline and run fallback serially if needed.
        verify_session = SessionLocal()
        try:
            metrics_count = verify_session.query(StockMetrics).count()
            movers_count = verify_session.query(MarketMover).count()
        finally:
            verify_session.close()

        if metrics_count == 0 or movers_count == 0:
            print("\n  ⚠️  Screener baseline empty after first load. Running serial fallback...")
            fallback_steps = [
                ("Historical Prices Loader (1y fallback)", "load_historical_prices.py --period 1y", 2400),
                ("Calculate Stock Metrics (fallback)", "calculate_stock_metrics.py", 3600),
                ("Update Market Movers (fallback)", "update_market_movers.py", 1200),
            ]
            for name, cmd, timeout in fallback_steps:
                print(f"  → {name} ...")
                result = _run_script_command(cmd, timeout=timeout)
                if result["success"]:
                    print("    ✓ OK")
                else:
                    failures.append((name, result))
                    print(f"    ⚠️  Failed (exit={result.get('exit_code')})")
                    if result.get("stderr_tail"):
                        print(f"       stderr: {result['stderr_tail']}")

        print(f"\n  ✓ First load finished (completed_steps={completed}, failed_steps={len(failures)})")
        if failures:
            print("  Failures summary:")
            for name, result in failures:
                print(f"   - {name} (exit={result.get('exit_code')})")

    print("\n" + "=" * 60)
    print("  ✓ Seed complete! Start the server with:")
    print("    python -m dataloader.app")
    print("    or: python -m dataloader")
    print("  Then open http://localhost:8001")
    print("=" * 60)


if __name__ == "__main__":
    main()
