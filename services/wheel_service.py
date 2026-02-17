"""
Wheel Service — option analytics focused on cash-secured puts and covered calls.
Designed for LLM calls with stable response contracts and explicit assumptions.
"""
import logging
import math
from datetime import date, datetime, timedelta
from statistics import median
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from dataloader.database import SessionLocal
from dataloader.models import (
    HistoricalPrice,
    OptionIVSnapshot,
    OptionMetric,
    RealtimePrice,
    Stock,
)

logger = logging.getLogger(__name__)

DEFAULT_MARKET = "sweden"
DEFAULT_LIMIT = 5
MAX_LIMIT = 50
DEFAULT_CONTRACT_MULTIPLIER = 100
DEFAULT_DELTA_MIN = 0.25
DEFAULT_DELTA_MAX = 0.35
DEFAULT_DTE_MIN = 4
DEFAULT_DTE_MAX = 10

MARKET_MAP = {
    "brazil": ["B3"],
    "b3": ["B3"],
    "sweden": ["OMX"],
    "omx": ["OMX"],
    "usa": ["NASDAQ", "NYSE"],
    "us": ["NASDAQ", "NYSE"],
    "nasdaq": ["NASDAQ"],
    "nyse": ["NYSE"],
    "all": ["B3", "OMX", "NASDAQ", "NYSE"],
}

SYMBOL_ALIASES = {
    "NORDEA": "NDA-SE.ST",
    "NDA": "NDA-SE.ST",
    "SEB": "SEB-A.ST",
    "SWEDBANK": "SWED-A.ST",
    "TELIA": "TELIA.ST",
    "VOLVO": "VOLV-B.ST",
    "VOLV": "VOLV-B.ST",
}


def _resolve_market(market: str) -> List[str]:
    return MARKET_MAP.get((market or DEFAULT_MARKET).lower(), [market.upper()])


def _normalize_limit(limit: int, default: int = DEFAULT_LIMIT) -> int:
    if limit is None:
        return default
    return max(1, min(int(limit), MAX_LIMIT))


def _to_float(value):
    if value is None:
        return None
    try:
        val = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(val) or math.isinf(val):
        return None
    return val


def _option_premium(metric: OptionMetric):
    bid = _to_float(metric.bid)
    ask = _to_float(metric.ask)
    last = _to_float(metric.last)
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if last is not None and last > 0:
        return last
    if bid is not None and bid > 0:
        return bid
    if ask is not None and ask > 0:
        return ask
    return None


def _annualized_return_pct(premium: float, strike: float, dte: int):
    if premium is None or strike is None or strike <= 0 or dte <= 0:
        return None
    period_return = (premium / strike) * 100.0
    return period_return * (365.0 / float(dte))


def _get_spot_price(session, stock_id: int):
    rt = session.query(RealtimePrice).filter(RealtimePrice.stock_id == stock_id).first()
    if rt and _to_float(rt.price) and float(rt.price) > 0:
        return float(rt.price), "realtime_prices"

    hp = session.query(HistoricalPrice).filter(
        HistoricalPrice.stock_id == stock_id,
        HistoricalPrice.close.isnot(None),
        HistoricalPrice.close > 0,
    ).order_by(HistoricalPrice.date.desc()).first()

    if hp and _to_float(hp.close):
        return float(hp.close), "historical_prices"

    return None, None


def _resolve_stock(session, symbol: str, market: str = DEFAULT_MARKET):
    if not symbol:
        return None

    exchanges = _resolve_market(market)
    query = session.query(Stock).filter(Stock.exchange.in_(exchanges))

    raw = symbol.strip()
    upper = raw.upper()
    alias = SYMBOL_ALIASES.get(upper)

    if alias:
        aliased = query.filter(func.upper(Stock.symbol) == alias.upper()).first()
        if aliased:
            return aliased

    exact = query.filter(func.upper(Stock.symbol) == upper).first()
    if exact:
        return exact

    if "." not in upper:
        suffix = query.filter(func.upper(Stock.symbol).like(f"{upper}.%"))\
            .order_by(Stock.symbol.asc()).first()
        if suffix:
            return suffix

    by_name = query.filter(func.upper(Stock.name).like(f"%{upper}%")).order_by(Stock.symbol.asc()).first()
    return by_name


def _normalize_right(right: str) -> str:
    r = (right or "").upper()
    if r in {"P", "PUT"}:
        return "PUT"
    if r in {"C", "CALL"}:
        return "CALL"
    return ""


