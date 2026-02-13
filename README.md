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

## Why This Server vs Others

- IBKR real-time + Yahoo + local curated cache (not only direct Yahoo API reads).
- Wheel-first toolset (put selection, capacity, assignment flow, covered call continuation).
- Options with greeks + option metrics snapshots for IV and screening.
- Event risk modeling focused on Wheel impact windows.
- Local pipeline with deterministic serial jobs and MCP-friendly discovery tools.

### End-to-end Example 1 (Wheel Put Selection)

1. `get_wheel_put_candidates(symbol='Nordea', market='sweden', delta_min=0.25, delta_max=0.35, dte_min=4, dte_max=10)`
2. `analyze_wheel_put_risk(symbol='Nordea', pct_below_spot=5.0, target_dte=7)`
3. `get_wheel_contract_capacity(symbol='Nordea', capital_sek=200000, market='sweden')`

### End-to-end Example 2 (Event Risk Window)

1. `get_wheel_event_risk_window(ticker='NDA-SE.ST', market='sweden', days_ahead=14)`
2. `get_corporate_events(ticker='NDA-SE.ST', market='sweden')`
3. `get_monetary_policy_events(market='sweden')`

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
- `raw_market_events`, `market_events`
- `stock_intelligence_snapshots` (local cache for news/holders/recommendations/statements)

## MCP Tool Groups

### Market and Fundamentals

- `get_stock_price(symbol, exchange=None, currency='USD')`
- `get_historical_data(symbol, duration='1 D', bar_size='1 hour', exchange=None, currency='USD')`
- `get_historical_data_cached(symbol, period='1y', interval='1d')`
- `search_symbol(query)`
- `get_fundamentals(symbol)`
- `get_dividends(symbol)`
- `get_dividend_history(symbol, period='2y')`
- `get_company_info(symbol)`
- `get_financial_statements(symbol)`
- `get_comprehensive_stock_info(symbol)`
- `get_exchange_info(symbol)`
- `yahoo_search(query)`

### IB Account and Portfolio

- `get_account_summary(masked=True)`
- Resource: `finance://account/summary` (masked by default)
- Resource: `finance://portfolio/positions`

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
- `get_options_data(symbol, expiration_date=None)`

### Market Intelligence (Local Cache)

- `get_news(symbol, limit=10)`
- `get_institutional_holders(symbol, limit=50)`
- `get_analyst_recommendations(symbol, limit=50)`
- `get_technical_analysis(symbol, period='1y')`
- `get_sector_performance(symbols)`

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

### Event Calendar Tools

- `get_event_calendar(market='sweden', category=None, event_type=None, ticker=None, start_date=None, end_date=None, min_volatility_impact='low', limit=50)`
- `get_corporate_events(market='sweden', ticker=None, start_date=None, end_date=None, min_volatility_impact='low', limit=50)`
- `get_macro_events(market='sweden', start_date=None, end_date=None, min_volatility_impact='low', limit=50)`
- `get_monetary_policy_events(market='sweden', start_date=None, end_date=None, min_volatility_impact='low', limit=50)`
- `get_geopolitical_events(market='sweden', start_date=None, end_date=None, min_volatility_impact='low', limit=50)`
- `get_market_structure_events(market='sweden', start_date=None, end_date=None, min_volatility_impact='low', limit=50)`
- `get_wheel_event_risk_window(ticker, market='sweden', days_ahead=14, limit=100)`

### Local Cached DB Tools

- `get_earnings_history(symbol, limit=10)`
- `get_earnings_calendar(symbol)`
- `query_local_stocks(country=None, sector=None)`
- `query_local_fundamentals(symbol)`

### Job and Pipeline Management

- `list_jobs()`
- `get_job_logs(job_name, limit=5)`
- `trigger_job(job_name)`
- `toggle_job(job_name, active)`
- `get_job_status()`
- `run_pipeline_health_check()`

### Capability Discovery

- `get_market_capabilities()`
  - Returns grouped capabilities (`methods` + `examples`) so an LLM can answer "what can you do?" with concrete actions.
- `describe_tool(tool_name)`
  - Returns parameter schema (types/defaults), Pydantic JSON schema (when available), docstring summary and examples for one tool.
- `help_tool(tool_name)`
  - Alias for `describe_tool`, useful for agents that ask for `help`.
- `get_server_health()`
  - Returns health payload equivalent to `/health`.
- `get_server_metrics(output_format='json'|'prometheus')`
  - Returns metrics payload equivalent to `/metrics`.

### Health and Metrics Resources

- Resource: `finance://status`
- Resource: `finance://health`
- Resource: `finance://metrics`

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

### Agent Directives (MCP-friendly)

Use these directives when wiring another AI agent to this server:

