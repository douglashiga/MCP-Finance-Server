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
        Correct IB contract resolution:
        1. Normalize the symbol (strip Yahoo suffixes).
        2. reqMatchingSymbols → get primaryExchange + currency.
        3. Stock(symbol, "SMART", currency, primaryExchange=X).
        4. reqContractDetails → validate + get conId.
        5. Return Contract(conId=X, exchange="SMART") for market data.
        """
        symbol, exchange, currency = MarketService._normalize_symbol(symbol, exchange, currency)
        logger.info(f"[RESOLVE] Input: {symbol}, exchange={exchange}, currency={currency}")

        primary_exchange = exchange  # from normalization or user input

        # Step 1: reqMatchingSymbols to discover the correct primaryExchange
        if not primary_exchange:
            try:
                matches = await asyncio.wait_for(
                    ib_conn.ib.reqMatchingSymbolsAsync(symbol),
                    timeout=TIMEOUT_MARKET
                )
                if matches:
                    for cd in matches:
                        c = cd.contract
                        if c.secType == "STK" and c.symbol == symbol:
                            primary_exchange = c.primaryExchange
                            currency = c.currency
                            logger.info(f"[RESOLVE] reqMatchingSymbols → primary={primary_exchange}, currency={currency}")
                            break
                    # If exact match not found, use first STK
                    if not primary_exchange:
                        for cd in matches:
                            c = cd.contract
                            if c.secType == "STK":
                                primary_exchange = c.primaryExchange
                                currency = c.currency
                                symbol = c.symbol  # use IB's symbol
                                logger.info(f"[RESOLVE] reqMatchingSymbols (first STK) → {symbol} primary={primary_exchange}")
                                break
            except Exception as e:
                logger.warning(f"[RESOLVE] reqMatchingSymbols failed: {e}")

        # Step 2: Build contract with SMART + primaryExchange (correct pattern)
        contract = Stock(symbol, "SMART", currency)
        if primary_exchange:
            contract.primaryExchange = primary_exchange

        # Step 3: reqContractDetails to validate and get conId
        try:
            details = await asyncio.wait_for(
                ib_conn.ib.reqContractDetailsAsync(contract),
                timeout=TIMEOUT_MARKET
            )
            if details:
                # Use the first match
                validated = details[0].contract
                logger.info(f"[RESOLVE] reqContractDetails → conId={validated.conId}, "
                          f"symbol={validated.symbol}, primary={validated.primaryExchange}, "
                          f"currency={validated.currency}")

                # Build final contract using conId (most reliable for market data)
                final = Contract(conId=validated.conId, exchange="SMART")
                final.primaryExchange = validated.primaryExchange
                final.symbol = validated.symbol
                final.currency = validated.currency
                final.secType = "STK"

                # Qualify to ensure it's valid
                await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(final), timeout=5.0)
                if final.conId > 0:
                    logger.info(f"[RESOLVE] Final → conId={final.conId} on SMART (primary={final.primaryExchange})")
                    return final
        except Exception as e:
            logger.warning(f"[RESOLVE] reqContractDetails failed: {e}")

        # Fallback: direct qualification
        logger.info(f"[RESOLVE] Falling back to direct qualification")
        fallback = Stock(symbol, exchange or "SMART", currency)
        try:
            await asyncio.wait_for(ib_conn.ib.qualifyContractsAsync(fallback), timeout=5.0)
            if fallback.conId > 0:
                return fallback
        except Exception:
            pass

        return None

    @staticmethod
    async def _fetch_market_data(contract: Contract) -> dict:
        """
        Fetch market data with delayed data fallback.
        Uses the validated contract (with conId) for reliable data.
        """
        try:
            # Enable delayed data if real-time not subscribed (free)
            ib_conn.ib.reqMarketDataType(3)

            # Request market data
            ticker = ib_conn.ib.reqMktData(contract, genericTickList='', snapshot=False, regulatorySnapshot=False)

            # Wait for data to arrive (IB pushes asynchronously)
            await asyncio.sleep(3)

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
    def _to_yahoo_symbol(symbol: str, original_input: str, currency: str) -> str:
        """
        Convert IB symbol back to Yahoo format for fallback.
        If original input had suffix (e.g. PETR4.SA), use it.
        Otherwise, reverse-lookup from exchange_map by currency.
        US stocks stay as-is.
        """
        # If original already had Yahoo suffix, use it
        if '.' in original_input:
            return original_input

        # Reverse lookup: find suffix by currency
        CURRENCY_TO_SUFFIX = {
            "BRL": ".SA", "SEK": ".ST", "GBP": ".L", "EUR": ".DE",
            "CAD": ".TO", "HKD": ".HK", "JPY": ".T", "AUD": ".AX",
            "NOK": ".OL", "DKK": ".CO", "CHF": ".SW", "SGD": ".SI",
            "KRW": ".KS", "TWD": ".TW", "INR": ".NS", "MXN": ".MX",
            "ZAR": ".JO", "TRY": ".IS", "ARS": ".BA",
        }

        suffix = CURRENCY_TO_SUFFIX.get(currency, "")
        if suffix and currency != "USD":
            return symbol + suffix
        return symbol

    @staticmethod
    async def get_price(symbol: str, exchange: str = None, currency: str = 'USD') -> Dict[str, Any]:
        """
        Get real-time price from local database (populated by ELT pipeline).
        Falls back to Yahoo if not found in DB.
        """
        from dataloader.database import SessionLocal
        from dataloader.models import Stock, RealtimePrice
        
        logger.info(f"[PRICE] Requesting price for {symbol} from local DB")
        
        session = SessionLocal()
        try:
            # Query local database
            stock = session.query(Stock).filter_by(symbol=symbol).first()
            if not stock and '.' not in symbol:
                stock = session.query(Stock).filter(Stock.symbol.ilike(f"{symbol}.%")).first()
            
            if not stock:
                logger.info(f"[PRICE] Stock {symbol} not found in local DB")
                yahoo_symbol = symbol if "." in symbol else MarketService._to_yahoo_symbol(symbol, symbol, currency)
                return MarketService._yahoo_fallback(yahoo_symbol, "not_found_in_local_database")
            
            realtime = session.query(RealtimePrice).filter_by(stock_id=stock.id).first()
            
            if not realtime:
                logger.info(f"[PRICE] No realtime price data for {symbol}")
                return MarketService._yahoo_fallback(stock.symbol, "missing_local_realtime_snapshot")
            
            return {
                "success": True,
                "data": {
                    "symbol": stock.symbol,
                    "name": stock.name,
                    "exchange": stock.exchange,
                    "currency": realtime.currency or stock.currency,
                    "price": realtime.price,
                    "open": realtime.open,
                    "high": realtime.high,
                    "low": realtime.low,
                    "volume": realtime.volume,
                    "change": realtime.change,
                    "change_percent": realtime.change_percent,
                    "market_state": realtime.market_state,
                    "last_updated": realtime.last_updated.isoformat() if realtime.last_updated else None,
                    "source": "local_database",
                }
            }
        finally:
            session.close()

    @staticmethod
    def _yahoo_fallback(yahoo_symbol: str, source_note: str = "") -> Dict[str, Any]:
        """Fetch price from Yahoo Finance as fallback."""
        from services.yahoo_service import YahooService
        logger.info(f"[YAHOO_FALLBACK] Fetching {yahoo_symbol} ({source_note})")
        result = YahooService.get_price(yahoo_symbol)
        if result.get("success") and result.get("data"):
            result["data"]["fallback_reason"] = source_note
        return result

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
