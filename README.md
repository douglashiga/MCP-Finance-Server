# 🏦 MCP Finance Server

A professional-grade **Model Context Protocol (MCP)** server for financial data, powered by **Interactive Brokers** (real-time), **Yahoo Finance** (fundamentals), and a built-in **Stock Screener** with technical indicators.

Covers **3 markets**: 🇧🇷 Brazil (B3), 🇸🇪 Sweden (OMX), 🇺🇸 USA (NASDAQ/NYSE).

---

## 📐 Architecture

```
MCP_Finance/
├── core/                          # Infrastructure Layer
│   ├── connection.py              # IB Singleton, auto-reconnect, heartbeat
│   ├── rate_limiter.py            # Token bucket (5 req/sec)
│   └── decorators.py              # @require_connection
├── services/                      # Business Logic Layer
│   ├── market_service.py          # Real-time price (local DB + IB fallback)
│   ├── history_service.py         # OHLCV bars + 30s cache (IB)
│   ├── option_service.py          # Option chains & Greeks (IB)
│   ├── account_service.py         # Balances, margin, positions (IB)
│   ├── yahoo_service.py           # Fundamentals, dividends (local DB)
│   ├── screener_service.py        # Stock screener & technical signals ⭐
│   └── job_service.py             # Job management for LLM ⭐
├── dataloader/                    # ELT Data Pipeline ⭐
│   ├── app.py                     # Scheduler + Web UI (port 8001)
│   ├── models.py                  # SQLAlchemy models (17 tables)
│   ├── database.py                # SQLite/PostgreSQL support
│   ├── seed.py                    # Initialize DB + register jobs
│   ├── scripts/                   # Extract, Transform, Load scripts
│   │   ├── extract_yahoo_prices.py
│   │   ├── extract_yahoo_fundamentals.py
│   │   ├── extract_ibkr_prices.py
│   │   ├── transform_prices.py
│   │   ├── transform_fundamentals.py
│   │   ├── transform_ibkr_prices.py
│   │   ├── calculate_stock_metrics.py    # RSI, MACD, performance ⭐
│   │   ├── update_market_movers.py       # Top gainers/losers ⭐
│   │   ├── load_stock_list.py
│   │   ├── load_dividends.py
│   │   ├── load_historical_prices.py
│   │   └── load_index_performance.py
│   └── static/index.html          # Data Loader Web UI
├── mcp_server.py                  # MCP entry point (22 tools)
├── docker-compose.yml             # IB Gateway + MCP + DataLoader
├── test_mcp_server.py             # Unit tests (12 tests)
├── test_integration.py            # Integration tests (11 tests)
└── Dockerfile
```

### ELT Data Flow

```
┌─────────────────────────────────────────────────┐
│ EXTRACT (Scheduled Jobs)                        │
│  Yahoo Prices → raw_yahoo_prices                │
│  Yahoo Fundamentals → raw_yahoo_fundamentals    │
│  IBKR Prices → raw_ibkr_prices                 │
│  Historical Data → historical_prices            │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ TRANSFORM (Scheduled Jobs)                      │
│  raw prices → realtime_prices                   │
│  raw fundamentals → fundamentals                │
│  historical → stock_metrics (RSI, MACD, etc)    │
│  stock_metrics → market_movers (rankings)       │
└──────────────────┬──────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────┐
│ SERVE (MCP Tools + Dashboard)                   │
│  22 MCP tools query local DB                    │
│  Stock Screener Dashboard                       │
│  Data Loader Web UI                             │
└─────────────────────────────────────────────────┘
```

---

## 🛠 Tools (22)

### Interactive Brokers (Real-time) — 6 tools

| Tool | Description | Example |
## 🛠 MCP Tool Catalog (32 Tools)

The server exposes 32 specialized tools for LLM agents to interact with financial data.

