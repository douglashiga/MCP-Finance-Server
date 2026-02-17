# Method Redesign - Specific Intent-Based Tools

## Philosophy

**LLM-Facing (MCP Tools):** Métodos específicos com nomes descritivos
**Backend (Services):** Métodos genéricos para reutilização (DRY)

**Princípios:**
1. **1 Intent = 1 Method:** Cada pergunta do usuário mapeia para 1 método claro
2. **Nomes Descritivos:** `get_option_premium` > `get_option_screener`
3. **Parâmetros Mínimos:** Apenas o essencial para aquele intent
4. **Backend Genérico:** Services usam helpers internos (DRY)

---

## Redesigned Tool Catalog

### 1. Market Data (12 tools) ✅

#### Price & Quotes
```python
@mcp.tool()
async def get_stock_price(symbol: str, market: str = 'sweden') -> Dict:
    """Get current stock price. Example: "Qual o preço da Nordea?"""

@mcp.tool()
async def get_stock_quote(symbol: str, market: str = 'sweden') -> Dict:
    """Get full quote (bid/ask/volume/change). Example: "Me mostre a cotação completa da SEB"""

@mcp.tool()
async def get_historical_prices(symbol: str, period: str = '1m', interval: str = '1d') -> Dict:
    """Get OHLCV history. Example: "Histórico de 3 meses da Volvo"""
```

#### Search & Discovery
```python
@mcp.tool()
async def search_stock_by_ticker(ticker: str, market: str = 'sweden') -> Dict:
    """Search specifically by symbol/ticker. Example: "Busca ticker NDA" """

@mcp.tool()
async def search_stock_by_name(name: str, market: str = 'sweden') -> Dict:
    """Search specifically by company name. Example: "Busca banco sueco" """

@mcp.tool()
async def search_stock_by_profile(query: str, market: str = 'sweden') -> Dict:
    """Search by keywords in business description. Example: "Ações de energia solar" """
```

#### Sector Performance
```python
@mcp.tool()
async def get_sector_performance(market: str = 'sweden') -> Dict:
    """Sector performance today. Example: "Como estão os setores hoje?""""

@mcp.tool()
async def get_market_status(market: str = 'sweden') -> Dict:
    """Market open/closed status. Example: "A bolsa está aberta?""""
```

---

### 2. Fundamentals (10 tools) ✅

#### Company Info
```python
@mcp.tool()
async def get_company_profile(symbol: str) -> Dict:
    """Company description, sector, employees. Example: "Me fale sobre a Nordea""""

@mcp.tool()
async def get_company_financials(symbol: str) -> Dict:
    """P/E, Market Cap, Revenue, Profit. Example: "Fundamentos da SEB""""

@mcp.tool()
async def get_financial_statements(symbol: str, statement_type: str = 'income') -> Dict:
    """Balance sheet, income, cash flow. Example: "Balanço da Volvo""""
```

#### Dividends
```python
@mcp.tool()
async def get_dividend_yield(symbol: str) -> Dict:
    """Current dividend yield. Example: "Qual o dividend yield da Nordea?""""

@mcp.tool()
async def get_dividend_history(symbol: str, period: str = '2y') -> Dict:
    """Historical dividends. Example: "Histórico de dividendos da SEB""""

@mcp.tool()
async def get_next_dividend(symbol: str) -> Dict:
    """Next dividend date/amount. Example: "Quando a Volvo paga dividendo?""""
```

#### Earnings
```python
@mcp.tool()
async def get_next_earnings(symbol: str) -> Dict:
    """Next earnings date. Example: "Quando sai o resultado da Nordea?""""

@mcp.tool()
async def get_earnings_history(symbol: str, limit: int = 10) -> Dict:
    """Past earnings. Example: "Últimos resultados da SEB""""

@mcp.tool()
async def get_earnings_surprise(symbol: str) -> Dict:
    """Earnings vs estimates. Example: "A Volvo bateu as estimativas?""""
```

---

### 3. Screener & Rankings (15 tools) ✅

