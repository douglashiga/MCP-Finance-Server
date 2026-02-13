#!/usr/bin/env python3
"""
Extract Option Metrics — Fetches option chains, Greeks, and bid/ask from IB Gateway.
Filters expiries within 5 weeks of current date.
Divided by market/exchange to manage load and rate limits.
"""
import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime, date, timedelta
from typing import List
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ib_insync import Option
from dataloader.database import SessionLocal
from dataloader.models import Stock, OptionMetric
from core.connection import ib_conn
from services.market_service import MarketService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("extract_option_metrics")


def _to_float(value):
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or math.isinf(val) or val == -1:
        return None
    return val


def _to_int(value):
    val = _to_float(value)
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _pick_greeks(ticker):
    return ticker.modelGreeks or ticker.bidGreeks or ticker.askGreeks or ticker.lastGreeks

def _select_expiries(expiries: List[str], today: date, limit_date: date, max_expiries: int = 3) -> List[str]:
    candidates = []
    for exp in expiries:
        try:
            exp_date = datetime.strptime(exp, '%Y%m%d').date()
        except Exception:
            continue
        if today <= exp_date <= limit_date:
            candidates.append((exp_date, exp))
    candidates.sort(key=lambda x: x[0])
    return [exp for _, exp in candidates[:max_expiries]]


def _select_strikes(strikes: List[float], ref_price: float = None, max_strikes: int = 15) -> List[float]:
    if not strikes:
        return []
    unique = sorted(set(float(s) for s in strikes))
    if ref_price is None:
        return unique[:max_strikes]
    ranked = sorted(unique, key=lambda s: abs(s - ref_price))
    return sorted(ranked[:max_strikes])


async def get_chains_for_stock(ib, stock_record, max_weeks=5, max_expiries=3, max_strikes=15):
    """Fetch option chains and greeks for a single stock."""
    try:
        # Resolve underlying contract with IB-aware normalization/exchange mapping
        underlying = await MarketService._resolve_contract(
            symbol=stock_record.symbol,
            exchange=None,  # let resolver map local exchange labels to IB primary exchange
            currency=stock_record.currency,
        )
        if not underlying:
            logger.warning(f"Could not qualify underlying {stock_record.symbol}")
            return []

        # Request option parameters
        chains = await ib.reqSecDefOptParamsAsync(
            underlying.symbol, '', underlying.secType, underlying.conId
        )
        
        if not chains:
            logger.warning(f"No option chains found for {stock_record.symbol}")
            return []
        
        # Underlying reference price to reduce strike universe.
        mkt = await MarketService._fetch_market_data(underlying)
        ref_price = (mkt or {}).get("price") or (mkt or {}).get("close")

        # Filter expiries within max_weeks and limit chain size
        today = date.today()
        limit_date = today + timedelta(weeks=max_weeks)
        
        target_expiries = []
        for chain in chains:
            # Prefer SMART/global chains when available for better liquidity coverage.
            if chain.exchange not in {"SMART", underlying.exchange, underlying.primaryExchange}:
                continue
            selected_exp = _select_expiries(list(chain.expirations), today, limit_date, max_expiries=max_expiries)
            for exp in selected_exp:
                target_expiries.append((exp, chain))
        
        if not target_expiries:
            logger.info(f"No expiries within {max_weeks} weeks for {stock_record.symbol}")
            return []
        
        # Build option contracts
        option_contracts = []
        seen = set()
        for exp, chain in target_expiries:
            # Limit strikes to around current price for efficiency if needed, 
            # but for now we'll take what IB gives or filter a bit
            # For simplicity, let's take all strikes in the chain for these expiries
            for strike in _select_strikes(list(chain.strikes), ref_price=ref_price, max_strikes=max_strikes):
                for right in ['C', 'P']:
                    key = (underlying.symbol, exp, float(strike), right, chain.exchange)
                    if key in seen:
                        continue
                    seen.add(key)
                    option_contracts.append(Option(
                        symbol=underlying.symbol,
                        lastTradeDateOrContractMonth=exp,
                        strike=strike,
                        right=right,
                        exchange=chain.exchange,
                        currency=underlying.currency
                    ))
        
        if len(option_contracts) > 600:
            option_contracts = option_contracts[:600]

        # Qualify all options (batching helps)
        logger.info(f"Qualifying {len(option_contracts)} options for {stock_record.symbol}...")
        # Qualify in chunks to avoid overloading
        chunk_size = 100
        qualified_options = []
        for i in range(0, len(option_contracts), chunk_size):
            chunk = option_contracts[i:i+chunk_size]
            qualified_options.extend(await ib.qualifyContractsAsync(*chunk))
            
        if not qualified_options:
            return []
            
        # Request market data (Greeks + Bid/Ask)
        logger.info(f"Requesting tickers for {len(qualified_options)} options...")
        # reqTickers is efficient for batching
        tickers = []
        ticker_chunk_size = 100
        for i in range(0, len(qualified_options), ticker_chunk_size):
            chunk = qualified_options[i:i+ticker_chunk_size]
            batch = await ib.reqTickersAsync(*chunk)
            tickers.extend(batch)
            await asyncio.sleep(0.2)
        
        results = []
        for t in tickers:
            greeks = _pick_greeks(t)
            expiry_raw = t.contract.lastTradeDateOrContractMonth or ""
            if len(expiry_raw) >= 8:
                expiry_date = datetime.strptime(expiry_raw[:8], '%Y%m%d').date()
            else:
                continue

            results.append({
                "option_symbol": t.contract.localSymbol,
                "stock_id": stock_record.id,
                "strike": _to_float(t.contract.strike),
                "right": "CALL" if t.contract.right == 'C' else "PUT",
                "expiry": expiry_date,
                "bid": _to_float(t.bid),
                "ask": _to_float(t.ask),
                "last": _to_float(t.last),
                "volume": _to_int(t.volume),
                "open_interest": _to_int(t.openInterest),
                "delta": _to_float(greeks.delta) if greeks else None,
                "gamma": _to_float(greeks.gamma) if greeks else None,
                "theta": _to_float(greeks.theta) if greeks else None,
                "vega": _to_float(greeks.vega) if greeks else None,
                "iv": _to_float(greeks.impliedVol) if greeks else None,
            })
            
        return results
        
    except Exception as e:
        logger.error(f"Error processing stock {stock_record.symbol}: {e}")
        return []

