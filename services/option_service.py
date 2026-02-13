import asyncio
import logging
import datetime
from typing import Dict, Any, List, Optional
from ib_insync import Stock, Option, util
from core.connection import ib_conn, TIMEOUT_MARKET
from services.market_service import MarketService

logger = logging.getLogger(__name__)

class OptionService:
    @staticmethod
    def _to_float(value):
        if value is None:
            return None
        try:
            if util.isNan(value):
                return None
        except Exception:
            pass
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _pick_greeks(ticker):
        return ticker.modelGreeks or ticker.bidGreeks or ticker.askGreeks or ticker.lastGreeks

    @staticmethod
    async def get_option_chain(symbol: str, exchange: str = 'SMART', sec_type: str = 'STK', currency: str = 'USD') -> Dict[str, Any]:
        """
        Get option chain parameters (strikes, expirations) for a refined underlying.
        Note: This returns the *structure* of the chain, not market data for every option.
        """
        logger.info(f"[OPTIONS] Requesting option chain for {symbol}")
        
        # 1. Resolve underlying contract with robust mapping/qualification
        underlying = await MarketService._resolve_contract(symbol, exchange, currency) if sec_type == 'STK' else None
        # TODO: Support other underlying types if needed
        
        if not underlying:
             return {"success": False, "error": "Only STK underlying supported for now"}

        async with ib_conn.market_semaphore:
            try:
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

        # Prefer SMART chain, fallback to all exchanges if SMART is unavailable.
        all_expirations = set()
        all_strikes = set()
        preferred = [c for c in chains if c.exchange == 'SMART']
        selected_chains = preferred if preferred else chains

        for chain in selected_chains:
            all_expirations.update(chain.expirations)
            all_strikes.update(chain.strikes)

        if not all_expirations or not all_strikes:
            return {"success": False, "error": f"Option chain unavailable for {symbol}"}

        # Retrieve multiplier from first chain if available
        multiplier = selected_chains[0].multiplier if selected_chains else "100"

        return {
            "success": True, 
            "data": {
                "underlying": symbol,
                "underlying_con_id": underlying.conId,
                "multiplier": multiplier,
                "expirations": sorted(list(all_expirations)),
                "strikes": sorted(list(all_strikes)),
                "exchanges": sorted(list({c.exchange for c in selected_chains if c.exchange})),
                "as_of_datetime": datetime.datetime.utcnow().isoformat(),
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
        
        normalized_right = (right or "").upper()
        if normalized_right in {"CALL", "C"}:
            normalized_right = "C"
        elif normalized_right in {"PUT", "P"}:
            normalized_right = "P"
        else:
            return {"success": False, "error": "Invalid right. Use C/P or CALL/PUT"}

        clean_symbol, _, _ = MarketService._normalize_symbol(symbol, exchange, "USD")
        contract = Option(clean_symbol, last_trade_date, strike, normalized_right, exchange)
        
        async with ib_conn.market_semaphore:
            try:
                await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(contract), timeout=2.0)
                
                ib_conn.ib.reqMarketDataType(3)
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
        
        greeks = OptionService._pick_greeks(t)
        
        data = {
            "conId": contract.conId,
            "symbol": contract.localSymbol,
            "bid": OptionService._to_float(t.bid),
            "ask": OptionService._to_float(t.ask),
            "last": OptionService._to_float(t.last),
            "impliedVol": OptionService._to_float(greeks.impliedVol) if greeks else None,
            "delta": OptionService._to_float(greeks.delta) if greeks else None,
            "gamma": OptionService._to_float(greeks.gamma) if greeks else None,
            "vega": OptionService._to_float(greeks.vega) if greeks else None,
            "theta": OptionService._to_float(greeks.theta) if greeks else None,
            "undPrice": OptionService._to_float(greeks.undPrice) if greeks else None,
            "as_of_datetime": datetime.datetime.utcnow().isoformat(),
        }
        
        return {"success": True, "data": data}