#### Performance Rankings
```python
@mcp.tool()
async def get_top_gainers(market: str = 'sweden', period: str = '1d', limit: int = 10) -> Dict:
    """Biggest gainers. Example: "Maiores altas hoje""""

@mcp.tool()
async def get_top_losers(market: str = 'sweden', period: str = '1d', limit: int = 10) -> Dict:
    """Biggest losers. Example: "Maiores quedas hoje""""

@mcp.tool()
async def get_most_active(market: str = 'sweden', limit: int = 10) -> Dict:
    """Most traded stocks. Example: "Ações mais negociadas""""
```

#### Technical Signals
```python
@mcp.tool()
async def get_oversold_stocks(market: str = 'sweden', limit: int = 10) -> Dict:
    """RSI < 30. Example: "Ações sobrevendidas""""

@mcp.tool()
async def get_overbought_stocks(market: str = 'sweden', limit: int = 10) -> Dict:
    """RSI > 70. Example: "Ações sobrecompradas""""

@mcp.tool()
async def get_stocks_near_support(market: str = 'sweden', limit: int = 10) -> Dict:
    """Near Bollinger lower band. Example: "Ações perto do suporte""""

@mcp.tool()
async def get_stocks_near_resistance(market: str = 'sweden', limit: int = 10) -> Dict:
    """Near Bollinger upper band. Example: "Ações perto da resistência""""
```

#### Fundamental Rankings
```python
@mcp.tool()
async def get_highest_dividend_yield(market: str = 'sweden', limit: int = 10) -> Dict:
    """Top dividend payers. Example: "Maiores pagadores de dividendo""""

@mcp.tool()
async def get_lowest_pe_ratio(market: str = 'sweden', limit: int = 10) -> Dict:
    """Cheapest by P/E. Example: "Ações mais baratas por P/E""""

@mcp.tool()
async def get_largest_market_cap(market: str = 'sweden', limit: int = 10) -> Dict:
    """Biggest companies. Example: "Maiores empresas da Suécia""""
```

#### Sector Filtering
```python
@mcp.tool()
async def get_stocks_by_sector(sector: str, market: str = 'sweden', limit: int = 50) -> Dict:
    """Filter by sector. Example: "Bancos suecos""""

@mcp.tool()
async def get_stocks_by_industry(industry: str, market: str = 'sweden', limit: int = 50) -> Dict:
    """Filter by industry. Example: "Empresas de tecnologia""""
```

#### Technical Analysis
```python
@mcp.tool()
async def get_stock_rsi(symbol: str, period: int = 14) -> Dict:
    """RSI indicator. Example: "Qual o RSI da Nordea?""""

@mcp.tool()
async def get_stock_macd(symbol: str) -> Dict:
    """MACD indicator. Example: "MACD da SEB""""

@mcp.tool()
async def get_stock_bollinger_bands(symbol: str) -> Dict:
    """Bollinger Bands. Example: "Bandas de Bollinger da Volvo""""
```

---

### 4. Options - Discovery (5 tools) ✅

```python
@mcp.tool()
async def get_option_expirations(symbol: str) -> Dict:
    """Available expiration dates. Example: "Quais vencimentos de opções da Nordea?""""

@mcp.tool()
async def get_option_strikes(symbol: str, expiry: str) -> Dict:
    """Available strikes for expiry. Example: "Strikes disponíveis para março""""

@mcp.tool()
async def get_option_chain(symbol: str, expiry: str = None) -> Dict:
    """Full option chain. Example: "Cadeia de opções da SEB""""

@mcp.tool()
async def find_atm_options(symbol: str, expiry: str = None) -> Dict:
    """At-the-money options. Example: "Opções ATM da Volvo""""

@mcp.tool()
async def find_otm_options(symbol: str, expiry: str = None, pct_otm: float = 5.0) -> Dict:
    """Out-of-the-money options. Example: "Puts 5% OTM da Nordea""""
```

---

### 5. Options - Pricing & Greeks (10 tools) ✅ **NEW**

