#!/usr/bin/env python3
"""
Load Market Intelligence - Fetches Yahoo-based intelligence datasets and stores
normalized JSON snapshots in stock_intelligence_snapshots.

Runtime MCP tools consume these local snapshots to avoid direct API calls.
"""
import sys
import os
import json
import time
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, StockIntelligenceSnapshot


def _safe_float(value):
    try:
        if value is None:
            return None
        f = float(value)
        if f != f or f == float("inf") or f == float("-inf"):
            return None
        return f
    except Exception:
        return None


def _safe_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _safe_date(value):
    if value is None:
        return None
    try:
        if hasattr(value, "date"):
            return value.date().isoformat()
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return str(value)
    except Exception:
        return str(value)


def _to_json(data):
    return json.dumps(data, ensure_ascii=False)


def _extract_news(ticker, limit: int):
    raw = ticker.news or []
    items = []
    for article in raw[:max(1, limit)]:
        thumb = None
        thumbnail = article.get("thumbnail") if isinstance(article, dict) else None
        if isinstance(thumbnail, dict):
            resolutions = thumbnail.get("resolutions") or []
            if resolutions and isinstance(resolutions[0], dict):
                thumb = resolutions[0].get("url")

        items.append(
            {
                "uuid": article.get("uuid"),
                "title": article.get("title"),
                "publisher": article.get("publisher"),
                "link": article.get("link"),
                "provider_publish_time": article.get("providerPublishTime"),
                "publish_datetime_utc": datetime.utcfromtimestamp(article.get("providerPublishTime")).isoformat()
                if article.get("providerPublishTime")
                else None,
                "type": article.get("type"),
                "thumbnail": thumb,
                "related_tickers": article.get("relatedTickers") or [],
            }
        )
    return items


def _extract_institutional_holders(ticker):
    holders = []
    df = ticker.institutional_holders
    if df is None or getattr(df, "empty", True):
        return holders

    for _, row in df.iterrows():
        holders.append(
            {
                "holder": row.get("Holder"),
                "shares": _safe_int(row.get("Shares")),
                "date_reported": _safe_date(row.get("Date Reported")),
                "percent_out": _safe_float(row.get("% Out")),
                "value": _safe_int(row.get("Value")),
            }
        )
    return holders


def _extract_major_holders(ticker):
    major = {}
    df = ticker.major_holders
    if df is None or getattr(df, "empty", True):
        return major

    try:
        for _, row in df.iterrows():
            if len(row) >= 2:
                label = str(row.iloc[1])
                value = str(row.iloc[0])
                major[label] = value
    except Exception:
        return {}

    return major


def _extract_recommendations(ticker):
    recommendations = []
    upgrades = []

    try:
        rec_df = ticker.recommendations
        if rec_df is not None and not rec_df.empty:
            for idx, row in rec_df.iterrows():
                recommendations.append(
                    {
                        "date": _safe_date(idx),
                        "firm": row.get("Firm"),
                        "to_grade": row.get("To Grade"),
                        "from_grade": row.get("From Grade"),
                        "action": row.get("Action"),
                    }
                )
    except Exception:
        pass

    try:
        up_df = ticker.upgrades_downgrades
        if up_df is not None and not up_df.empty:
            for idx, row in up_df.iterrows():
                upgrades.append(
                    {
                        "date": _safe_date(idx),
                        "firm": row.get("Firm"),
                        "to_grade": row.get("ToGrade"),
                        "from_grade": row.get("FromGrade"),
                        "action": row.get("Action"),
                    }
                )
    except Exception:
        pass

    return recommendations, upgrades


def _format_statement_df(df):
    if df is None or getattr(df, "empty", True):
        return {}

    out = {}
    for col in df.columns:
        period_key = _safe_date(col)
        period_map = {}
        for idx in df.index:
            val = df.at[idx, col]
            if hasattr(val, "item"):
                try:
                    val = val.item()
                except Exception:
                    pass
            if isinstance(val, (int, float)):
                casted = _safe_float(val)
                period_map[str(idx)] = casted
            else:
                period_map[str(idx)] = None if val is None else str(val)
        out[period_key] = period_map
    return out


