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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from ib_insync import Option, Stock as IBStock
from dataloader.database import SessionLocal
from dataloader.models import Stock, OptionMetric
from core.connection import ib_conn
from services.market_service import MarketService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("extract_option_metrics")

async def get_chains_for_stock(ib, stock_record, max_weeks=5):
    """Fetch option chains and greeks for a single stock."""
    try:
        # Resolve underlying contract
        underlying = IBStock(
            symbol=stock_record.symbol.split('.')[0] if '.' in stock_record.symbol else stock_record.symbol,
            exchange=stock_record.exchange,
            currency=stock_record.currency
        )
        qualified = await ib.qualifyContractsAsync(underlying)
        if not qualified:
            logger.warning(f"Could not qualify underlying {stock_record.symbol}")
            return []
        
        underlying = qualified[0]
        
        # Request option parameters
        chains = await ib.reqSecDefOptParamsAsync(
            underlying.symbol, '', underlying.secType, underlying.conId
        )
        
        if not chains:
            logger.warning(f"No option chains found for {stock_record.symbol}")
            return []
        
        # Filter expiries within 5 weeks
        today = date.today()
        limit_date = today + timedelta(weeks=max_weeks)
        
        target_expiries = []
        for chain in chains:
            for exp in chain.expirations:
                # IB expiries are YYYYMMDD
                exp_date = datetime.strptime(exp, '%Y%m%d').date()
                if today <= exp_date <= limit_date:
                    target_expiries.append((exp, chain))
        
        if not target_expiries:
            logger.info(f"No expiries within {max_weeks} weeks for {stock_record.symbol}")
            return []
        
        # Build option contracts
        option_contracts = []
        for exp, chain in target_expiries:
            # Limit strikes to around current price for efficiency if needed, 
            # but for now we'll take what IB gives or filter a bit
            # For simplicity, let's take all strikes in the chain for these expiries
            for strike in chain.strikes:
                for right in ['C', 'P']:
                    option_contracts.append(Option(
                        symbol=underlying.symbol,
                        lastTradeDateOrContractMonth=exp,
                        strike=strike,
                        right=right,
                        exchange=chain.exchange,
                        currency=underlying.currency
                    ))
        
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
        tickers = ib.reqTickers(*qualified_options)
        
        # Wait a bit for tickers to populate (Greeks take a moment)
        await asyncio.sleep(2)
        
        results = []
        for t in tickers:
            greeks = t.modelGreeks
            results.append({
                "option_symbol": t.contract.localSymbol,
                "stock_id": stock_record.id,
                "strike": t.contract.strike,
                "right": "CALL" if t.contract.right == 'C' else "PUT",
                "expiry": datetime.strptime(t.contract.lastTradeDateOrContractMonth, '%Y%m%d').date(),
                "bid": t.bid if t.bid != -1 else None,
                "ask": t.ask if t.ask != -1 else None,
                "last": t.last if t.last != -1 else None,
                "volume": t.volume if t.volume != -1 else None,
                "open_interest": t.openInterest if t.openInterest != -1 else None,
                "delta": greeks.delta if greeks else None,
                "gamma": greeks.gamma if greeks else None,
                "theta": greeks.theta if greeks else None,
                "vega": greeks.vega if greeks else None,
                "iv": greeks.impliedVol if greeks else None,
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
