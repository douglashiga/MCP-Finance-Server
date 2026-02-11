# 🏦 MCP Finance Server

A professional-grade **Model Context Protocol (MCP)** server for financial data, powered by **Interactive Brokers** (real-time) and **Yahoo Finance** (fundamentals).

Built for LLM agents that need structured, reliable access to market data, options, account info, and company fundamentals.

---

## 📐 Architecture

```
MCP_Finance/
├── core/                          # Infrastructure Layer
│   ├── connection.py              # IB Singleton, auto-reconnect, heartbeat
│   ├── rate_limiter.py            # Token bucket (5 req/sec)
│   └── decorators.py              # @require_connection
├── services/                      # Business Logic Layer
│   ├── market_service.py          # Real-time price (IB)
│   ├── history_service.py         # OHLCV bars + 30s cache (IB)
│   ├── option_service.py          # Option chains & Greeks (IB)
│   ├── account_service.py         # Balances, margin, positions (IB)
│   └── yahoo_service.py           # Fundamentals, dividends, financials (Yahoo)
├── mcp_server.py                  # MCP entry point (thin layer)
├── Dockerfile
├── docker-compose.yml             # IB Gateway + MCP Server
├── test_mcp_server.py             # 12 tests
└── client.py                      # Test client
```

### Data Flow

```
LLM Agent
    │
    ▼
┌──────────────┐
│  MCP Server  │  ← mcp_server.py (tools, resources, prompts)
└──────┬───────┘
       │
  ┌────┴────┐
  ▼         ▼
┌─────┐  ┌───────┐
│ IB  │  │ Yahoo │  ← services/
└──┬──┘  └───────┘
   ▼
┌──────────┐
│IB Gateway│  ← Docker or local
└──────────┘
```

---

## 🛠 Tools (12)

### Interactive Brokers (Real-time)

| Tool | Description | Example |
|------|-------------|---------|
| `get_stock_price(symbol)` | Live price, bid/ask, volume | `get_stock_price("AAPL")` |
| `get_historical_data(symbol, duration, bar_size)` | OHLCV bars (cached 30s) | `get_historical_data("AAPL", "1 M", "1 day")` |
| `search_symbol(query)` | Find contracts on IB | `search_symbol("AAPL")` |
| `get_account_summary()` | Balance, margin, liquidity | `get_account_summary()` |
| `get_option_chain(symbol)` | Strikes & expirations | `get_option_chain("AAPL")` |
| `get_option_greeks(symbol, date, strike, right)` | Delta, gamma, theta, vega, IV | `get_option_greeks("AAPL", "20240119", 150.0, "C")` |

### Yahoo Finance (Fundamentals)

| Tool | Description | Example |
|------|-------------|---------|
| `get_fundamentals(symbol)` | PE, EPS, market cap, margins | `get_fundamentals("AAPL")` |
| `get_dividends(symbol)` | Yield, rate, payout history | `get_dividends("KO")` |
| `get_company_info(symbol)` | Sector, industry, description | `get_company_info("TSLA")` |
| `get_financial_statements(symbol)` | Income, balance sheet, cash flow | `get_financial_statements("MSFT")` |
| `get_exchange_info(symbol)` | Timezone, hours, market state | `get_exchange_info("VOW3.DE")` |
| `yahoo_search(query)` | Discover tickers by keyword | `yahoo_search("Brazilian banks")` |

### Resources

| URI | Description |
|-----|-------------|
| `finance://status` | Connection health + server time |
| `finance://account/summary` | Account balances & margin |
| `finance://portfolio/positions` | Current portfolio positions |
| `finance://market/ticker/{symbol}` | Real-time snapshot |

### Response Format

All tools return a standardized response:

```json
// Success
{"success": true, "data": {"symbol": "AAPL", "price": 150.25}}

// Error
{"success": false, "error": "Timeout fetching market data"}
```

---

## 🚀 Quick Start

### Option 1: Docker (Recommended)

