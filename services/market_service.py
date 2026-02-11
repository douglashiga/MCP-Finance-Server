import asyncio
import json
import logging
import os
import re
from typing import Dict, Any, List, Tuple
from ib_insync import Stock, Contract, util
from core.connection import ib_conn, TIMEOUT_MARKET

logger = logging.getLogger(__name__)

# Load exchange map from JSON
_MAP_PATH = os.path.join(os.path.dirname(__file__), '..', 'exchange_map.json')
with open(_MAP_PATH) as f:
    EXCHANGE_MAP: Dict[str, dict] = json.load(f)


class MarketService:

    @staticmethod
    def _normalize_symbol(symbol: str, exchange: str = None, currency: str = 'USD') -> Tuple[str, str, str]:
        """
        Clean Yahoo/Bloomberg-style ticker → IB format using regex + JSON map.

        Examples:
            VOLV-B.ST  → VOLVB, SFB, SEK
            PETR4.SA   → PETR4, BOVESPA, BRL
            BMW.DE     → BMW, IBIS, EUR
            AAPL       → AAPL, None, USD  (unchanged)
        """
        # Regex: split on the LAST dot to get base and suffix
        match = re.match(r'^(.+)\.([A-Z]{1,2})$', symbol.upper())

        if match:
            base = match.group(1)
            suffix = match.group(2)

            if suffix in EXCHANGE_MAP:
                info = EXCHANGE_MAP[suffix]
                clean = base.replace("-", "")  # VOLV-B → VOLVB
                logger.info(f"[NORMALIZE] {symbol} → {clean} on {info['exchange']} ({info['currency']}) [{info['name']}]")
                return clean, exchange or info["exchange"], info["currency"]

        # No suffix matched: just clean dashes
        clean = symbol.replace("-", "")
        return clean, exchange, currency

    @staticmethod
    async def _resolve_contract(symbol: str, exchange: str = None, currency: str = 'USD') -> Contract:
        """
        Smart contract resolution:
        1. Normalize the symbol (strip suffixes, convert dashes).
        2. Try direct qualification (fast path).
        3. If fails, search IB for the symbol and use the best STK match.
        """
        symbol, exchange, currency = MarketService._normalize_symbol(symbol, exchange, currency)

        # Fast path: direct qualification
        contract = Stock(symbol, exchange or "SMART", currency)
        try:
            await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(contract), timeout=5.0)
            if contract.conId > 0:
                logger.info(f"[RESOLVE] {symbol} → conId={contract.conId} (direct)")
                return contract
        except Exception:
            pass

        # Slow path: search and pick best STK match
        logger.info(f"[RESOLVE] Direct failed for {symbol}, searching...")
        try:
            matches = await asyncio.wait_for(
                ib_conn.ib.reqMatchingSymbolsAsync(symbol),
                timeout=TIMEOUT_MARKET
            )
        except Exception:
            return None

        if not matches:
            return None

        # Find best STK match
        for cd in matches:
            c = cd.contract
            if c.secType == "STK":
                resolved = Stock(c.symbol, c.primaryExchange or "SMART", c.currency)
                try:
                    await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(resolved), timeout=5.0)
                    if resolved.conId > 0:
                        logger.info(f"[RESOLVE] {symbol} → {c.symbol} on {c.primaryExchange} ({c.currency}), conId={resolved.conId}")
                        return resolved
                except Exception:
                    continue

        return None

    @staticmethod
    async def get_price(symbol: str, exchange: str = None, currency: str = 'USD') -> Dict[str, Any]:
        logger.info(f"[PRICE] Requesting price for {symbol}")

        async with ib_conn.market_semaphore:
            contract = await MarketService._resolve_contract(symbol, exchange, currency)

            if not contract or contract.conId == 0:
                return {"success": False, "error": f"Contract not found: {symbol}. Try search_symbol('{symbol}') to find the correct ticker."}

            try:
                # Request market data (streams asynchronously)
                ticker = ib_conn.ib.reqMktData(contract, genericTickList='', snapshot=False, regulatorySnapshot=False)

                # Wait for data to arrive (IB pushes it asynchronously)
                await asyncio.sleep(2)

                # Cancel subscription (we only need a snapshot)
                ib_conn.ib.cancelMktData(contract)

            except Exception as e:
                logger.error(f"[PRICE] Error: {e}")
                return {"success": False, "error": str(e)}

        if not ticker:
            return {"success": False, "error": f"No market data found for {symbol}"}

        price = ticker.marketPrice()

        data = {
            "symbol": contract.symbol,
            "exchange": contract.exchange,
            "currency": contract.currency,
            "price": float(price) if price and not util.isNan(price) else None,
            "bid": float(ticker.bid) if ticker.bid and not util.isNan(ticker.bid) else None,
            "ask": float(ticker.ask) if ticker.ask and not util.isNan(ticker.ask) else None,
            "volume": int(ticker.volume) if ticker.volume and not util.isNan(ticker.volume) else None,
            "close": float(ticker.close) if ticker.close and not util.isNan(ticker.close) else None
        }
        return {"success": True, "data": data}

    @staticmethod
    async def search_symbol(query: str) -> Dict[str, Any]:
        logger.info(f"[SEARCH] Query: {query}")
        try:
            contracts = await asyncio.wait_for(
                ib_conn.ib.reqMatchingSymbolsAsync(query),
                timeout=TIMEOUT_MARKET
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timeout searching symbol"}

        if not contracts:
            return {"success": True, "data": [], "message": f"No symbols found matching '{query}'"}

        results = []
        for cd in contracts:
            c = cd.contract
            results.append({
                "symbol": c.symbol,
                "secType": c.secType,
                "exchange": c.primaryExchange,
                "currency": c.currency,
                "conId": c.conId
            })
        return {"success": True, "data": results}