def _extract_financial_statements(ticker):
    statements = {
        "income_statement": {},
        "balance_sheet": {},
        "cash_flow": {},
        "quarterly_income_statement": {},
        "quarterly_balance_sheet": {},
        "quarterly_cash_flow": {},
    }

    try:
        statements["income_statement"] = _format_statement_df(ticker.income_stmt)
    except Exception:
        pass
    try:
        statements["balance_sheet"] = _format_statement_df(ticker.balance_sheet)
    except Exception:
        pass
    try:
        statements["cash_flow"] = _format_statement_df(ticker.cashflow)
    except Exception:
        pass
    try:
        statements["quarterly_income_statement"] = _format_statement_df(ticker.quarterly_income_stmt)
    except Exception:
        pass
    try:
        statements["quarterly_balance_sheet"] = _format_statement_df(ticker.quarterly_balance_sheet)
    except Exception:
        pass
    try:
        statements["quarterly_cash_flow"] = _format_statement_df(ticker.quarterly_cashflow)
    except Exception:
        pass

    return statements


def _extract_analyst_targets(ticker):
    try:
        targets = ticker.analyst_price_targets or {}
        return {
            "current": _safe_float(targets.get("current")),
            "high": _safe_float(targets.get("high")),
            "low": _safe_float(targets.get("low")),
            "mean": _safe_float(targets.get("mean")),
            "median": _safe_float(targets.get("median")),
        }
    except Exception:
        return {}


def main(market: str = None, news_limit: int = 20, max_stocks: int = None, sleep_seconds: float = 0.35, test: bool = False):
    init_db()

    if test:
        max_stocks = 1
        news_limit = min(news_limit, 2)

    import yfinance as yf

    session = SessionLocal()
    processed = 0

    try:
        query = session.query(Stock)
        if market:
            m = market.strip().upper()
            query = query.filter(Stock.exchange == m)

        stocks = query.order_by(Stock.symbol.asc()).all()
        if max_stocks is not None:
            stocks = stocks[: max(0, int(max_stocks))]

        print(f"[LOAD MARKET INTELLIGENCE] Processing {len(stocks)} stocks...")

        for stock in stocks:
            try:
                ticker = yf.Ticker(stock.symbol)

                news = _extract_news(ticker, news_limit)
                institutional = _extract_institutional_holders(ticker)
                major = _extract_major_holders(ticker)
                recommendations, upgrades = _extract_recommendations(ticker)
                statements = _extract_financial_statements(ticker)
                analyst_targets = _extract_analyst_targets(ticker)

                snapshot = session.query(StockIntelligenceSnapshot).filter(
                    StockIntelligenceSnapshot.stock_id == stock.id
                ).first()

                if not snapshot:
                    snapshot = StockIntelligenceSnapshot(stock_id=stock.id, source="yahoo")
                    session.add(snapshot)

                snapshot.fetched_at = datetime.utcnow()
                snapshot.news_json = _to_json(news)
                snapshot.institutional_holders_json = _to_json(institutional)
                snapshot.major_holders_json = _to_json(major)
                snapshot.analyst_recommendations_json = _to_json(recommendations)
                snapshot.upgrades_downgrades_json = _to_json(upgrades)
                snapshot.analyst_price_targets_json = _to_json(analyst_targets)
                snapshot.financial_statements_json = _to_json(statements)
                snapshot.payload = _to_json(
                    {
                        "symbol": stock.symbol,
                        "news_count": len(news),
                        "institutional_holders_count": len(institutional),
                        "recommendations_count": len(recommendations),
                        "upgrades_downgrades_count": len(upgrades),
                    }
                )

                processed += 1
                if processed % 10 == 0:
                    session.commit()
                    print(f"  Processed {processed} stocks...")

                time.sleep(max(0.0, sleep_seconds))

            except Exception as e:
                print(f"  ⚠️  Failed for {stock.symbol}: {type(e).__name__}: {e}", file=sys.stderr)
                continue

        session.commit()
        print(f"[LOAD MARKET INTELLIGENCE] Updated {processed} snapshots")
        print(f"RECORDS_AFFECTED={processed}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


def _parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--market", help="Optional exchange filter, e.g. OMX/B3/NASDAQ")
    parser.add_argument("--news-limit", type=int, default=20)
    parser.add_argument("--max-stocks", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.35)
    parser.add_argument("--test", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    main(
        market=args.market,
        news_limit=args.news_limit,
        max_stocks=args.max_stocks,
        sleep_seconds=args.sleep_seconds,
        test=args.test,
    )
