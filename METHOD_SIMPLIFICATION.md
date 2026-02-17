# Method Simplification Proposal

## Executive Summary

**Current State:** 77 MCP tools
**Proposed State:** 55 MCP tools (-22 tools, -29% reduction)

**Goals:**
1. **Reduce LLM Confusion:** Eliminate overlapping tools with unclear boundaries
2. **Improve Discoverability:** Clearer naming and intent-specific tools
3. **Maintain Functionality:** No loss of capabilities, only consolidation
4. **Better Documentation:** Each tool has one clear purpose

---

## Detailed Analysis

### Category 1: Overlapping Historical Data

#### Issue
```python
# Current: 2 tools for the same thing
get_historical_data(symbol, duration='1 D', bar_size='1 hour')  # IBKR
get_historical_data_cached(symbol, period='1y', interval='1d')  # Yahoo/Local
```

**Problem:**
- LLM doesn't know which to use
- Different parameter names (`duration` vs `period`, `bar_size` vs `interval`)
- Both return OHLCV data

**Solution:**
```python
# Proposed: 1 unified tool
get_historical_data(symbol, period='1y', interval='1d', source='auto')
# source='auto' → Try local first, fallback to IBKR if needed
# source='ibkr' → Force IBKR
# source='local' → Force local cache
```

**Migration:**
- Deprecate `get_historical_data` (old IBKR-only version)
- Rename `get_historical_data_cached` → `get_historical_data`
- Add `source` parameter for explicit control

---

### Category 2: Dividend Redundancy

#### Issue
```python
# Current: 2 tools
get_dividends(symbol)           # Returns current dividend info
get_dividend_history(symbol)    # Returns historical dividends
```

**Problem:**
- Unclear distinction: "current" vs "history" is ambiguous
- Most use cases need history anyway

**Solution:**
```python
# Proposed: 1 tool with period filter
get_dividends(symbol, period='2y', upcoming=False)
# period='2y' → Last 2 years (default)
# upcoming=True → Include future declared dividends
```

**Migration:**
- Deprecate `get_dividends` (old version)
- Rename `get_dividend_history` → `get_dividends`
- Add `upcoming` parameter

---

### Category 3: Company Info Mega-Tool

#### Issue
```python
# Current: 2 tools
get_company_info(symbol)              # Basic profile
get_comprehensive_stock_info(symbol)  # Everything (price + fundamentals + dividends + news)
```

**Problem:**
- `get_comprehensive_stock_info` is a mega-tool (anti-pattern)
- LLM doesn't know when to use specific vs comprehensive
- Comprehensive tool is slow (multiple queries)

**Solution:**
```python
# Proposed: Remove mega-tool, use composition
# LLM should call multiple specific tools:
get_company_info(symbol)      # Profile only
get_fundamentals(symbol)      # Financials
get_dividends(symbol)         # Dividends
get_news(symbol)              # News
```

**Migration:**
- Deprecate `get_comprehensive_stock_info`
- Update LLM prompts to use composition
- Keep `get_company_info` as lightweight profile tool

---

### Category 4: Option Chain Confusion

#### Issue
```python
# Current: 3 tools for option chains
get_option_chain(symbol)                    # Returns expirations + strikes
get_option_chain_snapshot(symbol, expiry)   # Returns full chain with Greeks
get_options_data(symbol, expiration_date)   # IBKR live data
```

**Problem:**
- Unclear when to use each
- `get_option_chain` returns minimal data (discovery)
- `get_option_chain_snapshot` returns full data (analysis)
- `get_options_data` is redundant

**Solution:**
```python
# Proposed: 1 unified tool with detail level
get_option_chain(symbol, expiry=None, detail='full')
# detail='summary' → Just expirations + strikes (fast)
# detail='full' → Full chain with Greeks (default)
# expiry=None → All expirations
# expiry='2026-03-21' → Specific expiration
```

**Migration:**
- Deprecate `get_option_chain_snapshot`
- Deprecate `get_options_data`
- Enhance `get_option_chain` with `detail` parameter

---

