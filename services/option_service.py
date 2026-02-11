import asyncio
import logging
import datetime
from typing import Dict, Any, List, Optional
from ib_insync import Stock, Option, util
from core.connection import ib_conn, TIMEOUT_MARKET

logger = logging.getLogger(__name__)

class OptionService:
    @staticmethod
    async def get_option_chain(symbol: str, exchange: str = 'SMART', sec_type: str = 'STK', currency: str = 'USD') -> Dict[str, Any]:
        """
        Get option chain parameters (strikes, expirations) for a refined underlying.
        Note: This returns the *structure* of the chain, not market data for every option.
        """
        logger.info(f"[OPTIONS] Requesting option chain for {symbol}")
        
        # 1. Qualify the underlying
        underlying = Stock(symbol, exchange, currency) if sec_type == 'STK' else None
        # TODO: Support other underlying types if needed
        
        if not underlying:
             return {"success": False, "error": "Only STK underlying supported for now"}

        async with ib_conn.market_semaphore:
            try:
                await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(underlying), timeout=2.0)
                
                # 2. Request Security Definition Option Parameters
                chains = await asyncio.wait_for(
                    ib_conn.ib.reqSecDefOptParamsAsync(
                        underlying.symbol, '', underlying.secType, underlying.conId
                    ),
                    timeout=TIMEOUT_MARKET
                )
            except asyncio.TimeoutError:
                return {"success": False, "error": "Timeout fetching option chain"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        if not chains:
             return {"success": False, "error": f"No option chain found for {symbol}"}

        # Organize data: usually multiple exchanges return similar chains. 
        # We'll merge them or return the SMART one if possible.
        
        # Simple aggregation
        all_expirations = set()
        all_strikes = set()
        
        for chain in chains:
            if chain.exchange == 'SMART':
                 all_expirations.update(chain.expirations)
                 all_strikes.update(chain.strikes)

        # Retrieve multiplier from first chain if available
        multiplier = chains[0].multiplier if chains else "100"

        return {
            "success": True, 
            "data": {
                "underlying": symbol,
                "multiplier": multiplier,
                "expirations": sorted(list(all_expirations)),
                "strikes": sorted(list(all_strikes))
            }
        }

    @staticmethod
    async def get_option_greeks(symbol: str, last_trade_date: str, strike: float, right: str, exchange: str = 'SMART') -> Dict[str, Any]:
        """
        Get Greeks and market data for a specific option contract.
        right: 'C' or 'P'
        last_trade_date: 'YYYYMMDD'
        """
        logger.info(f"[GREEKS] Requesting greeks for {symbol} {last_trade_date} {strike} {right}")
        
        contract = Option(symbol, last_trade_date, strike, right, exchange)
        
        async with ib_conn.market_semaphore:
            try:
                await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(contract), timeout=2.0)
                
                # Request ticker with greeks
                # we might need to enable generic ticks for greeks if not default? 
                # 100: Option Volume, 101: Option Open Interest, 106: Option Implied Vol?
                # Usually snapshot=True provides model greeks if calculator is active
                
                tickers = await asyncio.wait_for(
                    ib_conn.ib.reqTickersAsync(contract),
                    timeout=TIMEOUT_MARKET
                )
            except asyncio.TimeoutError:
                 return {"success": False, "error": "Timeout fetching option data"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        if not tickers:
            return {"success": False, "error": "No data found for option"}
            
        t = tickers[0]
        
        # Greeks are in t.modelGreeks (if available) or t.bidGreeks/t.askGreeks
        # We prefer modelGreeks
        greeks = t.modelGreeks
        
        data = {
            "conId": contract.conId,
            "symbol": contract.localSymbol,
            "bid": t.bid,
            "ask": t.ask,
            "last": t.last,
            "impliedVol": greeks.impliedVol if greeks else None,
            "delta": greeks.delta if greeks else None,
            "gamma": greeks.gamma if greeks else None,
            "vega": greeks.vega if greeks else None,
            "theta": greeks.theta if greeks else None,
            "undPrice": greeks.undPrice if greeks else None
        }
        
        return {"success": True, "data": data}