1. Start by calling `get_market_capabilities()` for intent routing.
2. For unknown tools, call `describe_tool(tool_name)` before execution.
3. Prefer intent-specific tools over broad queries.
4. Always use explicit market defaults (`market='sweden'`) unless user overrides.
5. Respect uncertainty: if backend has no data, return insufficient-data response.
6. Never infer timestamps; use `meta.asof` from tool responses.
7. In Yahoo-only mode (`IB_ENABLED=false`), avoid IB tools and fallback to local/Yahoo tools.
8. For sensitive info, keep `get_account_summary(masked=True)` unless user explicitly requests otherwise in trusted environment.
9. If a tool returns `validation_error`, fix input and retry once with corrected parameters.
10. If a source is open-circuited (`circuit_open`), avoid repeated retries until cooldown.

### Event Modeling Rules

Use unified events in `market_events` with this minimum contract:

- Identification:
`event_id`, `event_type`, `category`, `subtype`
- Time:
`event_datetime_utc`, `timezone`, `market`, `is_market_hours`, `is_pre_market`, `is_after_market`
- Scope:
`ticker`, `sector`, `country`, `region`, `affected_markets`
- Impact:
`expected_volatility_impact`, `systemic_risk_level`, `is_recurring`, `confidence_score`
- Specific data:
`expected_eps`, `previous_eps`, `expected_revenue`, `previous_value`, `forecast_value`, `actual_value`

Supported categories:
- `corporate`
- `macro`
- `monetary_policy`
- `geopolitical`
- `market_structure`

### Stable Response Envelope

Preferred shape:

```json
{
  "success": true,
  "data": {},
  "error": {
    "code": null,
    "message": null,
    "details": null
  },
  "meta": {
    "source": "ibkr|yahoo|local_db|pipeline|system|...",
    "asof": "2026-02-13T12:34:56.000000+00:00",
    "cache_ttl": null,
    "request_id": "uuid",
    "default_market": "sweden",
    "market_timezone": "Europe/Stockholm"
  }
}
```

Notes:
- The envelope is normalized in `mcp_server.py` (`tool_endpoint` decorator).
- Existing service-specific keys (`count`, `criteria`, etc.) are preserved.

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
- Analytics: stock metrics, market movers, option IV snapshots, event calendar.
- Intelligence cache: news, institutional holders, analyst recommendations, financial statements snapshots.
- Loaders: stock list, reference data, dividends, historical prices, index performance.
- Validation: pipeline health check.

Seed behavior (`python -m dataloader.seed`):
- Idempotent sync of default jobs: missing jobs are created and existing jobs are updated (description/script/cron/timeout/tables) without duplicating rows.
- Full first load runs by default and always in serial (no parallel job execution).
- Load order is phase-based to maximize robustness:
  - `MASTER`: reference/tickers/raw+transform/history/dividends/earnings/classification.
  - `IB`: IBKR extractors/options (still serial, can be skipped).
  - `COMPUTE`: metrics/movers/events/intelligence snapshots.
- First-load dataset includes:
  - historical prices (5y),
  - dividends (5y),
  - earnings (10y) + curation,
  - classification normalization + company profile enrichment,
  - stock metrics + market movers,
  - normalized event calendar generation.
  - market intelligence snapshots.
- Built-in fallback: if screener baseline remains empty, it retries historical load + metrics/movers.
- Optional flags:
  - `--skip-first-load`: only init DB + sync jobs.
  - `--skip-ib`: skip IB-dependent steps during first load.
  - `--warmup`: deprecated alias (first load is already default).

## Quick Start

### 5-minute onboarding (plug-and-play)

```bash
pip install -e .
python -m dataloader.seed --skip-ib
IB_ENABLED=false mcp-finance
```

Then point your MCP client to this server (examples below).

### Docker

```bash
docker compose up -d
docker compose --profile init run seed
```

### Local

```bash
pip install -e .
python -m dataloader.seed
mcp-finance
python -m dataloader.app
```

### Runtime Profiles

- `Yahoo-only`:
  - `IB_ENABLED=false`
  - No IB connection attempt on startup.
  - IB tools return structured `ib_disabled` errors.
- `IBKR + Yahoo`:
  - `IB_ENABLED=true` (default)
  - Requires IB Gateway/TWS connectivity and market data permissions.

### Environment Variables (Reference)

- `IB_ENABLED`:
  - `true|false` (default `true`)
- `MCP_TRANSPORT`:
  - `sse|stdio` (default `sse`)
- `MCP_HOST`:
  - default `0.0.0.0`
- `MCP_PORT`:
  - default `8000`
- `DEFAULT_MARKET`:
  - default `sweden`