#### Pricing
```python
@mcp.tool()
async def get_option_premium(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """
    Get option premium (bid/ask/last).
    
    Use case: "Quanto custa a call 120 da Nordea?"
    Alert use case: "Me avisa quando a put 115 custar menos de 2 SEK"
    """

@mcp.tool()
async def get_option_bid(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Bid price only. Example: "Qual o bid da put 115?""""

@mcp.tool()
async def get_option_ask(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Ask price only. Example: "Qual o ask da call 120?""""

@mcp.tool()
async def get_option_spread(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Bid-ask spread. Example: "Qual o spread dessa opção?""""
```

#### Greeks
```python
@mcp.tool()
async def get_option_iv(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Implied volatility. Example: "Qual a IV da call 120?""""

@mcp.tool()
async def get_option_delta(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Delta (price sensitivity). Example: "Qual o delta dessa put?""""

@mcp.tool()
async def get_option_theta(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Theta (time decay). Example: "Quanto essa opção perde por dia?""""

@mcp.tool()
async def get_option_gamma(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Gamma (delta sensitivity). Example: "Qual o gamma dessa call?""""

@mcp.tool()
async def get_option_vega(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """Vega (IV sensitivity). Example: "Qual o vega dessa put?""""

@mcp.tool()
async def get_option_greeks(symbol: str, strike: float, expiry: str, right: str) -> Dict:
    """All Greeks together. Example: "Me mostre todos os greeks dessa opção""""
```

---

### 6. Options - Screening (8 tools) ✅

#### By Delta
```python
@mcp.tool()
async def find_options_by_delta(symbol: str, target_delta: float, right: str, expiry: str = None) -> Dict:
    """Find options near target delta. Example: "Puts com delta 0.30""""

@mcp.tool()
async def find_delta_neutral_options(symbol: str, expiry: str = None) -> Dict:
    """Delta ~0.50 options. Example: "Opções delta neutral da Nordea""""
```

#### By IV
```python
@mcp.tool()
async def find_high_iv_options(symbol: str, min_iv: float = 0.30, expiry: str = None) -> Dict:
    """High IV options. Example: "Opções com IV acima de 30%""""

@mcp.tool()
async def find_low_iv_options(symbol: str, max_iv: float = 0.20, expiry: str = None) -> Dict:
    """Low IV options. Example: "Opções baratas por IV""""
```

#### By Liquidity
```python
@mcp.tool()
async def find_liquid_options(symbol: str, min_volume: int = 100, expiry: str = None) -> Dict:
    """Liquid options. Example: "Opções com volume alto""""

@mcp.tool()
async def find_tight_spread_options(symbol: str, max_spread_pct: float = 5.0, expiry: str = None) -> Dict:
    """Tight bid-ask spread. Example: "Opções com spread baixo""""
```

#### By Premium
```python
@mcp.tool()
async def find_options_by_premium(symbol: str, min_premium: float = None, max_premium: float = None, right: str = None) -> Dict:
    """Filter by premium range. Example: "Puts entre 2 e 5 SEK""""

@mcp.tool()
async def find_cheap_options(symbol: str, max_premium: float = 2.0, right: str = None) -> Dict:
    """Cheap options. Example: "Opções abaixo de 2 SEK""""
```

---

### 7. Wheel Strategy (15 tools) ✅

#### Put Selection
```python
@mcp.tool()
async def get_wheel_put_candidates(symbol: str, delta_min: float = 0.25, delta_max: float = 0.35, dte_min: int = 4, dte_max: int = 10) -> Dict:
    """Best puts to sell. Example: "Qual put vender essa semana?""""

@mcp.tool()
async def get_wheel_put_return(symbol: str, strike: float, expiry: str, premium: float) -> Dict:
    """Annualized return. Example: "Qual o retorno dessa put?""""

@mcp.tool()
async def get_wheel_put_breakeven(symbol: str, strike: float, premium: float) -> Dict:
    """Break-even price. Example: "Qual o break-even dessa put?""""

@mcp.tool()
async def get_wheel_put_assignment_probability(symbol: str, strike: float, expiry: str) -> Dict:
    """Assignment probability (via delta). Example: "Qual a chance de assignment?""""
```

