#!/usr/bin/env python3
"""
Calculate Stock Metrics — Computes technical indicators and performance metrics.
Populates stock_metrics table with RSI, MACD, EMA, performance, etc.
Runs daily after market close.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from dataloader.database import SessionLocal
from dataloader.models import Stock, HistoricalPrice, StockMetrics, RealtimePrice


def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index."""
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_ema(prices, period):
    """Calculate Exponential Moving Average."""
    return pd.Series(prices).ewm(span=period, adjust=False).mean().iloc[-1]


def calculate_sma(prices, period):
    """Calculate Simple Moving Average."""
    return np.mean(prices[-period:]) if len(prices) >= period else None


def calculate_macd(prices, fast=12, slow=26, signal=9):
    """Calculate MACD (Moving Average Convergence Divergence)."""
    series = pd.Series(prices)
    ema_fast = series.ewm(span=fast, adjust=False).mean()
    ema_slow = series.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return {
        "macd": macd_line.iloc[-1],
        "signal": signal_line.iloc[-1],
        "histogram": histogram.iloc[-1]
    }


def calculate_atr(highs, lows, closes, period=14):
    """Calculate Average True Range."""
    if len(highs) < period + 1:
        return None
    
    tr = []
    for i in range(1, len(highs)):
        tr.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        ))
    
    return np.mean(tr[-period:]) if len(tr) >= period else None


