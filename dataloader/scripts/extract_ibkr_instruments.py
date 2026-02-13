#!/usr/bin/env python3
"""
Extract IBKR Instruments — stores raw IBKR contract details and option sec-def params.
This builds a pure IBKR metadata layer (independent from Yahoo transforms).
"""
import sys
import os
import json
import argparse
import asyncio
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal
from dataloader.models import Stock, RawIBKRContract, RawIBKROptionParam
from core.connection import ib_conn
from services.market_service import MarketService


def _safe_contract_payload(detail):
    contract = detail.contract
    return {
        "contract": {
            "conId": contract.conId,
            "symbol": contract.symbol,
            "secType": contract.secType,
            "exchange": contract.exchange,
            "primaryExchange": contract.primaryExchange,
            "currency": contract.currency,
            "localSymbol": contract.localSymbol,
            "tradingClass": contract.tradingClass,
        },
        "marketName": detail.marketName,
        "longName": detail.longName,
        "industry": detail.industry,
        "category": detail.category,
        "subcategory": detail.subcategory,
        "timeZoneId": detail.timeZoneId,
        "tradingHours": detail.tradingHours,
        "liquidHours": detail.liquidHours,
        "validExchanges": detail.validExchanges,
        "minTick": detail.minTick,
    }


def _safe_option_param_payload(param):
    return {
        "exchange": param.exchange,
        "underlyingConId": param.underlyingConId,
        "tradingClass": param.tradingClass,
        "multiplier": param.multiplier,
        "expirations": sorted(list(param.expirations)),
        "strikes": sorted(list(param.strikes)),
    }


async def main_async(test=False, market=None):
    session = SessionLocal()
    contracts_count = 0
    options_count = 0

    try:
        await ib_conn.connect()
        if not ib_conn.is_connected():
            raise RuntimeError("IB connection failed")

        query = session.query(Stock)
        if market == "B3":
            query = query.filter(Stock.exchange == "B3")
        elif market == "US":
            query = query.filter(Stock.exchange.in_(["NASDAQ", "NYSE"]))
        elif market == "OMX":
            query = query.filter(Stock.exchange == "OMX")

        if test:
            query = query.limit(2)

        stocks = query.all()
        print(f"[EXTRACT IBKR INSTRUMENTS] processing {len(stocks)} symbols")

        for stock in stocks:
            try:
                resolved = await MarketService._resolve_contract(stock.symbol, stock.exchange, stock.currency)
                if not resolved or resolved.conId <= 0:
                    print(f"  ⚠️ resolve failed for {stock.symbol}", file=sys.stderr)
                    continue

                details = await ib_conn.ib.reqContractDetailsAsync(resolved)
                for d in details or []:
                    payload = _safe_contract_payload(d)
                    session.add(
                        RawIBKRContract(
                            symbol=stock.symbol,
                            con_id=d.contract.conId,
                            exchange=d.contract.exchange,
                            primary_exchange=d.contract.primaryExchange,
                            currency=d.contract.currency,
                            sec_type=d.contract.secType,
                            data=json.dumps(payload),
                            fetched_at=datetime.utcnow(),
                        )
                    )
                    contracts_count += 1

                params = await ib_conn.ib.reqSecDefOptParamsAsync(
                    resolved.symbol, "", resolved.secType, resolved.conId
                )
                for p in params or []:
                    payload = _safe_option_param_payload(p)
                    session.add(
                        RawIBKROptionParam(
                            symbol=stock.symbol,
                            underlying_con_id=p.underlyingConId,
                            exchange=p.exchange,
                            trading_class=p.tradingClass,
                            multiplier=p.multiplier,
                            data=json.dumps(payload),
                            fetched_at=datetime.utcnow(),
                        )
                    )
                    options_count += 1

                session.commit()
            except Exception as e:
                session.rollback()
                print(f"  ⚠️ failed {stock.symbol}: {e}", file=sys.stderr)

        total = contracts_count + options_count
        print(f"[EXTRACT IBKR INSTRUMENTS] contracts={contracts_count} option_params={options_count}")
        print(f"RECORDS_AFFECTED={total}")
    finally:
        await ib_conn.shutdown()
        session.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run in test mode (2 symbols)")
    parser.add_argument("--market", choices=["B3", "US", "OMX"], help="Limit by market")
    args = parser.parse_args()
    asyncio.run(main_async(test=args.test, market=args.market))


if __name__ == "__main__":
    main()