- `DEFAULT_MARKET_TIMEZONE`:
  - default `Europe/Stockholm`
- `MCP_TOOL_ALLOWLIST`:
  - comma-separated tool names; if set, only listed tools are callable
- `CIRCUIT_BREAKER_FAILURE_THRESHOLD`:
  - default `4`
- `CIRCUIT_BREAKER_COOLDOWN_SECONDS`:
  - default `45`

### MCP Client Config Examples

#### Claude Desktop

```json
{
  "mcpServers": {
    "finance": {
      "command": "mcp-finance",
      "env": {
        "IB_ENABLED": "false",
        "DEFAULT_MARKET": "sweden",
        "DEFAULT_MARKET_TIMEZONE": "Europe/Stockholm"
      }
    }
  }
}
```

#### Cursor

```json
{
  "mcp": {
    "servers": {
      "finance": {
        "command": "mcp-finance",
        "args": [],
        "env": {
          "IB_ENABLED": "true",
          "MCP_TRANSPORT": "stdio"
        }
      }
    }
  }
}
```

#### Windsurf

```json
{
  "mcpServers": [
    {
      "name": "finance",
      "command": "mcp-finance",
      "env": {
        "IB_ENABLED": "false"
      }
    }
  ]
}
```

#### Minimal Python Agent

```python
import os
import subprocess

env = os.environ.copy()
env["IB_ENABLED"] = "false"
proc = subprocess.Popen(["mcp-finance"], env=env)
print("MCP Finance server PID:", proc.pid)
```

## Security Notes

- Set `DATALOADER_API_KEY` for admin API endpoints.
- Keep `DATALOADER_ALLOW_INSECURE=true` only in local development.
- Configure CORS with `DATALOADER_ALLOWED_ORIGINS`.
- Optional tool allowlist: set `MCP_TOOL_ALLOWLIST=get_market_capabilities,describe_tool,...`.
- Account summary is masked by default (`get_account_summary(masked=true)`).
- If running MCP over network transport (`MCP_TRANSPORT=sse`), keep host/firewall restricted and use API/auth controls on your MCP client gateway.

### Threat Model (What this server does NOT do)

- Does not place orders.
- Does not modify positions.
- Does not submit trades.
- Does not transfer funds.
- Does not provide guaranteed forecasts.

Read-only by design: analytics, screening, events, account inspection, and pipeline control only.

## Observability and Operations

- `get_server_health()` and resource `finance://health`
- `get_server_metrics(output_format='json'|'prometheus')` and resource `finance://metrics`
- Structured JSON logs per tool call (`request_id`, tool, source, latency, success)
- Circuit breaker by source (IBKR/Yahoo/local groups) with cooldown
- Built-in tool-level metrics: calls/failures/avg latency/source breakdown
- Rate limiter metrics exposed via IB connection runtime snapshot

## Code Quality and Releases

- `pre-commit` hooks configured (`ruff`, `black`, `isort`, `mypy`)
- GitHub Actions CI (`.github/workflows/ci.yml`) running lint, type-check and tests
- Recommended release flow:
  - bump `version` in `pyproject.toml`
  - create git tag (`vX.Y.Z`)
  - update changelog/release notes

## Operational Notes

- If screener returns empty, run:
  - `Historical Prices Loader`
  - `Calculate Stock Metrics`
  - `Update Market Movers`
- If Wheel IV analysis reports insufficient history, run option metrics jobs and `Snapshot Option IV` for multiple days.
- If option greeks are sparse, ensure IB market data permissions and option subscriptions are active.
- For macro/monetary/geopolitical events, maintain `dataloader/data/manual_events.json` and run `Load Event Calendar`.
- To refresh local news/holders/recommendations/statements cache, run `Load Market Intelligence`.
- To avoid duplicate manual runs, backend and frontend both protect against concurrent triggers for the same job:
  - backend returns `"Job '<name>' is already queued/running"` when an open run exists,
  - frontend disables the run button while request is in flight.
- Scheduler execution model is now a single-worker queue:
  - all cron/manual triggers are enqueued with `status='queued'`,
  - only one job runs at a time globally,
  - same job is deduplicated while already `queued/running`.
  - on scheduler startup, orphan `queued/running` runs are auto-recovered to `failed`.
- Jobs UI uses in-app notifications/toasts and confirmation modal (no browser `alert()` flow).

## Troubleshooting

- Error during metrics seed like `operands could not be broadcast together with shapes (29,) (30,)`:
  - fixed by using robust return series (`pct_change`) in volatility calculation instead of brittle array slicing.
  - ensure you are on commit `4d0292f` or newer.
- If seed fails due missing deps locally, install project dependencies first:
  - `pip install -e .`

## License

MIT
