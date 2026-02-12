import asyncio
import json
import logging
import os
import re
from typing import Dict, Any, Tuple, Optional
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
        """
        match = re.match(r'^(.+)\.([A-Z]{1,2})$', symbol.upper())

        if match:
            base = match.group(1)
            suffix = match.group(2)

            if suffix in EXCHANGE_MAP:
                info = EXCHANGE_MAP[suffix]
                clean = base.replace("-", "")
                logger.info(f"[NORMALIZE] {symbol} → {clean} on {info['exchange']} ({info['currency']})")
                return clean, exchange or info["exchange"], info["currency"]

        clean = symbol.replace("-", "")
        return clean, exchange, currency

    @staticmethod
    async def _resolve_contract(symbol: str, exchange: str = None, currency: str = 'USD') -> Optional[Contract]:
        """
        Robust contract resolution using reqMatchingSymbols.
        Always returns a contract with the correct primaryExchange (not SMART).

        Strategy:
        1. Normalize the symbol (strip Yahoo suffixes).
        2. Search IB with reqMatchingSymbols to find the real exchange.
        3. Qualify the contract with primaryExchange for proper market data.
        4. Fallback to direct SMART qualification if search fails.
        """
        symbol, exchange, currency = MarketService._normalize_symbol(symbol, exchange, currency)
        logger.info(f"[RESOLVE] Input: {symbol}, exchange={exchange}, currency={currency}")

        # Strategy 1: Use reqMatchingSymbols (best — gives us primaryExchange)
        try:
            matches = await asyncio.wait_for(
                ib_conn.ib.reqMatchingSymbolsAsync(symbol),
                timeout=TIMEOUT_MARKET
            )

            if matches:
                # Find best STK match, prefer matching currency if specified
                best = None
                for cd in matches:
                    c = cd.contract
                    if c.secType != "STK":
                        continue
                    # If exchange was specified from normalization, prefer that
                    if exchange and c.primaryExchange == exchange:
                        best = c
                        break
                    # If currency matches, good candidate
                    if c.currency == currency:
                        if not best:
                            best = c
                    # First STK match as fallback
                    if not best:
                        best = c

                if best:
                    # Use primaryExchange (NOT SMART) for market data
                    primary = best.primaryExchange or exchange or "SMART"
                    resolved = Stock(best.symbol, primary, best.currency)
                    try:
                        await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(resolved), timeout=5.0)
                        if resolved.conId > 0:
                            logger.info(f"[RESOLVE] {symbol} → {best.symbol} on {primary} ({best.currency}), conId={resolved.conId}")
                            return resolved
                    except Exception:
                        pass

                    # If primaryExchange qualification fails, try with SMART + primaryExchange
                    resolved2 = Stock(best.symbol, "SMART", best.currency)
                    resolved2.primaryExchange = primary
                    try:
                        await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(resolved2), timeout=5.0)
                        if resolved2.conId > 0:
                            logger.info(f"[RESOLVE] {symbol} → {best.symbol} SMART+primary={primary} ({best.currency}), conId={resolved2.conId}")
                            return resolved2
                    except Exception:
                        pass

        except asyncio.TimeoutError:
            logger.warning(f"[RESOLVE] reqMatchingSymbols timeout for {symbol}")
        except Exception as e:
            logger.warning(f"[RESOLVE] reqMatchingSymbols error for {symbol}: {e}")

        # Strategy 2: Direct qualification fallback
        logger.info(f"[RESOLVE] Falling back to direct qualification for {symbol}")
        contract = Stock(symbol, exchange or "SMART", currency)
        try:
            await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(contract), timeout=5.0)
            if contract.conId > 0:
                logger.info(f"[RESOLVE] {symbol} → conId={contract.conId} (direct fallback)")
                return contract
        except Exception:
            pass

        return None

    @staticmethod
    async def _fetch_market_data(contract: Contract) -> dict:
        """
        Fetch market data with delayed data fallback.
        Returns dict with price, bid, ask, volume, close.
        """
        try:
            # Enable delayed data if real-time not subscribed (free)
            ib_conn.ib.reqMarketDataType(3)

            ticker = ib_conn.ib.reqMktData(contract, genericTickList='', snapshot=False, regulatorySnapshot=False)

            # Wait for data to arrive
            await asyncio.sleep(2)

            # Cancel subscription
            ib_conn.ib.cancelMktData(contract)

        except Exception as e:
            logger.error(f"[MARKET_DATA] Error: {e}")
            return None

        if not ticker:
            return None

        price = ticker.marketPrice()

        return {
            "price": float(price) if price and not util.isNan(price) else None,
            "bid": float(ticker.bid) if ticker.bid and not util.isNan(ticker.bid) else None,
            "ask": float(ticker.ask) if ticker.ask and not util.isNan(ticker.ask) else None,
            "volume": int(ticker.volume) if ticker.volume and not util.isNan(ticker.volume) else None,
            "close": float(ticker.close) if ticker.close and not util.isNan(ticker.close) else None,
        }

    @staticmethod
    async def get_price(symbol: str, exchange: str = None, currency: str = 'USD') -> Dict[str, Any]:
        logger.info(f"[PRICE] Requesting price for {symbol}")

        async with ib_conn.market_semaphore:
            contract = await MarketService._resolve_contract(symbol, exchange, currency)

            if not contract or contract.conId == 0:
                return {"success": False, "error": f"Contract not found: {symbol}. Try search_symbol('{symbol}') to find the correct ticker."}

            logger.info(f"[PRICE] Using contract: {contract.symbol} exchange={contract.exchange} primary={contract.primaryExchange} currency={contract.currency}")

            # Fetch market data
            mkt = await MarketService._fetch_market_data(contract)

            if not mkt:
                return {"success": False, "error": f"No market data for {symbol}"}

            # If all values null and we used SMART, retry with primaryExchange
            all_null = all(v is None for v in mkt.values())
            if all_null and contract.primaryExchange and contract.exchange == "SMART":
                logger.info(f"[PRICE] All null with SMART, retrying with primaryExchange={contract.primaryExchange}")
                retry_contract = Stock(contract.symbol, contract.primaryExchange, contract.currency)
                try:
                    await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(retry_contract), timeout=5.0)
                    if retry_contract.conId > 0:
                        mkt2 = await MarketService._fetch_market_data(retry_contract)
                        if mkt2 and not all(v is None for v in mkt2.values()):
                            mkt = mkt2
                            contract = retry_contract
                except Exception:
                    pass

            data = {
                "symbol": contract.symbol,
                "exchange": contract.primaryExchange or contract.exchange,
                "currency": contract.currency,
                **mkt,
            }

            # Note if all still null
            if all(v is None for k, v in mkt.items()):
                data["note"] = "Market may be closed or no market data subscription for this exchange. Try during market hours."

            return {"success": True, "data": data}

    @staticmethod
    async def search_symbol(query: str) -> Dict[str, Any]:
        """Search for contracts and return detailed info including correct exchange."""
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
                "primaryExchange": c.primaryExchange,
                "currency": c.currency,
                "conId": c.conId,
            })
        return {"success": True, "data": results}
