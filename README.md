# MCP Finance Server

MCP server for market data, fundamentals, screener analytics, options analytics, and Wheel strategy workflows.

This project combines:
- Interactive Brokers (real-time market connectivity)
- Yahoo Finance (broad coverage for fundamentals/history)
- Local ELT pipeline (normalized + cached tables for reliable LLM queries)

Default market for LLM-facing analytics is `sweden`.

## Core Goals

- Stable, LLM-friendly tools with explicit defaults and predictable response envelopes.
- Reliable cached analytics from local DB first, with controlled fallbacks.
- Fast answers for practical trading questions (screener, options, Wheel).
- Clear data lineage from raw ingestion to curated analytics tables.

## Architecture

```text
MCP-Finance-Server/
├── mcp_server.py                    # MCP tool registry and entrypoint
├── services/
│   ├── market_service.py            # Price lookup and symbol resolution
│   ├── option_service.py            # IB option chain + greeks
│   ├── option_screener_service.py   # Cached option metrics queries
│   ├── screener_service.py          # Stock screener + rankings
│   ├── classification_service.py    # Sector/subsector/core business/earnings
│   ├── wheel_service.py             # Wheel analytics (puts, calls, risk, stress)
│   └── job_service.py               # ELT job controls
├── dataloader/
│   ├── models.py                    # SQLAlchemy models
│   ├── seed.py                      # DB seed + default jobs
│   ├── scheduler.py                 # Cron-like job runner
│   └── scripts/                     # Extract/transform/curation scripts
└── README.md
```

## Data Model Highlights

Key normalized/curated tables used by MCP tools:

- `stocks`, `realtime_prices`, `historical_prices`
- `fundamentals`, `dividends`
- `stock_metrics`, `market_movers`
- `option_metrics`
- `option_iv_snapshots` (IV history snapshots from option metrics)
- `exchanges`, `market_indices`
- `sector_taxonomy`, `industry_taxonomy`, `subindustry_taxonomy`
- `stock_classification_snapshots`, `company_profiles`
- `raw_earnings_events`, `earnings_events`

## MCP Tool Groups

### Market and Fundamentals

- `get_stock_price(symbol, exchange=None, currency='USD')`
- `get_historical_data(symbol, duration='1 D', bar_size='1 hour', exchange=None, currency='USD')`
- `search_symbol(query)`
- `get_fundamentals(symbol)`
- `get_dividends(symbol)`
- `get_company_info(symbol)`
- `get_financial_statements(symbol)`
- `get_exchange_info(symbol)`
- `yahoo_search(query)`

### Stock Screener

- `get_stock_screener(market='sweden', sector=None, sort_by='perf_1d', limit=50)`
- `get_top_gainers(market='sweden', period='1D', limit=10)`
- `get_top_losers(market='sweden', period='1D', limit=10)`
- `get_most_active_stocks(market='sweden', period='1D', limit=10)`
- `get_top_dividend_payers(market='sweden', sector=None, limit=10)`
- `get_technical_signals(market='sweden', signal_type='oversold', limit=20)`
- `get_highest_rsi(market='sweden', limit=10)`
- `get_lowest_rsi(market='sweden', limit=10)`
- `get_fundamental_rankings(market='sweden', metric='market_cap', limit=10, sector=None)`

### Classification and Earnings

- `get_companies_by_sector(market='sweden', sector=None, industry=None, subindustry=None, limit=50)`
- `get_company_core_business(symbol)`
- `get_earnings_events(symbol=None, market='sweden', upcoming_only=False, limit=20)`

### Options (Cached + Live)

- `get_option_chain(symbol)`
- `get_option_greeks(symbol, last_trade_date, strike, right)`
- `get_option_screener(symbol=None, expiry=None, right=None, min_delta=None, max_delta=None, min_iv=None, max_iv=None, has_liquidity=True, limit=50)`
- `get_option_chain_snapshot(symbol, expiry=None)`

### Wheel Strategy Tools