#### Capital Management
```python
@mcp.tool()
async def get_wheel_contract_capacity(symbol: str, capital: float, strike: float = None, margin_pct: float = 1.0) -> Dict:
    """How many contracts. Example: "Com 200k SEK, quantos contratos?"```

@mcp.tool()
async def get_wheel_capital_required(symbol: str, strike: float, contracts: int = 1, margin_pct: float = 1.0) -> Dict:
    """Capital needed. Example: "Quanto preciso para 5 contratos?"```

@mcp.tool()
async def get_wheel_margin_requirement(symbol: str, strike: float, contracts: int = 1) -> Dict:
    """Margin required. Example: "Qual a margem necessária?"```
```

#### Risk Analysis
```python
@mcp.tool()
async def analyze_wheel_put_risk(symbol: str, strike: float, premium: float, drop_pct: float = 5.0) -> Dict:
    """Risk if stock drops. Example: "Risco se cair 5%?"```

@mcp.tool()
async def simulate_wheel_drawdown(symbol: str, strike: float, premium: float, drop_pct: float = 10.0) -> Dict:
    """Drawdown scenario. Example: "Perda se cair 10%?"```

@mcp.tool()
async def get_wheel_event_risk(symbol: str, days_ahead: int = 14) -> Dict:
    """Events in next N days. Example: "Eventos nas próximas 2 semanas?"```
```

#### Covered Call (Post-Assignment)
```python
@mcp.tool()
async def get_wheel_call_candidates(symbol: str, cost_basis: float, delta_min: float = 0.25, delta_max: float = 0.35) -> Dict:
    """Calls to sell after assignment. Example: "Qual call vender após assignment?"```

@mcp.tool()
async def get_wheel_call_return(symbol: str, strike: float, expiry: str, premium: float, cost_basis: float) -> Dict:
    """Total return (premium + upside). Example: "Retorno total dessa call?"```
```

#### Multi-Stock & Portfolio
```python
@mcp.tool()
async def build_wheel_portfolio(capital: float, symbols: List[str] = None, market: str = 'sweden') -> Dict:
    """Diversified Wheel plan. Example: "Plano Wheel com 500k SEK"```

@mcp.tool()
async def stress_test_wheel_portfolio(capital: float, drop_pct: float = 20.0, symbols: List[str] = None) -> Dict:
    """Stress test. Example: "Impacto de queda de 20%?"```

@mcp.tool()
async def compare_wheel_timing(symbol: str, wait_drop_pct: float = 3.0) -> Dict:
    """Start now vs wait. Example: "Melhor entrar agora ou esperar?"```
```

---

### 8. Market Intelligence (8 tools) ✅

```python
@mcp.tool()
async def get_latest_news(symbol: str, limit: int = 10) -> Dict:
    """Recent news. Example: "Notícias da Nordea"```

@mcp.tool()
async def get_news_sentiment(symbol: str) -> Dict:
    """News sentiment score. Example: "Sentimento das notícias da SEB"```

@mcp.tool()
async def get_institutional_holders(symbol: str, limit: int = 20) -> Dict:
    """Top institutional holders. Example: "Quem são os maiores holders?"```

@mcp.tool()
async def get_insider_trades(symbol: str, limit: int = 20) -> Dict:
    """Recent insider trades. Example: "Insiders estão comprando?"```

@mcp.tool()
async def get_analyst_ratings(symbol: str) -> Dict:
    """Analyst recommendations. Example: "O que analistas dizem da Volvo?"```

@mcp.tool()
async def get_analyst_price_target(symbol: str) -> Dict:
    """Price target consensus. Example: "Qual o preço-alvo da Nordea?"```

@mcp.tool()
async def get_short_interest(symbol: str) -> Dict:
    """Short interest %. Example: "Quanto está vendido da SEB?"```

@mcp.tool()
async def get_analyst_upgrades_downgrades(symbol: str, days: int = 30) -> Dict:
    """Recent rating changes. Example: "Mudanças de rating recentes"```