def _list_candidates(
    session,
    stock_id: int,
    right: str,
    dte_min: int,
    dte_max: int,
    delta_min: Optional[float] = None,
    delta_max: Optional[float] = None,
    require_liquidity: bool = True,
):
    today = date.today()
    right_norm = _normalize_right(right)
    if not right_norm:
        return []

    rows = session.query(OptionMetric).filter(
        OptionMetric.stock_id == stock_id,
        OptionMetric.right == right_norm,
        OptionMetric.expiry >= today + timedelta(days=max(0, int(dte_min))),
        OptionMetric.expiry <= today + timedelta(days=max(0, int(dte_max))),
    ).order_by(OptionMetric.expiry.asc(), OptionMetric.strike.asc()).all()

    results = []
    for metric in rows:
        strike = _to_float(metric.strike)
        if strike is None or strike <= 0:
            continue

        premium = _option_premium(metric)
        if premium is None:
            continue

        bid = _to_float(metric.bid)
        ask = _to_float(metric.ask)
        if require_liquidity and not (bid is not None and ask is not None and bid > 0 and ask > 0):
            continue

        dte = (metric.expiry - today).days if metric.expiry else None
        if dte is None or dte <= 0:
            continue

        delta_raw = _to_float(metric.delta)
        delta_abs = abs(delta_raw) if delta_raw is not None else None

        if delta_min is not None and delta_abs is not None and delta_abs < float(delta_min):
            continue
        if delta_max is not None and delta_abs is not None and delta_abs > float(delta_max):
            continue

        results.append({
            "option_symbol": metric.option_symbol,
            "expiry": metric.expiry,
            "dte": dte,
            "strike": strike,
            "right": right_norm,
            "bid": bid,
            "ask": ask,
            "last": _to_float(metric.last),
            "premium": premium,
            "delta": delta_raw,
            "delta_abs": delta_abs,
            "iv": _to_float(metric.iv),
            "open_interest": metric.open_interest,
            "volume": metric.volume,
            "updated_at": metric.updated_at,
        })

    return results


def _select_atm_option(candidates: List[Dict[str, Any]], spot: float, target_dte: int):
    if not candidates:
        return None
    target_dte = max(1, int(target_dte))
    return sorted(
        candidates,
        key=lambda x: (
            abs(int(x.get("dte", 9999)) - target_dte),
            abs(float(x.get("strike", 0.0)) - float(spot or 0.0)),
        ),
    )[0]