### 📈 Market Data — 8 tools
| Tool | Description | Example |
|------|-------------|---------|
| `get_quote(symbol)` | Real-time prices (IBKR/Yahoo) | `get_quote("PETR4")` |
| `get_company_info(symbol)` | Profile, sector, industry | `get_company_info("AAPL")` |
| `get_stock_history(symbol)` | Historical OHLCV data | `get_stock_history("VALE3", "1mo")` |
| `search_tickers(query)` | Search stocks by name/sector | `search_tickers("banco")` |
| `get_index_components(idx)` | OMXS30, IBOV, etc | `get_index_components("IBOV")` |
| `get_index_performance(idx)` | Historical performance data | `get_index_performance("OMXS30")` |
| `get_ibkr_pnl()` | Real-time account PnL | `get_ibkr_pnl()` |
| `get_ibkr_positions()` | Current open positions | `get_ibkr_positions()` |

### 🔍 Stock Screener & Analytics — 5 tools ⭐
| Tool | Description | Example |
|------|-------------|---------|
| `get_stock_screener(...)` | Filter by Perf, RSI, Volume | `get_stock_screener(market="usa")` |
| `get_top_movers(market)` | Gainers, Losers, Most Active | `get_top_movers("brazil")` |
| `get_top_dividend_payers(mkt)`| High yield rankings | `get_top_dividend_payers("sweden")` |
| `get_technical_signals(mkt)` | RSI Oversold, Golden Cross | `get_technical_signals("usa", "oversold")` |
| `get_market_summary(market)` | Holistic view of indices | `get_market_summary("brazil")` |

### 💎 Options Screener — 2 tools ⭐
| Tool | Description | Example |
|------|-------------|---------|
| `get_option_screener(...)` | Filter by Delta, IV, Liquidity | `get_option_screener("AAPL", min_delta=0.2)` |
| `get_option_chain_snapshot(sym)`| Latest cached Greeks/Quotes | `get_option_chain_snapshot("PETR4")` |

### 🩺 Pipeline & Health — 6 tools ⭐
| Tool | Description | Example |
|------|-------------|---------|
| `run_pipeline_health_check()` | Lightweight validation of all jobs| `run_pipeline_health_check()` |
| `get_job_status()` | Health overview of all tasks | `get_job_status()` |
| `list_jobs()` | List all ELT schedules | `list_jobs()` |
| `trigger_job(name)` | Manually start a data sync | `trigger_job("Extract IBKR")` |
| `get_job_logs(name)` | View script output/errors | `get_job_logs("Update Movers")` |
| `toggle_job(name, active)` | Enable/Disable schedules | `toggle_job("Yahoo Prices", false)` |

---

## 🏗 System Architecture (ELT)

We use an **ELT (Extract, Load, Transform)** flow to ensure data is always fresh and queries are fast.

1.  **EXTRACTORS**: Python scripts fetch raw JSON from Yahoo Finance and IBKR Gateway.
2.  **LOADERS**: Raw data is stored in the PostgreSQL database.
3.  **TRANSFORMERS/ANALYTICS**: Background jobs normalize the data and calculate technical indicators (RSI, MACD, Greeks).

---

## 🐳 Quick Start (Docker)

The easiest way to run the whole stack is using Docker Compose.

### 1. Configure `.env`
Create a `.env` file based on `.env.example`:
```bash
IB_HOST=ib-gateway
IB_PORT=4003
POSTGRES_PASSWORD=your_secure_password
TWS_USERID=your_ibkr_user
TWS_PASSWORD=your_ibkr_pass
TRADING_MODE=paper
```

### 2. Launch Services
```bash
docker compose up -d
```
This starts:
- **PostgreSQL**: Central data storage.
- **IB Gateway**: Headless connection to Interactive Brokers.
- **MCP Finance Server**: The agent bridge (Port 8000).
- **Data Loader**: The scheduler and UI (Port 8001).

### 3. Initialize Database
Run the one-shot seed script to create tables and load the initial stock list:
```bash
docker compose --profile init run seed
```

---

## 🖥 Monitoring & Management

Access the **Data Loader UI** at `http://localhost:8001` to:
- Monitor background job status.
- Trigger manual health checks.
- Browse the PostgreSQL tables directly.
- View logs and PnL metrics.