```

---

### 9. Events & Calendar (10 tools) ✅

#### Corporate Events
```python
@mcp.tool()
async def get_upcoming_earnings(market: str = 'sweden', days_ahead: int = 14, limit: int = 20) -> Dict:
    """Earnings calendar. Example: "Resultados nas próximas 2 semanas"```

@mcp.tool()
async def get_upcoming_dividends(market: str = 'sweden', days_ahead: int = 30, limit: int = 20) -> Dict:
    """Dividend calendar. Example: "Dividendos no próximo mês"```

@mcp.tool()
async def get_upcoming_splits(market: str = 'sweden', days_ahead: int = 90) -> Dict:
    """Stock splits. Example: "Splits nos próximos 3 meses"```

@mcp.tool()
async def get_upcoming_ipos(market: str = 'sweden', days_ahead: int = 60) -> Dict:
    """IPO calendar. Example: "IPOs nos próximos 2 meses"```
```

#### Macro Events
```python
@mcp.tool()
async def get_upcoming_cpi_releases(market: str = 'sweden', days_ahead: int = 30) -> Dict:
    """CPI releases. Example: "Quando sai o CPI?"```

@mcp.tool()
async def get_upcoming_gdp_releases(market: str = 'sweden', days_ahead: int = 90) -> Dict:
    """GDP releases. Example: "Quando sai o PIB?"```

@mcp.tool()
async def get_upcoming_interest_rate_decisions(market: str = 'sweden', days_ahead: int = 180) -> Dict:
    """Central bank meetings. Example: "Próximas reuniões do Riksbank"```
```

#### Event Impact
```python
@mcp.tool()
async def get_high_impact_events(market: str = 'sweden', days_ahead: int = 14) -> Dict:
    """High volatility events. Example: "Eventos de alto impacto"```

@mcp.tool()
async def get_events_for_stock(symbol: str, days_ahead: int = 30) -> Dict:
    """All events for stock. Example: "Eventos da Nordea no próximo mês"```

@mcp.tool()
async def get_event_calendar(market: str = 'sweden', category: str = None, days_ahead: int = 30) -> Dict:
    """Full event calendar. Example: "Calendário completo de eventos"```
```

---

## Summary

**Total Tools:** 109 (Refined for purely financial analysis)
- Market Data: 12
- Fundamentals: 10
- Screener: 15
- Options Discovery: 5
- Options Pricing/Greeks: 10
- Options Screening: 8
- Wheel Strategy: 15
- Market Intelligence: 8
- Events: 10
- Non-Financial (Jobs, Server, Account): Removed for security and focus.

**Key Additions:**
✅ **Option Premium Tools** (bid/ask/spread) - Critical for alerts
✅ **Individual Greek Tools** (IV, delta, theta, gamma, vega)
✅ **Specific Screener Tools** (oversold, overbought, near support/resistance)
✅ **Event-Specific Tools** (CPI, GDP, interest rates)
✅ **Wheel Risk Tools** (breakeven, assignment probability, margin)

---

## Backend Implementation (DRY)

All specific tools use generic helpers:

```python
# services/option_service.py

class OptionService:
    @staticmethod
    def _get_option_field(symbol, strike, expiry, right, field):
        """Generic helper - used by all specific tools"""
        # Single implementation, reused everywhere
        
    @staticmethod
    def get_option_premium(symbol, strike, expiry, right):
        return _get_option_field(symbol, strike, expiry, right, ['bid', 'ask', 'last'])
    
    @staticmethod
    def get_option_iv(symbol, strike, expiry, right):
        return _get_option_field(symbol, strike, expiry, right, ['iv'])
    
    @staticmethod
    def get_option_delta(symbol, strike, expiry, right):
        return _get_option_field(symbol, strike, expiry, right, ['delta'])
    
    # ... etc
```

**Benefits:**
- ✅ LLM vê 128 métodos específicos (fácil escolha)
- ✅ Backend tem 1 implementação genérica (DRY)
- ✅ Fácil adicionar novos métodos (wrapper de 2 linhas)

---

## Next Steps

1. ✅ Aprovar essa estrutura
2. Implementar helpers genéricos nos services
3. Criar wrappers MCP específicos
4. Atualizar documentação
5. Testar com LLM real

Quer que eu implemente isso?