def calculate_returns(prices, lookback_returns=30):
    """
    Robust return series using pct_change to avoid vector shape mismatches.
    Returns up to `lookback_returns` most recent finite returns.
    """
    if prices is None or len(prices) < 2:
        return np.array([], dtype=float)

    series = pd.Series(prices, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if len(series) < 2:
        return np.array([], dtype=float)

    returns = series.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    if returns.empty:
        return np.array([], dtype=float)

    arr = returns.tail(lookback_returns).to_numpy(dtype=float)
    if arr.ndim != 1:
        arr = arr.reshape(-1)
    return arr


def calculate_metrics_for_stock(session, stock_id, today):
    """Calculate all metrics for a single stock."""
    # Get historical data (1 year)
    one_year_ago = today - timedelta(days=365)
    
    historical = session.query(HistoricalPrice).filter(
        HistoricalPrice.stock_id == stock_id,
        HistoricalPrice.date >= one_year_ago,
        HistoricalPrice.date <= today
    ).order_by(HistoricalPrice.date).all()
    
    if len(historical) < 30:  # Need minimum data
        return None
    
    # Keep only valid rows to avoid NaN poisoning.
    cleaned = []
    for h in historical:
        if h.close is None or not np.isfinite(h.close) or h.close <= 0:
            continue
        open_high = h.high if h.high is not None and np.isfinite(h.high) else h.close
        open_low = h.low if h.low is not None and np.isfinite(h.low) else h.close
        vol = h.volume if h.volume is not None and np.isfinite(h.volume) else 0.0
        cleaned.append((h.date, float(h.close), float(open_high), float(open_low), float(vol)))

    if len(cleaned) < 30:
        return None

    # Convert to arrays
    dates = [x[0] for x in cleaned]
    closes = np.array([x[1] for x in cleaned], dtype=float)
    highs = np.array([x[2] for x in cleaned], dtype=float)
    lows = np.array([x[3] for x in cleaned], dtype=float)
    volumes = np.array([x[4] for x in cleaned], dtype=float)
    
    # Current price
    current_price = closes[-1]
    
    # Performance calculations
    metrics = {}
    
    # Performance (%)
    metrics['perf_1d'] = ((closes[-1] / closes[-2]) - 1) * 100 if len(closes) >= 2 else None
    metrics['perf_1w'] = ((closes[-1] / closes[-5]) - 1) * 100 if len(closes) >= 5 else None
    metrics['perf_2w'] = ((closes[-1] / closes[-10]) - 1) * 100 if len(closes) >= 10 else None
    metrics['perf_1m'] = ((closes[-1] / closes[-21]) - 1) * 100 if len(closes) >= 21 else None
    metrics['perf_3m'] = ((closes[-1] / closes[-63]) - 1) * 100 if len(closes) >= 63 else None
    metrics['perf_1y'] = ((closes[-1] / closes[0]) - 1) * 100 if len(closes) >= 252 else None
    
    # YTD (from Jan 1)
    ytd_start_idx = next((i for i, d in enumerate(dates) if d.year == today.year), 0)
    if ytd_start_idx < len(closes) - 1:
        metrics['perf_ytd'] = ((closes[-1] / closes[ytd_start_idx]) - 1) * 100
    
    # Technical Indicators
    if len(closes) >= 15:
        metrics['rsi_14'] = calculate_rsi(closes, 14)
    
    if len(closes) >= 26:
        macd_data = calculate_macd(closes)
        metrics['macd'] = macd_data['macd']
        metrics['macd_signal'] = macd_data['signal']
        metrics['macd_hist'] = macd_data['histogram']
    
    if len(closes) >= 20:
        metrics['ema_20'] = calculate_ema(closes, 20)
    
    if len(closes) >= 50:
        metrics['ema_50'] = calculate_ema(closes, 50)
    
    if len(closes) >= 200:
        metrics['sma_200'] = calculate_sma(closes, 200)
    
    # Volume metrics
    if len(volumes) >= 10:
        metrics['avg_volume_10d'] = np.mean(volumes[-10:])
        metrics['volume_ratio'] = volumes[-1] / metrics['avg_volume_10d'] if metrics['avg_volume_10d'] > 0 else None
    
    # Volatility (30-day std dev of returns)
    if len(closes) >= 30:
        returns = calculate_returns(closes, lookback_returns=30)
        metrics['volatility_30d'] = (np.std(returns) * 100) if len(returns) > 0 else None
    
    # ATR
    if len(highs) >= 15:
        metrics['atr_14'] = calculate_atr(highs, lows, closes, 14)
    
    # 52-week high/low
    if len(closes) >= 252:
        last_year = closes[-252:]
        metrics['high_52w'] = np.max(last_year)
        metrics['low_52w'] = np.min(last_year)
        metrics['distance_52w_high'] = ((current_price /metrics['high_52w']) - 1) * 100
        metrics['distance_52w_low'] = ((current_price / metrics['low_52w']) - 1) * 100
    
    return metrics, dates[-1]


def ensure_python_types(metrics):
    """Convert numpy types to standard python types for database compatibility."""
    result = {}
    for k, v in metrics.items():
        if v is None:
            result[k] = None
        elif isinstance(v, (np.floating, float)):
            val = float(v)
            if np.isnan(val) or np.isinf(val):
                result[k] = None
            else:
                result[k] = val
        elif isinstance(v, (np.integer, int)):
            result[k] = int(v)
        elif hasattr(v, 'item'): # Fallback for other numpy scalars
            val = v.item()
            if isinstance(val, float) and (np.isnan(val) or np.isinf(val)):
                result[k] = None
            else:
                result[k] = val
        else:
            result[k] = v
    return result


def main():
    session = SessionLocal()
    count = 0
    today = date.today()
    
    try:
        # Get all stocks
        stocks = session.query(Stock).all()
        
        print(f"[CALCULATE METRICS] Processing {len(stocks)} stocks...")
        
        for stock in stocks:
            try:
                result = calculate_metrics_for_stock(session, stock.id, today)
                
                if not result:
                    continue

                metrics, metrics_date = result
                
                # Sanitize for PostgreSQL compatibility
                metrics = ensure_python_types(metrics)
                
                # Upsert metrics
                existing = session.query(StockMetrics).filter_by(
                    stock_id=stock.id,
                    date=metrics_date
                ).first()
                
                if existing:
                    # Update
                    for key, value in metrics.items():
                        setattr(existing, key, value)
                    existing.calculated_at = datetime.utcnow()
                else:
                    # Insert
                    new_metric = StockMetrics(
                        stock_id=stock.id,
                        date=metrics_date,
                        **metrics
                    )
                    session.add(new_metric)
                
                count += 1
                
                if count % 10 == 0:
                    session.commit()
                    print(f"  Processed {count} stocks...")
                
            except Exception as e:
                print(f"  ⚠️  Failed for {stock.symbol}: {type(e).__name__}: {e}", file=sys.stderr)
                continue
        
        session.commit()
        print(f"[CALCULATE METRICS] Calculated metrics for {count} stocks")
        print(f"RECORDS_AFFECTED={count}")
        
    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