### Category 5: Option Greeks Redundancy

#### Issue
```python
# Current: 2 ways to get Greeks
get_option_greeks(symbol, last_trade_date, strike, right)  # Specific contract
get_option_screener(symbol, expiry, right, min_delta, max_delta)  # Filtered list
```

**Problem:**
- `get_option_greeks` is too specific (requires exact contract)
- `get_option_screener` can do the same with filters

**Solution:**
```python
# Proposed: Remove get_option_greeks, use screener
get_option_screener(symbol, expiry, strike, right)
# If strike is specified → Returns single contract (like old get_option_greeks)
# If strike is None → Returns filtered list
```

**Migration:**
- Deprecate `get_option_greeks`
- Enhance `get_option_screener` to handle single-contract queries

---

### Category 6: RSI Redundancy

#### Issue
```python
# Current: 3 tools for RSI
get_highest_rsi(market, limit)
get_lowest_rsi(market, limit)
get_technical_signals(market, signal_type='oversold')
```

**Problem:**
- `get_highest_rsi` is redundant with `get_technical_signals(signal_type='overbought')`
- `get_lowest_rsi` is redundant with `get_technical_signals(signal_type='oversold')`

**Solution:**
```python
# Proposed: Remove specific RSI tools
get_technical_signals(market, signal_type='overbought|oversold|neutral', limit=20)
# signal_type='overbought' → RSI > 70 (replaces get_highest_rsi)
# signal_type='oversold' → RSI < 30 (replaces get_lowest_rsi)
```

**Migration:**
- Deprecate `get_highest_rsi`
- Deprecate `get_lowest_rsi`
- Keep `get_technical_signals` as unified tool

---

### Category 7: Earnings Fragmentation

#### Issue
```python
# Current: 3 tools for earnings
get_earnings_events(symbol, upcoming_only=False)
get_earnings_history(symbol, limit=10)
get_earnings_calendar(symbol)
```

**Problem:**
- All three return earnings data
- Unclear distinction between "events", "history", "calendar"

**Solution:**
```python
# Proposed: 1 unified tool
get_earnings_events(symbol, upcoming_only=False, limit=20)
# upcoming_only=False → Historical + upcoming (replaces get_earnings_history)
# upcoming_only=True → Only future (replaces get_earnings_calendar)
```

**Migration:**
- Deprecate `get_earnings_history`
- Deprecate `get_earnings_calendar`
- Keep `get_earnings_events` as unified tool

---

### Category 8: Search Redundancy

#### Issue
```python
# Current: 2 search tools
search_symbol(query)    # Local DB fuzzy search
yahoo_search(query)     # Yahoo API search
```

**Problem:**
- LLM doesn't know which to use
- Both return similar results

**Solution:**
```python
# Proposed: 1 unified search
search_symbol(query, source='auto')
# source='auto' → Try local first, fallback to Yahoo
# source='local' → Local DB only
# source='yahoo' → Yahoo API only
```

**Migration:**
- Deprecate `yahoo_search`
- Enhance `search_symbol` with `source` parameter

---

### Category 9: Query Tools (Generic Anti-Pattern)

#### Issue
```python
# Current: Generic query tools
query_local_stocks(country, sector)
query_local_fundamentals(symbol)
```

**Problem:**
- Too generic, overlap with screener
- LLM doesn't know when to use vs specific tools

**Solution:**
```python
# Proposed: Remove generic queries
# Use specific tools instead:
get_stock_screener(market, sector, sort_by, limit)  # Replaces query_local_stocks
get_fundamentals(symbol)                            # Replaces query_local_fundamentals
```

**Migration:**
- Deprecate `query_local_stocks`
- Deprecate `query_local_fundamentals`

---

### Category 10: Wheel Redundancy

#### Issue
```python
# Current: Redundant Wheel tools
get_wheel_put_candidates(symbol, delta_min, delta_max, dte_min, dte_max)
get_wheel_put_annualized_return(symbol, target_dte)  # Already in put_candidates
compare_wheel_premiums(symbol_a, symbol_b)           # Can use option_screener
```