- `get_wheel_put_candidates(symbol, market='sweden', delta_min=0.25, delta_max=0.35, dte_min=4, dte_max=10, limit=5, require_liquidity=True)`
- `get_wheel_put_annualized_return(symbol, market='sweden', target_dte=7)`
- `get_wheel_contract_capacity(symbol, capital_sek, market='sweden', strike=None, margin_requirement_pct=1.0, cash_buffer_pct=0.0, target_dte=7)`
- `analyze_wheel_put_risk(symbol, market='sweden', pct_below_spot=5.0, target_dte=7)`
- `get_wheel_assignment_plan(symbol, assignment_strike, premium_received, market='sweden')`
- `get_wheel_covered_call_candidates(symbol, average_cost, market='sweden', delta_min=0.25, delta_max=0.35, dte_min=4, dte_max=21, min_upside_pct=1.0, limit=5)`
- `compare_wheel_premiums(symbol_a, symbol_b, market='sweden', delta_min=0.25, delta_max=0.35, dte_min=4, dte_max=10)`
- `evaluate_wheel_iv(symbol, market='sweden', lookback_days=90, high_iv_threshold_percentile=70.0, target_dte=7)`
- `simulate_wheel_drawdown(symbol, strike, premium_received, drop_percent=10.0, market='sweden')`
- `compare_wheel_start_timing(symbol, market='sweden', wait_drop_percent=3.0, delta_min=0.25, delta_max=0.35, dte_min=4, dte_max=10)`
- `build_wheel_multi_stock_plan(capital_sek, symbols=None, market='sweden', delta_min=0.25, delta_max=0.35, dte_min=4, dte_max=10, margin_requirement_pct=1.0, cash_buffer_pct=0.10)`
- `stress_test_wheel_portfolio(capital_sek, sector_drop_percent=20.0, symbols=None, market='sweden', delta_min=0.25, delta_max=0.35, dte_min=4, dte_max=10)`

### Job and Pipeline Management

- `list_jobs()`
- `get_job_logs(job_name, limit=5)`
- `trigger_job(job_name)`
- `toggle_job(job_name, active)`
- `get_job_status()`
- `run_pipeline_health_check()`

## LLM Service Design Rules

Use these rules when adding/updating tools so other agents can depend on stable behavior.

1. Prefer intent-specific tools over mega-tools.
2. Keep safe defaults (`market='sweden'`, low-risk `limit`, bounded windows).
3. Clamp limits and normalize known enum-style fields.
4. Return explicit `criteria` and `empty_reason` for zero-result queries.
5. Empty result is not a system error (`success=true`, `data=[]`).
6. Include `as_of_date` or `as_of_datetime` when data is snapshot-based.
7. Do not fabricate unavailable backend data; return uncertainty or insufficient-data states.
8. Keep response keys stable; avoid breaking renames.
9. Keep table schema stable when possible; evolve at query/service layer.
10. Protect admin endpoints with API key and strict script-path validation.

### Stable Response Envelope

Preferred shape:

```json
{
  "success": true,
  "data": [],
  "count": 0,
  "criteria": {},
  "empty_reason": null
}
```

## Wheel Analytics Formulas

Used in `wheel_service.py` and exposed by MCP tools:

- Put period return (%) = `(premium / strike) * 100`
- Annualized return (%) = `period_return * (365 / DTE)`
- Cash-secured capital per contract = `strike * 100`
- Capacity = `floor((capital * (1-cash_buffer_pct)) / (strike * 100 * margin_requirement_pct))`
- Break-even (short put) = `strike - premium`
- Assignment probability proxy = `abs(delta)`
- Drawdown scenario at expiry = `max(0, break_even - final_price)`

Notes:
- `abs(delta)` is a proxy, not a true probability model.
- Timing comparison tools return scenario analysis with explicit uncertainty (no forecasts).

## Data Pipeline Jobs (Key)

Major jobs in `dataloader/seed.py` include:

- Raw ingestion: Yahoo prices/fundamentals, IBKR prices, IBKR instruments, option metrics.
- Normalization: prices, fundamentals, classification taxonomy, company profiles.
- Curation: earnings events.
- Analytics: stock metrics, market movers, option IV snapshots.
- Loaders: stock list, reference data, dividends, historical prices, index performance.
- Validation: pipeline health check.

## Quick Start

### Docker

```bash
docker compose up -d
docker compose --profile init run seed
```

### Local

```bash
pip install -e .
python -m dataloader.seed
python -m mcp_server.py
python -m dataloader.app
```

## Security Notes

- Set `DATALOADER_API_KEY` for admin API endpoints.
- Keep `DATALOADER_ALLOW_INSECURE=true` only in local development.
- Configure CORS with `DATALOADER_ALLOWED_ORIGINS`.

## Operational Notes

- If screener returns empty, run:
  - `Historical Prices Loader`
  - `Calculate Stock Metrics`
  - `Update Market Movers`
- If Wheel IV analysis reports insufficient history, run option metrics jobs and `Snapshot Option IV` for multiple days.
- If option greeks are sparse, ensure IB market data permissions and option subscriptions are active.

## License

MIT