async def main_async(market=None, test=False):
    session = SessionLocal()
    count = 0
    
    try:
        await ib_conn.connect()
        ib = ib_conn.ib
        
        # Query stocks by market
        query = session.query(Stock)
        if market == "B3":
            query = query.filter(Stock.exchange == "B3")
        elif market == "US":
            query = query.filter(Stock.exchange.in_(["NASDAQ", "NYSE"]))
        elif market == "OMX":
             query = query.filter(Stock.exchange == "OMX")
            
        if test:
            query = query.limit(1)
            
        stocks = query.all()
        logger.info(f"Processing {len(stocks)} stocks for market {market}...")
        
        for stock in stocks:
            logger.info(f"Fetching options for {stock.symbol}...")
            metrics_list = await get_chains_for_stock(ib, stock)
            
            if not metrics_list:
                continue
                
            for m in metrics_list:
                # Upsert
                existing = session.query(OptionMetric).filter_by(
                    option_symbol=m["option_symbol"]
                ).first()
                
                if existing:
                    for key, value in m.items():
                        setattr(existing, key, value)
                else:
                    session.add(OptionMetric(**m))
            
            session.commit()
            count += len(metrics_list)
            logger.info(f"Updated {len(metrics_list)} options for {stock.symbol}")
            
        print(f"[EXTRACT OPTION METRICS] Market: {market} | Total options updated: {count}")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Global error: {e}")
        sys.exit(1)
    finally:
        await ib_conn.shutdown()
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", choices=["B3", "US", "OMX"], required=True)
    parser.add_argument("--test", action="store_true", help="Run in test mode (1 symbol)")
    args = parser.parse_args()
    
    asyncio.run(main_async(market=args.market, test=args.test))