**Problem:**
- `get_wheel_put_annualized_return` returns data already in `put_candidates`
- `compare_wheel_premiums` is redundant with `get_option_screener`

**Solution:**
```python
# Proposed: Remove redundant tools
get_wheel_put_candidates(symbol, ...)  # Already includes annualized return
get_option_screener(symbol, ...)       # Use for premium comparison
```

**Migration:**
- Deprecate `get_wheel_put_annualized_return`
- Deprecate `compare_wheel_premiums`

---

### Category 11: Technical Analysis Overlap

#### Issue
```python
# Current: 2 tools
get_technical_analysis(symbol, period)
get_technical_signals(market, signal_type)
```

**Problem:**
- `get_technical_analysis` returns RSI/MACD/Bollinger for one symbol
- `get_technical_signals` returns filtered list by signal type
- Overlapping functionality

**Solution:**
```python
# Proposed: Keep both but clarify intent
get_technical_analysis(symbol, period)  # Single-symbol deep dive
get_technical_signals(market, signal_type, limit)  # Market-wide screening
```

**Migration:**
- Keep both (different intents)
- Update descriptions to clarify use cases

---

### Category 12: Fundamental Rankings

#### Issue
```python
# Current: 2 tools
get_fundamental_rankings(market, metric, limit, sector)
get_stock_screener(market, sector, sort_by, limit)
```

**Problem:**
- `get_fundamental_rankings` is redundant with `get_stock_screener(sort_by=metric)`

**Solution:**
```python
# Proposed: Remove rankings, use screener
get_stock_screener(market, sector, sort_by='market_cap|pe_ratio|dividend_yield', limit)
```

**Migration:**
- Deprecate `get_fundamental_rankings`

---

### Category 13: Help Tool Alias

#### Issue
```python
# Current: 2 identical tools
describe_tool(tool_name)
help_tool(tool_name)  # Alias
```

**Problem:**
- Unnecessary alias

**Solution:**
```python
# Proposed: Remove alias
describe_tool(tool_name)  # Keep only this
```

**Migration:**
- Deprecate `help_tool`

---

## Summary of Changes

### Tools to Remove (22)

| Tool | Replacement | Reason |
|------|-------------|--------|
| `get_historical_data` (old) | `get_historical_data` (new) | Merge with cached version |
| `yahoo_search` | `search_symbol(source='yahoo')` | Redundant search |
| `query_local_stocks` | `get_stock_screener` | Generic anti-pattern |
| `get_dividends` (old) | `get_dividends` (new) | Merge with history |
| `get_comprehensive_stock_info` | Composition of specific tools | Mega-tool anti-pattern |
| `query_local_fundamentals` | `get_fundamentals` | Redundant |
| `get_highest_rsi` | `get_technical_signals(signal_type='overbought')` | Redundant |
| `get_lowest_rsi` | `get_technical_signals(signal_type='oversold')` | Redundant |
| `get_fundamental_rankings` | `get_stock_screener(sort_by=metric)` | Redundant |
| `get_option_chain_snapshot` | `get_option_chain(detail='full')` | Merge |
| `get_options_data` | `get_option_chain` | Redundant |
| `get_option_greeks` | `get_option_screener(strike=X)` | Too specific |
| `get_wheel_put_annualized_return` | `get_wheel_put_candidates` | Already included |
| `compare_wheel_premiums` | `get_option_screener` | Redundant |
| `get_earnings_history` | `get_earnings_events(upcoming_only=False)` | Merge |
| `get_earnings_calendar` | `get_earnings_events(upcoming_only=True)` | Merge |
| `help_tool` | `describe_tool` | Alias |

### Tools to Rename (4)

| Old Name | New Name |
|----------|----------|
| `get_historical_data_cached` | `get_historical_data` |
| `get_dividend_history` | `get_dividends` |
| `get_company_info` | `get_company_profile` |
| `get_comprehensive_stock_info` | ❌ Removed |

### Tools to Enhance (6)