class WheelService:
    @staticmethod
    def select_put_for_wheel(
        symbol: str,
        market: str = DEFAULT_MARKET,
        delta_min: float = DEFAULT_DELTA_MIN,
        delta_max: float = DEFAULT_DELTA_MAX,
        dte_min: int = DEFAULT_DTE_MIN,
        dte_max: int = DEFAULT_DTE_MAX,
        limit: int = DEFAULT_LIMIT,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
        require_liquidity: bool = True,
    ):
        session = SessionLocal()
        try:
            limit = _normalize_limit(limit)
            stock = _resolve_stock(session, symbol, market=market)
            if not stock:
                return {
                    "success": True,
                    "data": [],
                    "count": 0,
                    "criteria": {
                        "symbol": symbol,
                        "market": market,
                        "delta_min": delta_min,
                        "delta_max": delta_max,
                        "dte_min": dte_min,
                        "dte_max": dte_max,
                        "limit": limit,
                        "require_liquidity": require_liquidity,
                    },
                    "empty_reason": "stock_not_found_for_market",
                }

            spot, spot_source = _get_spot_price(session, stock.id)
            cands = _list_candidates(
                session,
                stock.id,
                right="PUT",
                dte_min=dte_min,
                dte_max=dte_max,
                delta_min=delta_min,
                delta_max=delta_max,
                require_liquidity=require_liquidity,
            )

            if not cands:
                return {
                    "success": True,
                    "data": [],
                    "count": 0,
                    "symbol": stock.symbol,
                    "spot": spot,
                    "spot_source": spot_source,
                    "criteria": {
                        "symbol": symbol,
                        "market": market,
                        "delta_min": delta_min,
                        "delta_max": delta_max,
                        "dte_min": dte_min,
                        "dte_max": dte_max,
                        "limit": limit,
                        "require_liquidity": require_liquidity,
                    },
                    "empty_reason": "no_put_candidates_for_criteria",
                }

            target_delta = (float(delta_min) + float(delta_max)) / 2.0
            ranked = sorted(
                cands,
                key=lambda x: (
                    abs((x.get("delta_abs") or target_delta) - target_delta),
                    abs(x.get("dte", 0) - int((dte_min + dte_max) / 2)),
                ),
            )[:limit]

            data = []
            for row in ranked:
                premium = row["premium"]
                strike = row["strike"]
                dte = row["dte"]
                capital = strike * int(contract_multiplier)
                premium_value = premium * int(contract_multiplier)
                premium_pct = (premium / strike) * 100.0 if strike > 0 else None
                annualized_pct = _annualized_return_pct(premium, strike, dte)

                data.append({
                    **row,
                    "premium_percent_on_capital": premium_pct,
                    "annualized_return_percent": annualized_pct,
                    "capital_per_contract": capital,
                    "premium_value_per_contract": premium_value,
                    "moneyness_percent": ((strike / spot) - 1) * 100.0 if spot and strike else None,
                })

            return {
                "success": True,
                "symbol": stock.symbol,
                "name": stock.name,
                "market": market,
                "spot": spot,
                "spot_source": spot_source,
                "contract_multiplier": int(contract_multiplier),
                "recommended": data[0] if data else None,
                "data": data,
                "count": len(data),
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "delta_min": delta_min,
                    "delta_max": delta_max,
                    "dte_min": dte_min,
                    "dte_max": dte_max,
                    "limit": limit,
                    "require_liquidity": require_liquidity,
                },
                "empty_reason": None if data else "no_put_candidates_for_criteria",
            }
        except Exception as e:
            logger.error(f"Wheel put selection error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_atm_put_annualized_return(
        symbol: str,
        market: str = DEFAULT_MARKET,
        target_dte: int = 7,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
    ):
        session = SessionLocal()
        try:
            stock = _resolve_stock(session, symbol, market=market)
            if not stock:
                return {"success": False, "error": f"Stock '{symbol}' not found in market '{market}'"}

            spot, spot_source = _get_spot_price(session, stock.id)
            if spot is None:
                return {"success": False, "error": f"Spot price unavailable for {stock.symbol}"}

            cands = _list_candidates(
                session,
                stock.id,
                right="PUT",
                dte_min=max(1, target_dte - 4),
                dte_max=max(2, target_dte + 4),
                delta_min=None,
                delta_max=None,
                require_liquidity=True,
            )
            selected = _select_atm_option(cands, spot=spot, target_dte=target_dte)
            if not selected:
                return {
                    "success": True,
                    "data": None,
                    "criteria": {
                        "symbol": symbol,
                        "market": market,
                        "target_dte": target_dte,
                    },
                    "empty_reason": "no_atm_put_candidate",
                }

            strike = selected["strike"]
            premium = selected["premium"]
            dte = selected["dte"]
            capital_per_contract = strike * int(contract_multiplier)
            premium_value = premium * int(contract_multiplier)
            period_return_pct = (premium / strike) * 100.0 if strike > 0 else None
            annualized_pct = _annualized_return_pct(premium, strike, dte)

            return {
                "success": True,
                "symbol": stock.symbol,
                "market": market,
                "spot": spot,
                "spot_source": spot_source,
                "data": {
                    **selected,
                    "capital_per_contract": capital_per_contract,
                    "premium_value_per_contract": premium_value,
                    "period_return_percent": period_return_pct,
                    "annualized_return_percent": annualized_pct,
                    "formula": {
                        "period_return_percent": "(premium / strike) * 100",
                        "annualized_return_percent": "period_return_percent * (365 / dte)",
                    },
                },
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "target_dte": target_dte,
                    "contract_multiplier": int(contract_multiplier),
                },
                "empty_reason": None,
            }
        except Exception as e:
            logger.error(f"ATM annualized return error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_wheel_contract_capacity(
        symbol: str,
        capital_sek: float,
        market: str = DEFAULT_MARKET,
        strike: float = None,
        margin_requirement_pct: float = 1.0,
        cash_buffer_pct: float = 0.0,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
        target_dte: int = 7,
    ):
        session = SessionLocal()
        try:
            stock = _resolve_stock(session, symbol, market=market)
            if not stock:
                return {"success": False, "error": f"Stock '{symbol}' not found in market '{market}'"}

            margin_requirement_pct = max(0.01, float(margin_requirement_pct))
            cash_buffer_pct = max(0.0, min(float(cash_buffer_pct), 0.95))
            capital_sek = float(capital_sek)
            contract_multiplier = int(contract_multiplier)

            selected_strike = _to_float(strike)
            chosen_option = None

            spot, spot_source = _get_spot_price(session, stock.id)
            if selected_strike is None:
                cands = _list_candidates(
                    session,
                    stock.id,
                    right="PUT",
                    dte_min=max(1, target_dte - 4),
                    dte_max=max(2, target_dte + 4),
                    require_liquidity=True,
                )
                chosen_option = _select_atm_option(cands, spot=spot or 0.0, target_dte=target_dte)
                if not chosen_option:
                    return {
                        "success": True,
                        "data": None,
                        "criteria": {
                            "symbol": symbol,
                            "market": market,
                            "capital_sek": capital_sek,
                            "target_dte": target_dte,
                        },
                        "empty_reason": "no_option_for_capacity_estimate",
                    }
                selected_strike = chosen_option["strike"]

            reserved_per_contract = selected_strike * contract_multiplier * margin_requirement_pct
            deployable_capital = capital_sek * (1.0 - cash_buffer_pct)
            max_contracts = int(math.floor(deployable_capital / reserved_per_contract)) if reserved_per_contract > 0 else 0
            used_capital = max_contracts * reserved_per_contract
            remaining_capital = max(0.0, deployable_capital - used_capital)

            return {
                "success": True,
                "symbol": stock.symbol,
                "market": market,
                "spot": spot,
                "spot_source": spot_source,
                "data": {
                    "capital_sek": capital_sek,
                    "deployable_capital_sek": deployable_capital,
                    "cash_buffer_pct": cash_buffer_pct,
                    "strike": selected_strike,
                    "contract_multiplier": contract_multiplier,
                    "margin_requirement_pct": margin_requirement_pct,
                    "reserved_per_contract_sek": reserved_per_contract,
                    "max_contracts": max_contracts,
                    "capital_used_sek": used_capital,
                    "capital_remaining_sek": remaining_capital,
                    "selected_option": chosen_option,
                },
                "formula": {
                    "reserved_per_contract": "strike * contract_multiplier * margin_requirement_pct",
                    "max_contracts": "floor((capital * (1-cash_buffer_pct)) / reserved_per_contract)",
                },
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "capital_sek": capital_sek,
                    "strike": strike,
                    "margin_requirement_pct": margin_requirement_pct,
                    "cash_buffer_pct": cash_buffer_pct,
                    "contract_multiplier": contract_multiplier,
                },
                "empty_reason": None,
            }
        except Exception as e:
            logger.error(f"Wheel capacity error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def analyze_put_risk(
        symbol: str,
        market: str = DEFAULT_MARKET,
        pct_below_spot: float = 5.0,
        target_dte: int = 7,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
    ):
        session = SessionLocal()
        try:
            stock = _resolve_stock(session, symbol, market=market)
            if not stock:
                return {"success": False, "error": f"Stock '{symbol}' not found in market '{market}'"}

            spot, spot_source = _get_spot_price(session, stock.id)
            if spot is None:
                return {"success": False, "error": f"Spot price unavailable for {stock.symbol}"}

            target_strike = spot * (1.0 - float(pct_below_spot) / 100.0)
            cands = _list_candidates(
                session,
                stock.id,
                right="PUT",
                dte_min=max(1, target_dte - 4),
                dte_max=max(2, target_dte + 7),
                require_liquidity=True,
            )
            if not cands:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "data": None,
                    "criteria": {
                        "symbol": symbol,
                        "market": market,
                        "pct_below_spot": pct_below_spot,
                        "target_dte": target_dte,
                    },
                    "empty_reason": "no_put_candidates_for_risk_analysis",
                }

            selected = sorted(
                cands,
                key=lambda x: (
                    abs(x["strike"] - target_strike),
                    abs(x["dte"] - target_dte),
                ),
            )[0]

            strike = selected["strike"]
            premium = selected["premium"]
            break_even = strike - premium
            prob_itm = min(1.0, max(0.0, selected.get("delta_abs") or 0.0))
            exposure = strike * int(contract_multiplier)
            max_loss_zero = max(0.0, break_even) * int(contract_multiplier)

            return {
                "success": True,
                "symbol": stock.symbol,
                "market": market,
                "spot": spot,
                "spot_source": spot_source,
                "data": {
                    **selected,
                    "target_strike_from_spot": target_strike,
                    "break_even": break_even,
                    "probability_itm_approx": prob_itm,
                    "probability_assignment_approx": prob_itm,
                    "exposure_per_contract": exposure,
                    "max_loss_if_underlying_zero": max_loss_zero,
                    "buffer_to_break_even_percent": ((spot - break_even) / spot) * 100.0 if spot else None,
                },
                "assumptions": {
                    "probability_proxy": "abs(delta)",
                    "assignment_model": "European-style approximation at expiry",
                },
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "pct_below_spot": pct_below_spot,
                    "target_dte": target_dte,
                    "contract_multiplier": int(contract_multiplier),
                },
                "empty_reason": None,
            }
        except Exception as e:
            logger.error(f"Put risk analysis error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def evaluate_assignment(
        symbol: str,
        assignment_strike: float,
        premium_received: float,
        market: str = DEFAULT_MARKET,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
        call_delta_min: float = DEFAULT_DELTA_MIN,
        call_delta_max: float = DEFAULT_DELTA_MAX,
        call_dte_min: int = DEFAULT_DTE_MIN,
        call_dte_max: int = 21,
        min_upside_pct: float = 1.0,
        limit: int = DEFAULT_LIMIT,
    ):
        try:
            assignment_strike = float(assignment_strike)
            premium_received = float(premium_received)
        except (TypeError, ValueError):
            return {"success": False, "error": "assignment_strike and premium_received must be numeric"}

        cost_basis = assignment_strike - premium_received
        outlay = max(0.0, cost_basis) * int(contract_multiplier)

        covered_call = WheelService.suggest_covered_call_after_assignment(
            symbol=symbol,
            average_cost=cost_basis,
            market=market,
            delta_min=call_delta_min,
            delta_max=call_delta_max,
            dte_min=call_dte_min,
            dte_max=call_dte_max,
            min_upside_pct=min_upside_pct,
            limit=limit,
            contract_multiplier=contract_multiplier,
        )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "data": {
                "assignment_strike": assignment_strike,
                "premium_received": premium_received,
                "net_cost_basis_per_share": cost_basis,
                "net_cash_outlay_per_contract": outlay,
                "next_step": "sell_covered_call",
                "covered_call_plan": covered_call.get("data") if covered_call.get("success") else None,
            },
            "criteria": {
                "symbol": symbol,
                "market": market,
                "assignment_strike": assignment_strike,
                "premium_received": premium_received,
                "contract_multiplier": int(contract_multiplier),
            },
            "empty_reason": None,
        }

    @staticmethod
    def suggest_covered_call_after_assignment(
        symbol: str,
        average_cost: float,
        market: str = DEFAULT_MARKET,
        delta_min: float = DEFAULT_DELTA_MIN,
        delta_max: float = DEFAULT_DELTA_MAX,
        dte_min: int = DEFAULT_DTE_MIN,
        dte_max: int = 21,
        min_upside_pct: float = 1.0,
        limit: int = DEFAULT_LIMIT,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
    ):
        session = SessionLocal()
        try:
            limit = _normalize_limit(limit)
            average_cost = float(average_cost)
            floor_strike = average_cost * (1.0 + float(min_upside_pct) / 100.0)

            stock = _resolve_stock(session, symbol, market=market)
            if not stock:
                return {"success": False, "error": f"Stock '{symbol}' not found in market '{market}'"}

            spot, spot_source = _get_spot_price(session, stock.id)
            cands = _list_candidates(
                session,
                stock.id,
                right="CALL",
                dte_min=dte_min,
                dte_max=dte_max,
                delta_min=delta_min,
                delta_max=delta_max,
                require_liquidity=True,
            )

            cands = [c for c in cands if c["strike"] >= floor_strike]
            if not cands:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "market": market,
                    "spot": spot,
                    "spot_source": spot_source,
                    "average_cost": average_cost,
                    "data": [],
                    "count": 0,
                    "criteria": {
                        "symbol": symbol,
                        "market": market,
                        "average_cost": average_cost,
                        "delta_min": delta_min,
                        "delta_max": delta_max,
                        "dte_min": dte_min,
                        "dte_max": dte_max,
                        "min_upside_pct": min_upside_pct,
                        "limit": limit,
                    },
                    "empty_reason": "no_covered_call_candidates_for_criteria",
                }

            target_delta = (float(delta_min) + float(delta_max)) / 2.0
            ranked = sorted(
                cands,
                key=lambda x: (
                    abs((x.get("delta_abs") or target_delta) - target_delta),
                    -(_annualized_return_pct(x["premium"], max(average_cost, 0.01), x["dte"]) or -9999),
                ),
            )[:limit]

            data = []
            for row in ranked:
                premium = row["premium"]
                strike = row["strike"]
                dte = row["dte"]
                premium_value = premium * int(contract_multiplier)
                premium_yield = (premium / average_cost) * 100.0 if average_cost > 0 else None
                annualized = _annualized_return_pct(premium, max(average_cost, 0.01), dte)
                max_total_return = ((strike - average_cost + premium) / average_cost) * 100.0 if average_cost > 0 else None

                data.append({
                    **row,
                    "premium_value_per_contract": premium_value,
                    "premium_yield_on_cost_percent": premium_yield,
                    "annualized_return_percent": annualized,
                    "max_total_return_if_called_percent": max_total_return,
                    "upside_to_strike_percent": ((strike / average_cost) - 1.0) * 100.0 if average_cost > 0 else None,
                })

            return {
                "success": True,
                "symbol": stock.symbol,
                "name": stock.name,
                "market": market,
                "spot": spot,
                "spot_source": spot_source,
                "average_cost": average_cost,
                "recommended": data[0] if data else None,
                "data": data,
                "count": len(data),
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "average_cost": average_cost,
                    "delta_min": delta_min,
                    "delta_max": delta_max,
                    "dte_min": dte_min,
                    "dte_max": dte_max,
                    "min_upside_pct": min_upside_pct,
                    "limit": limit,
                },
                "empty_reason": None if data else "no_covered_call_candidates_for_criteria",
            }
        except Exception as e:
            logger.error(f"Covered call suggestion error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def compare_wheel_put_premiums(
        symbol_a: str,
        symbol_b: str,
        market: str = DEFAULT_MARKET,
        delta_min: float = DEFAULT_DELTA_MIN,
        delta_max: float = DEFAULT_DELTA_MAX,
        dte_min: int = DEFAULT_DTE_MIN,
        dte_max: int = DEFAULT_DTE_MAX,
    ):
        first = WheelService.select_put_for_wheel(
            symbol=symbol_a,
            market=market,
            delta_min=delta_min,
            delta_max=delta_max,
            dte_min=dte_min,
            dte_max=dte_max,
            limit=1,
        )
        second = WheelService.select_put_for_wheel(
            symbol=symbol_b,
            market=market,
            delta_min=delta_min,
            delta_max=delta_max,
            dte_min=dte_min,
            dte_max=dte_max,
            limit=1,
        )

        if not first.get("success") or not second.get("success"):
            return {
                "success": False,
                "error": "Failed to evaluate one or both symbols",
                "symbol_a_result": first,
                "symbol_b_result": second,
            }

        a_pick = first.get("recommended")
        b_pick = second.get("recommended")

        winner = None
        if a_pick and b_pick:
            a_yield = a_pick.get("premium_percent_on_capital") or -9999
            b_yield = b_pick.get("premium_percent_on_capital") or -9999
            winner = symbol_a if a_yield >= b_yield else symbol_b

        return {
            "success": True,
            "market": market,
            "data": {
                "symbol_a": symbol_a,
                "symbol_b": symbol_b,
                "pick_a": a_pick,
                "pick_b": b_pick,
                "winner_by_yield": winner,
                "comparison_basis": "premium_percent_on_capital",
            },
            "criteria": {
                "market": market,
                "delta_min": delta_min,
                "delta_max": delta_max,
                "dte_min": dte_min,
                "dte_max": dte_max,
            },
            "empty_reason": None if (a_pick or b_pick) else "no_candidates_for_both_symbols",
        }

    @staticmethod
    def evaluate_iv_regime_for_wheel(
        symbol: str,
        market: str = DEFAULT_MARKET,
        lookback_days: int = 90,
        high_iv_threshold_percentile: float = 70.0,
        target_dte: int = 7,
    ):
        session = SessionLocal()
        try:
            stock = _resolve_stock(session, symbol, market=market)
            if not stock:
                return {"success": False, "error": f"Stock '{symbol}' not found in market '{market}'"}

            spot, _ = _get_spot_price(session, stock.id)
            cands = _list_candidates(
                session,
                stock.id,
                right="PUT",
                dte_min=max(1, target_dte - 4),
                dte_max=max(2, target_dte + 4),
                require_liquidity=False,
            )
            current_atm = _select_atm_option(cands, spot=spot or 0.0, target_dte=target_dte)
            current_iv = current_atm.get("iv") if current_atm else None

            cutoff = date.today() - timedelta(days=max(5, int(lookback_days)))
            hist_rows = session.query(OptionIVSnapshot).filter(
                OptionIVSnapshot.stock_id == stock.id,
                OptionIVSnapshot.snapshot_date >= cutoff,
                OptionIVSnapshot.atm_iv.isnot(None),
            ).order_by(OptionIVSnapshot.snapshot_date.asc()).all()

            hist_values = [_to_float(r.atm_iv) for r in hist_rows if _to_float(r.atm_iv) is not None]
            if current_iv is None:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "market": market,
                    "data": None,
                    "criteria": {
                        "symbol": symbol,
                        "market": market,
                        "lookback_days": lookback_days,
                        "high_iv_threshold_percentile": high_iv_threshold_percentile,
                    },
                    "empty_reason": "current_iv_unavailable",
                }

            if len(hist_values) < 10:
                return {
                    "success": True,
                    "symbol": stock.symbol,
                    "market": market,
                    "data": {
                        "current_atm_iv": current_iv,
                        "history_points": len(hist_values),
                        "iv_percentile": None,
                        "high_enough_for_wheel": None,
                        "assessment": "insufficient_iv_history",
                    },
                    "criteria": {
                        "symbol": symbol,
                        "market": market,
                        "lookback_days": lookback_days,
                        "high_iv_threshold_percentile": high_iv_threshold_percentile,
                    },
                    "empty_reason": "insufficient_iv_history",
                }

            less_or_equal = sum(1 for v in hist_values if v <= current_iv)
            percentile = (less_or_equal / len(hist_values)) * 100.0
            high_enough = percentile >= float(high_iv_threshold_percentile)

            return {
                "success": True,
                "symbol": stock.symbol,
                "market": market,
                "data": {
                    "current_atm_iv": current_iv,
                    "history_points": len(hist_values),
                    "history_min_iv": min(hist_values),
                    "history_median_iv": median(hist_values),
                    "history_max_iv": max(hist_values),
                    "iv_percentile": percentile,
                    "high_enough_for_wheel": high_enough,
                    "assessment": "iv_rich" if high_enough else "iv_normal_or_low",
                },
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "lookback_days": lookback_days,
                    "high_iv_threshold_percentile": high_iv_threshold_percentile,
                },
                "empty_reason": None,
            }
        except Exception as e:
            logger.error(f"IV regime evaluation error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def simulate_wheel_drawdown(
        symbol: str,
        strike: float,
        premium_received: float,
        drop_percent: float = 10.0,
        market: str = DEFAULT_MARKET,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
    ):
        session = SessionLocal()
        try:
            stock = _resolve_stock(session, symbol, market=market)
            if not stock:
                return {"success": False, "error": f"Stock '{symbol}' not found in market '{market}'"}

            strike = float(strike)
            premium_received = float(premium_received)
            drop_percent = max(0.0, float(drop_percent))
            contract_multiplier = int(contract_multiplier)

            spot, spot_source = _get_spot_price(session, stock.id)
            if spot is None:
                return {"success": False, "error": f"Spot price unavailable for {stock.symbol}"}

            post_drop_price = spot * (1.0 - drop_percent / 100.0)
            break_even = strike - premium_received
            loss_per_share = max(0.0, break_even - post_drop_price)
            loss_per_contract = loss_per_share * contract_multiplier
            notional = strike * contract_multiplier

            return {
                "success": True,
                "symbol": stock.symbol,
                "market": market,
                "spot": spot,
                "spot_source": spot_source,
                "data": {
                    "strike": strike,
                    "premium_received": premium_received,
                    "break_even": break_even,
                    "drop_percent": drop_percent,
                    "post_drop_price": post_drop_price,
                    "loss_per_share_at_expiry": loss_per_share,
                    "loss_per_contract_at_expiry": loss_per_contract,
                    "drawdown_percent_on_collateral": (loss_per_contract / notional) * 100.0 if notional > 0 else None,
                    "notional_exposure_per_contract": notional,
                },
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "strike": strike,
                    "premium_received": premium_received,
                    "drop_percent": drop_percent,
                },
                "empty_reason": None,
            }
        except Exception as e:
            logger.error(f"Wheel drawdown simulation error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def compare_wheel_start_now_vs_wait(
        symbol: str,
        market: str = DEFAULT_MARKET,
        wait_drop_percent: float = 3.0,
        delta_min: float = DEFAULT_DELTA_MIN,
        delta_max: float = DEFAULT_DELTA_MAX,
        dte_min: int = DEFAULT_DTE_MIN,
        dte_max: int = DEFAULT_DTE_MAX,
    ):
        now_result = WheelService.select_put_for_wheel(
            symbol=symbol,
            market=market,
            delta_min=delta_min,
            delta_max=delta_max,
            dte_min=dte_min,
            dte_max=dte_max,
            limit=1,
        )
        if not now_result.get("success"):
            return now_result

        now_pick = now_result.get("recommended")
        spot = now_result.get("spot")
        if not now_pick or not spot:
            return {
                "success": True,
                "symbol": symbol,
                "market": market,
                "data": None,
                "criteria": {
                    "symbol": symbol,
                    "market": market,
                    "wait_drop_percent": wait_drop_percent,
                },
                "empty_reason": "no_current_reference_put",
            }

        strike_now = now_pick["strike"]
        premium_now = now_pick["premium"]
        net_entry_now = strike_now - premium_now

        wait_spot = float(spot) * (1.0 - float(wait_drop_percent) / 100.0)
        moneyness = (strike_now / float(spot)) - 1.0
        wait_target_strike = wait_spot * (1.0 + moneyness)

        premium_needed_to_match = wait_target_strike - net_entry_now

        proxy = None
        if now_result.get("symbol"):
            session = SessionLocal()
            try:
                stock = session.query(Stock).filter(Stock.symbol == now_result["symbol"]).first()
                if stock:
                    cands = _list_candidates(
                        session,
                        stock.id,
                        right="PUT",
                        dte_min=dte_min,
                        dte_max=dte_max,
                        delta_min=delta_min,
                        delta_max=delta_max,
                        require_liquidity=True,
                    )
                    if cands:
                        proxy = sorted(cands, key=lambda x: abs(x["strike"] - wait_target_strike))[0]
            finally:
                session.close()

        recommendation = "inconclusive_wait_requires_future_premium"
        if proxy:
            proxy_net_entry = proxy["strike"] - proxy["premium"]
            recommendation = "start_now" if net_entry_now <= proxy_net_entry else "wait_for_drop"

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "data": {
                "start_now": {
                    "spot": spot,
                    "selected_put": now_pick,
                    "net_entry_cost": net_entry_now,
                },
                "wait_scenario": {
                    "assumed_spot_after_drop": wait_spot,
                    "target_strike_to_keep_moneyness": wait_target_strike,
                    "premium_needed_to_match_start_now": premium_needed_to_match,
                    "proxy_current_chain_option": proxy,
                },
                "recommendation": recommendation,
                "uncertainty_note": "Future premium after a 3% move is unknown without forward pricing; this is a scenario comparison, not a forecast.",
            },
            "criteria": {
                "symbol": symbol,
                "market": market,
                "wait_drop_percent": wait_drop_percent,
                "delta_min": delta_min,
                "delta_max": delta_max,
                "dte_min": dte_min,
                "dte_max": dte_max,
            },
            "empty_reason": None,
        }

    @staticmethod
    def build_multi_stock_wheel_plan(
        capital_sek: float,
        symbols: List[str],
        market: str = DEFAULT_MARKET,
        delta_min: float = DEFAULT_DELTA_MIN,
        delta_max: float = DEFAULT_DELTA_MAX,
        dte_min: int = DEFAULT_DTE_MIN,
        dte_max: int = DEFAULT_DTE_MAX,
        margin_requirement_pct: float = 1.0,
        cash_buffer_pct: float = 0.10,
        contract_multiplier: int = DEFAULT_CONTRACT_MULTIPLIER,
    ):
        symbols = [s for s in (symbols or []) if s]
        if not symbols:
            symbols = ["Nordea", "SEB", "Swedbank"]

        capital_sek = float(capital_sek)
        deployable = capital_sek * (1.0 - max(0.0, min(float(cash_buffer_pct), 0.95)))
        per_symbol_budget = deployable / len(symbols)

        positions = []
        total_reserved = 0.0
        total_premium = 0.0

        for symbol in symbols:
            pick = WheelService.select_put_for_wheel(
                symbol=symbol,
                market=market,
                delta_min=delta_min,
                delta_max=delta_max,
                dte_min=dte_min,
                dte_max=dte_max,
                limit=1,
                contract_multiplier=contract_multiplier,
            )

            rec = pick.get("recommended") if pick.get("success") else None
            if not rec:
                positions.append({
                    "symbol": symbol,
                    "status": "no_candidate",
                })
                continue

            strike = rec["strike"]
            premium = rec["premium"]
            reserve_per_contract = strike * int(contract_multiplier) * float(margin_requirement_pct)
            contracts = int(math.floor(per_symbol_budget / reserve_per_contract)) if reserve_per_contract > 0 else 0
            reserved = contracts * reserve_per_contract
            premium_income = contracts * premium * int(contract_multiplier)

            total_reserved += reserved
            total_premium += premium_income

            positions.append({
                "symbol": pick.get("symbol") or symbol,
                "name": pick.get("name"),
                "allocation_budget_sek": per_symbol_budget,
                "selected_put": rec,
                "contracts": contracts,
                "reserved_capital_sek": reserved,
                "expected_premium_income_sek": premium_income,
            })

        return {
            "success": True,
            "market": market,
            "data": {
                "capital_sek": capital_sek,
                "deployable_capital_sek": deployable,
                "cash_buffer_pct": cash_buffer_pct,
                "positions": positions,
                "total_reserved_capital_sek": total_reserved,
                "total_expected_premium_income_sek": total_premium,
                "capital_remaining_sek": max(0.0, deployable - total_reserved),
            },
            "criteria": {
                "symbols": symbols,
                "market": market,
                "delta_min": delta_min,
                "delta_max": delta_max,
                "dte_min": dte_min,
                "dte_max": dte_max,
                "margin_requirement_pct": margin_requirement_pct,
                "cash_buffer_pct": cash_buffer_pct,
            },
            "empty_reason": None if positions else "no_positions_generated",
        }

    @staticmethod
    def stress_test_wheel_portfolio(
        capital_sek: float,
        sector_drop_percent: float = 20.0,
        symbols: List[str] = None,
        market: str = DEFAULT_MARKET,
        delta_min: float = DEFAULT_DELTA_MIN,
        delta_max: float = DEFAULT_DELTA_MAX,
        dte_min: int = DEFAULT_DTE_MIN,
        dte_max: int = DEFAULT_DTE_MAX,
    ):
        plan = WheelService.build_multi_stock_wheel_plan(
            capital_sek=capital_sek,
            symbols=symbols or ["Nordea", "SEB", "Swedbank"],
            market=market,
            delta_min=delta_min,
            delta_max=delta_max,
            dte_min=dte_min,
            dte_max=dte_max,
        )
        if not plan.get("success"):
            return plan

        positions = plan["data"].get("positions", [])
        drop = max(0.0, float(sector_drop_percent))

        stress_rows = []
        total_loss = 0.0

        for pos in positions:
            rec = pos.get("selected_put")
            contracts = int(pos.get("contracts") or 0)
            if not rec or contracts <= 0:
                continue

            strike = float(rec["strike"])
            premium = float(rec["premium"])
            spot = _to_float(plan.get("spot"))
            # Use option strike moneyness if spot is unavailable in this payload.
            if spot is None:
                spot = strike / max(0.01, 1.0 + ((rec.get("moneyness_percent") or 0.0) / 100.0))

            final_price = spot * (1.0 - drop / 100.0)
            break_even = strike - premium
            loss_per_share = max(0.0, break_even - final_price)
            loss_total = loss_per_share * DEFAULT_CONTRACT_MULTIPLIER * contracts
            total_loss += loss_total

            stress_rows.append({
                "symbol": pos.get("symbol"),
                "contracts": contracts,
                "strike": strike,
                "premium": premium,
                "break_even": break_even,
                "assumed_final_price": final_price,
                "loss_total_sek": loss_total,
            })

        capital = float(capital_sek)
        return {
            "success": True,
            "market": market,
            "data": {
                "sector_drop_percent": drop,
                "positions": stress_rows,
                "total_stress_loss_sek": total_loss,
                "total_stress_loss_percent_of_capital": (total_loss / capital) * 100.0 if capital > 0 else None,
            },
            "criteria": {
                "capital_sek": capital_sek,
                "symbols": symbols or ["Nordea", "SEB", "Swedbank"],
                "market": market,
                "sector_drop_percent": sector_drop_percent,
            },
            "empty_reason": None if stress_rows else "no_active_positions_to_stress",
        }
    @staticmethod
    def get_wheel_put_return(symbol: str, strike: float, expiry: str, premium: float, market: str = DEFAULT_MARKET):
        """Calculate annualized return for a specific put."""
        today = date.today()
        expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        dte = max(1, (expiry_date - today).days)
        annualized = _annualized_return_pct(premium, strike, dte)
        return {
            "success": True,
            "symbol": symbol,
            "strike": strike,
            "premium": premium,
            "dte": dte,
            "annualized_return_percent": annualized,
            "period_return_percent": (premium / strike) * 100.0 if strike > 0 else 0
        }

    @staticmethod
    def get_wheel_put_breakeven(symbol: str, strike: float, premium: float):
        """Calculate break-even for a put."""
        return {
            "success": True,
            "symbol": symbol,
            "strike": strike,
            "premium": premium,
            "break_even": strike - premium,
            "buffer_percent": (premium / strike) * 100.0 if strike > 0 else 0
        }

    @staticmethod
    def get_wheel_put_assignment_probability(symbol: str, strike: float, expiry: str, market: str = DEFAULT_MARKET):
        """Calculate approximate assignment probability using Delta."""
        session = SessionLocal()
        try:
            stock = _resolve_stock(session, symbol, market=market)
            if not stock: return {"success": False, "error": "Stock not found"}
            
            expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
            metric = session.query(OptionMetric).filter(
                OptionMetric.stock_id == stock.id,
                OptionMetric.strike == strike,
                OptionMetric.expiry == expiry_date,
                OptionMetric.right == "PUT"
            ).first()
            
            if not metric or metric.delta is None:
                return {"success": False, "error": "Option metrics (Delta) not found"}
            
            prob = abs(metric.delta)
            return {
                "success": True,
                "symbol": stock.symbol,
                "strike": strike,
                "expiry": expiry,
                "delta": metric.delta,
                "assignment_probability_approx": prob,
                "note": "Assignment probability is approximated using the absolute value of Delta."
            }
        finally:
            session.close()

    @staticmethod
    def get_wheel_capital_required(symbol: str, strike: float, contracts: int = 1, margin_pct: float = 1.0):
        """Calculate capital needed for a set of contracts."""
        capital = strike * DEFAULT_CONTRACT_MULTIPLIER * contracts * margin_pct
        return {
            "success": True,
            "symbol": symbol,
            "strike": strike,
            "contracts": contracts,
            "margin_requirement_pct": margin_pct,
            "capital_required_sek": capital
        }
    @staticmethod
    async def get_wheel_call_candidates(symbol: str, cost_basis: float, delta_min: float = 0.25, delta_max: float = 0.35, market: str = DEFAULT_MARKET):
        """Find candidate calls for the second half of the Wheel strategy."""
        # This uses OptionScreenerService internally
        from services.option_screener_service import OptionScreenerService
        return OptionScreenerService.get_option_screener(
            symbol=symbol, right="CALL", min_delta=delta_min, max_delta=delta_max
        )

    @staticmethod
    def get_wheel_call_return(symbol: str, strike: float, expiry: str, premium: float, cost_basis: float):
        """Calculate total return for a covered call (premium + upside)."""
        today = date.today()
        expiry_date = datetime.strptime(expiry, '%Y-%m-%d').date()
        dte = max(1, (expiry_date - today).days)
        
        capital_gain = (strike - cost_basis) if strike > cost_basis else 0
        total_profit = premium + capital_gain
        annualized = (total_profit / cost_basis) * (365 / dte) * 100.0 if cost_basis > 0 else 0
        
        return {
            "success": True,
            "symbol": symbol,
            "annualized_return_percent": annualized,
            "premium_return_percent": (premium / cost_basis) * 100.0 if cost_basis > 0 else 0,
            "upside_potential_percent": ((strike - cost_basis) / cost_basis) * 100.0 if cost_basis > 0 and strike > cost_basis else 0
        }
