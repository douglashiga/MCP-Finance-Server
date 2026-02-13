import asyncio
import logging
import time
from typing import Dict, Any
from core.connection import ib_conn, TIMEOUT_HISTORY
from services.market_service import MarketService

logger = logging.getLogger(__name__)

# Simple in-memory cache: {symbol_key: (data, timestamp)}
_history_cache = {}
CACHE_TTL = 30  # seconds

class HistoryService:
    @staticmethod
    async def get_historical_data(symbol: str, duration: str = "1 D", bar_size: str = "1 hour",
                                  exchange: str = None, currency: str = "USD") -> Dict[str, Any]:
        # Validation
        if not symbol.replace('.', '').replace('-', '').isalnum():
             return {"success": False, "error": f"Invalid symbol: {symbol}"}

        valid_durations = {"1 D", "1 W", "1 M", "3 M", "1 Y"}
        valid_bar_sizes = {"1 min", "5 mins", "15 mins", "1 hour", "1 day"}
        if duration not in valid_durations:
            return {"success": False, "error": f"Invalid duration '{duration}'"}
        if bar_size not in valid_bar_sizes:
            return {"success": False, "error": f"Invalid bar_size '{bar_size}'"}

        contract = await MarketService._resolve_contract(symbol, exchange, currency)
        if not contract:
            return {"success": False, "error": f"Could not resolve contract for symbol '{symbol}'"}
        
        # Cache Key
        cache_key = f"{symbol}_{exchange}_{currency}_{duration}_{bar_size}"
        
        # Check Cache
        if cache_key in _history_cache:
            data, timestamp = _history_cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"[HISTORY] Returning cached data for {symbol}")
                return {"success": True, "data": data}

        logger.info(f"[HISTORY] Requesting history for {symbol} ({duration}, {bar_size})")

        # Concurrency Control
        async with ib_conn.market_semaphore:
            try:
                # Qualify contract (optional for history but good safe practice if strict)
                # But reqHistoricalData usually handles it.
                
                bars = await asyncio.wait_for(
                    ib_conn.ib.reqHistoricalDataAsync(
                        contract,
                        endDateTime='',
                        durationStr=duration,
                        barSizeSetting=bar_size,
                        whatToShow='TRADES',
                        useRTH=True
                    ),
                    timeout=TIMEOUT_HISTORY
                )
            except asyncio.TimeoutError:
                 return {"success": False, "error": "Timeout fetching historical data"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        if not bars:
            return {"success": False, "error": f"No historical data found for {symbol}"}
            
        data = []
        for bar in bars:
            data.append({
                "date": str(bar.date),
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "volume": bar.volume
            })
            
        # Update Cache
        _history_cache[cache_key] = (data, time.time())
            
        return {"success": True, "data": data}
