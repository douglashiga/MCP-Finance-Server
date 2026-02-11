import asyncio
import logging
from typing import Dict, Any, List
from ib_insync import Stock, util
from core.connection import ib_conn, TIMEOUT_MARKET

logger = logging.getLogger(__name__)

class MarketService:
    @staticmethod
    async def get_price(symbol: str, exchange: str = None, currency: str = 'USD') -> Dict[str, Any]:
        logger.info(f"[PRICE] Requesting price for {symbol}")
        
        contract = Stock(symbol, exchange or "SMART", currency)
        
        async with ib_conn.market_semaphore:
            try:
                # Validation: Qualify the contract
                await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(contract), timeout=5.0)
            except Exception as e:
                return {"success": False, "error": f"Invalid Symbol/Contract: {symbol}. {e}"}

            if contract.conId == 0:
                return {"success": False, "error": f"Contract not found: {symbol} on {exchange or 'SMART'} ({currency}). Try a different exchange (e.g. BVMF for Brazil, LSE for London)."}

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
        # Check if generic ticks are available, if useless nan, maybe we need market data sub
        price = ticker.marketPrice()
        
        data = {
            "symbol": symbol,
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
                "conId": c.conId
            })
        return {"success": True, "data": results}