Everything runs in containers — IB Gateway + MCP Server.

**1. Clone and configure:**

```bash
cd MCP_Finance
cp .env.example .env
```

**2. Edit `.env` with your IB credentials:**

```env
TWS_USERID=your_username
TWS_PASSWORD=your_password
TRADING_MODE=paper          # 'paper' or 'live'
```

**3. Start everything:**

```bash
docker compose up -d
```

That's it! The MCP server will:
- Wait for IB Gateway to be healthy
- Auto-connect with exponential backoff
- Start heartbeat monitoring

**4. Check status:**

```bash
docker compose logs -f mcp-finance
```

**5. Access VNC (optional debug):**

Open `vnc://localhost:5900` to see the IB Gateway UI.

---

### Option 2: Local Development

**1. Prerequisites:**
- Python 3.10+
- IB Gateway or TWS running locally on port 4001

**2. Install dependencies:**

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

**3. Run the server:**

```bash
python mcp_server.py
```

**4. Run tests:**

```bash
pytest test_mcp_server.py -v
```

---

## ⚙️ Configuration

All settings are configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `IB_HOST` | `127.0.0.1` | IB Gateway host |
| `IB_PORT` | `4001` | IB Gateway API port |
| `IB_CLIENT_ID` | `1` | Client ID for IB connection |
| `IB_READ_ONLY` | `true` | Enforce read-only mode |
| `IB_MAX_RETRIES` | `5` | Max connection retry attempts |
| `LOG_LEVEL` | `INFO` | Logging level |
| `TIMEOUT_MARKET` | `5` | Market data timeout (seconds) |
| `TIMEOUT_HISTORY` | `15` | Historical data timeout (seconds) |
| `TIMEOUT_ACCOUNT` | `5` | Account data timeout (seconds) |

---

## 🔒 Production Features (24/7)

| Feature | Description |
|---------|-------------|
| **Auto-Reconnect** | Detects disconnections and reconnects automatically |
| **Heartbeat** | Checks connection health every 60 seconds |
| **Graceful Shutdown** | Handles SIGTERM/SIGINT cleanly |
| **Rate Limiting** | 5 requests/second to respect IB limits |
| **Concurrency Control** | Semaphore(10) for market data requests |
| **TTL Cache** | Historical data cached for 30 seconds |
| **Read-Only by Design** | No trading methods exist — only market data and analysis |
| **Contract Validation** | `qualifyContractsAsync` before data requests |

---

## 🔌 MCP Client Integration

To connect a Claude Desktop or other MCP client, add to your MCP config:

```json
{
  "mcpServers": {
    "finance": {
      "command": "python",
      "args": ["/path/to/MCP_Finance/mcp_server.py"],
      "env": {
        "IB_HOST": "127.0.0.1",
        "IB_PORT": "4001"
      }
    }
  }
}
```

---

## 🧪 Tests

```bash
# Run all tests (12 tests)
pytest test_mcp_server.py test_options.py -v

# Expected output:
# test_mcp_server.py::test_get_stock_price PASSED
# test_mcp_server.py::test_get_historical_data PASSED
# test_mcp_server.py::test_search_symbol PASSED
# test_mcp_server.py::test_get_account_summary PASSED
# test_mcp_server.py::test_get_option_chain PASSED
# test_mcp_server.py::test_get_option_greeks PASSED
# test_mcp_server.py::test_get_fundamentals PASSED
# test_mcp_server.py::test_get_dividends PASSED
# test_mcp_server.py::test_get_company_info PASSED
# test_mcp_server.py::test_get_financial_statements PASSED
# test_mcp_server.py::test_get_exchange_info PASSED
# test_mcp_server.py::test_yahoo_search PASSED
# ======================== 12 passed ========================
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `mcp` | Model Context Protocol framework |
| `ib_insync` | Interactive Brokers API |
| `yfinance` | Yahoo Finance data |
| `pytest` / `pytest-asyncio` | Testing |

---

## 📄 License

MIT
