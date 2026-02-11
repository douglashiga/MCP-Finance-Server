import asyncio
import logging
from typing import Dict, Any, List
from ib_insync import util
from core.connection import ib_conn, TIMEOUT_ACCOUNT

logger = logging.getLogger(__name__)

class AccountService:
    @staticmethod
    async def get_summary() -> Dict[str, Any]:
        logger.info(f"[ACCOUNT] Requesting account summary")
        try:
            summary = await asyncio.wait_for(
                ib_conn.ib.accountSummaryAsync(), 
                timeout=TIMEOUT_ACCOUNT
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timeout fetching account summary"}
            
        key_tags = [
            'NetLiquidation', 'TotalCashValue', 'BuyingPower', 'GrossPositionValue',
            'MaintMarginReq', 'InitMarginReq', 'AvailableFunds', 'ExcessLiquidity', 'Cushion'
        ]
        
        data = {}
        for item in summary:
            if item.tag in key_tags:
                data[item.tag] = {"value": item.value, "currency": item.currency}
                
        return {"success": True, "data": data}

    @staticmethod
    async def get_positions() -> Dict[str, Any]:
        try:
            positions = await asyncio.wait_for(
                ib_conn.ib.reqPositionsAsync(), 
                timeout=TIMEOUT_ACCOUNT
            )
        except asyncio.TimeoutError:
            return {"success": False, "error": "Timeout fetching positions"}
            
        data = []
        for p in positions:
            data.append({
                "symbol": p.contract.symbol,
                "secType": p.contract.secType,
                "position": p.position,
                "avgCost": p.avgCost
            })
        return {"success": True, "data": data}
