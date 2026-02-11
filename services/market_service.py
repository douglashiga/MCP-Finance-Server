import asyncio
import logging
from typing import Dict, Any, List
from ib_insync import Stock, Contract, util
from core.connection import ib_conn, TIMEOUT_MARKET

logger = logging.getLogger(__name__)


class MarketService:

    @staticmethod
    async def _resolve_contract(symbol: str, exchange: str = None, currency: str = 'USD') -> Contract:
        """
        Smart contract resolution:
        1. Try direct qualification (fast path).
        2. If fails, search IB for the symbol and use the best STK match.
        """
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
                tickers = await asyncio.wait_for(
                    ib_conn.ib.reqTickersAsync(contract),
                    timeout=TIMEOUT_MARKET
                )
            except asyncio.TimeoutError:
                logger.error(f"[PRICE] Timeout fetching price for {symbol}")
                return {"success": False, "error": "Timeout fetching market data"}
            except Exception as e:
                logger.error(f"[PRICE] Error: {e}")
                return {"success": False, "error": str(e)}

        if not tickers:
            return {"success": False, "error": f"No market data found for {symbol}"}

        ticker = tickers[0]
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