| Tool | Enhancement |
|------|-------------|
| `get_historical_data` | Add `source='auto\|ibkr\|local'` parameter |
| `get_dividends` | Add `upcoming=False` parameter |
| `search_symbol` | Add `source='auto\|local\|yahoo'` parameter |
| `get_option_chain` | Add `detail='summary\|full'` parameter |
| `get_option_screener` | Support single-contract queries (strike specified) |
| `get_earnings_events` | Add `upcoming_only=False` parameter |

---

## Migration Guide

### Phase 1: Add Deprecation Warnings (Week 1)

```python
@mcp.tool()
async def get_historical_data_old(symbol: str, duration='1 D', bar_size='1 hour'):
    """
    ⚠️ DEPRECATED: Use get_historical_data(symbol, period, interval) instead.
    This tool will be removed in v2.0.0.
    """
    logger.warning("get_historical_data_old is deprecated, use get_historical_data instead")
    # ... existing implementation
```

### Phase 2: Implement New Tools (Week 2)

```python
@mcp.tool()
async def get_historical_data(symbol: str, period='1y', interval='1d', source='auto'):
    """
    Get historical OHLCV data.
    
    Parameters:
        symbol: Stock ticker
        period: Time range ('1d', '1w', '1m', '3m', '1y', '5y')
        interval: Bar size ('1m', '5m', '1h', '1d')
        source: Data source ('auto', 'ibkr', 'local')
    """
    if source == 'auto':
        # Try local first, fallback to IBKR
        ...
    elif source == 'ibkr':
        # Force IBKR
        ...
    elif source == 'local':
        # Force local cache
        ...
```

### Phase 3: Update Documentation (Week 2)

- Update `README.md` with new tool catalog
- Update `ARCHITECTURE.md` with simplified diagram
- Update client examples

### Phase 4: Monitor Usage (Week 3-4)

```python
# Log deprecated tool usage
DEPRECATED_TOOL_USAGE = {
    "get_historical_data_old": 0,
    "yahoo_search": 0,
    # ...
}

# In tool decorator:
if tool_name in DEPRECATED_TOOL_USAGE:
    DEPRECATED_TOOL_USAGE[tool_name] += 1
    logger.warning(f"Deprecated tool {tool_name} called (count: {DEPRECATED_TOOL_USAGE[tool_name]})")
```

### Phase 5: Remove Deprecated Tools (v2.0.0)

- Remove deprecated tools
- Bump major version
- Update changelog

---

## Expected Benefits

### For LLMs
- **29% fewer tools** → Faster tool selection
- **Clearer intent** → Better tool matching
- **Consistent naming** → Easier to remember
- **Better docs** → More accurate usage

### For Developers
- **Less maintenance** → Fewer tools to update
- **Clearer architecture** → Easier to extend
- **Better testing** → Fewer edge cases
- **Simpler docs** → Easier onboarding

### For Users
- **Faster responses** → LLM picks right tool faster
- **More accurate** → Less confusion = better results
- **Better errors** → Clearer when tool doesn't exist

---

## Risk Assessment

### Low Risk
- Removing aliases (`help_tool`)
- Removing redundant tools with clear replacements
- Renaming tools (with deprecation period)

### Medium Risk
- Merging tools with different parameters
- Removing mega-tools (need to update LLM prompts)

### Mitigation
- 4-week deprecation period
- Clear migration docs
- Usage monitoring
- Rollback plan (keep old tools in v1.x branch)

---

## Approval Checklist

- [ ] Review proposed changes
- [ ] Validate replacement tools have same functionality
- [ ] Update LLM system prompts
- [ ] Create migration timeline
- [ ] Communicate to users
- [ ] Implement deprecation warnings
- [ ] Monitor usage metrics
- [ ] Execute removal in v2.0.0

---

## Next Steps

1. **Review this proposal** → Get feedback
2. **Create GitHub issue** → Track implementation
3. **Start Phase 1** → Add deprecation warnings
4. **Update docs** → Reflect new structure
5. **Monitor metrics** → Validate assumptions
6. **Release v2.0.0** → Clean architecture