---

## 🛠 Manual Installation (Non-Docker)

1. **Install dependencies**:
   ```bash
   pip install -e .
   ```
2. **Setup DB**:
   ```bash
   python -m dataloader.seed
   ```
3. **Start Services**:
   ```bash
   python -m mcp_server.py  # MCP bridge
   python -m dataloader.app # Dashboard/Scheduler
   ```

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///...` | PostgreSQL: `postgresql://user:pass@host:5432/db` |
| `IB_HOST` | `127.0.0.1` | IB Gateway host |
| `IB_PORT` | `4001` | IB Gateway API port |
| `IB_CLIENT_ID` | `1` | Client ID for IB connection |
| `IB_READ_ONLY` | `true` | Read-only mode |
| `LOG_LEVEL` | `INFO` | Logging level |

### Database: PostgreSQL (Production)

```bash
# Set DATABASE_URL to use PostgreSQL instead of SQLite
export DATABASE_URL="postgresql://finance:secret@localhost:5432/finance_db"

# Or in docker-compose.yml, add a postgres service
```

### Database: SQLite (Development, default)

No configuration needed. Data stored in `dataloader/finance_data.db`.

---

## 📊 Data Pipeline (12 Scheduled Jobs)

| Job | Schedule | Tables | Description |
|-----|----------|--------|-------------|
| Extract Yahoo Prices | Every minute | `raw_yahoo_prices` | Fetch current prices |
| Extract Yahoo Fundamentals | Daily 6 AM | `raw_yahoo_fundamentals` | Fetch PE, EPS, etc |
| Extract IBKR Prices | Every 2 min | `raw_ibkr_prices` | Real-time from IB Gateway |
| Extract Option Metrics - B3 | Every 15 min | `option_metrics` | Greeks, bid/ask for B3 |
| Extract Option Metrics - US | Every 30 min | `option_metrics` | Greeks, bid/ask for US |
| Extract Option Metrics - OMX | Every hour | `option_metrics` | Greeks, bid/ask for OMX |
| Transform Prices | Every 2 min | `realtime_prices` | Normalize price data |
| Transform IBKR Prices | Every 3 min | `realtime_prices` | IBKR → normalized |
| Transform Fundamentals | Daily 6:30 AM | `fundamentals` | Normalize fundamentals |
| Stock List Loader | Weekly Sun 5 AM | `stocks` | Refresh stock list |
| Dividends Loader | Weekly Mon 7 AM | `dividends` | Fetch dividend data |
| Historical Prices | Weekdays 6:30 AM | `historical_prices` | 12 months OHLCV |
| Index Performance | Weekly Mon 8 AM | `index_performance` | IBOV, OMXS30 data |
| **Calculate Stock Metrics** | **Daily 7 AM** | **`stock_metrics`** | **RSI, MACD, performance** |
| **Update Market Movers** | **Every 5 min** | **`market_movers`** | **Top gainers/losers** |

---

## 🏦 Markets Covered

| Market | Exchange | Stocks | Currency | Indices |
|--------|----------|--------|----------|---------|
| 🇧🇷 Brazil | B3 | 21 | BRL | IBOV |
| 🇸🇪 Sweden | OMX | 30 | SEK | OMXS30, OMXSPI |
| 🇺🇸 USA | NASDAQ/NYSE | 20 | USD | S&P 500 |

---

## 🧪 Tests

```bash
# Unit tests (12 — mock-based)
pytest test_mcp_server.py -v

# Integration tests (11 — real database)
pytest test_integration.py -v

# All tests
pytest -v
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `mcp` | Model Context Protocol framework |
| `ib_insync` | Interactive Brokers API |
| `yfinance` | Yahoo Finance data |
| `sqlalchemy` | Database ORM (SQLite + PostgreSQL) |
| `fastapi` | Data Loader Web API |
| `apscheduler` | Job scheduling |
| `pandas` / `numpy` | Technical indicator calculations |
| `psycopg2-binary` | PostgreSQL driver (optional) |

---

## 📄 License

MIT
