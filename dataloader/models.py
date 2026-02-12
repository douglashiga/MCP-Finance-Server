"""
SQLAlchemy models for the finance data warehouse and job scheduler.
"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Text, DateTime, Date,
    Boolean, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


# ============================================================================
# Finance Data Models
# ============================================================================

class Stock(Base):
    """Stock registry — each tradeable instrument."""
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)          # e.g. PETR4.SA, VOLV-B.ST
    name = Column(String(200), nullable=False)
    exchange = Column(String(50), nullable=False)         # e.g. B3, OMX, NASDAQ
    sector = Column(String(100))
    industry = Column(String(100))
    currency = Column(String(10), default="USD")
    country = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    fundamentals = relationship("Fundamental", back_populates="stock", cascade="all, delete-orphan")
    dividends = relationship("Dividend", back_populates="stock", cascade="all, delete-orphan")
    prices = relationship("HistoricalPrice", back_populates="stock", cascade="all, delete-orphan")
    index_memberships = relationship("IndexComponent", back_populates="stock", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("symbol", "exchange", name="uq_stock_symbol_exchange"),
    )

    def __repr__(self):
        return f"<Stock {self.symbol} ({self.exchange})>"


class Fundamental(Base):
    """Fundamental data snapshot for a stock (one row per fetch)."""
    __tablename__ = "fundamentals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    market_cap = Column(Float)
    enterprise_value = Column(Float)
    trailing_pe = Column(Float)
    forward_pe = Column(Float)
    trailing_eps = Column(Float)
    forward_eps = Column(Float)
    peg_ratio = Column(Float)
    price_to_book = Column(Float)
    revenue = Column(Float)
    revenue_growth = Column(Float)
    gross_margin = Column(Float)
    operating_margin = Column(Float)
    net_margin = Column(Float)
    roe = Column(Float)                # Return on Equity
    roa = Column(Float)                # Return on Assets
    debt_to_equity = Column(Float)
    current_ratio = Column(Float)
    total_debt = Column(Float)
    total_cash = Column(Float)
    net_debt = Column(Float)           # total_debt - total_cash
    free_cash_flow = Column(Float)
    ebitda = Column(Float)

    stock = relationship("Stock", back_populates="fundamentals")

    __table_args__ = (
        Index("ix_fundamentals_stock_date", "stock_id", "fetched_at"),
    )


class Dividend(Base):
    """Historical dividend payment."""
    __tablename__ = "dividends"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    ex_date = Column(Date, nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String(10))
    dividend_yield = Column(Float)           # Annual yield at time of payment
    payout_ratio = Column(Float)

    stock = relationship("Stock", back_populates="dividends")

    __table_args__ = (
        UniqueConstraint("stock_id", "ex_date", "amount", name="uq_dividend_record"),
        Index("ix_dividends_stock_date", "stock_id", "ex_date"),
    )


class HistoricalPrice(Base):
    """Daily OHLCV price data."""
    __tablename__ = "historical_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    adj_close = Column(Float)
    volume = Column(Float)

    stock = relationship("Stock", back_populates="prices")

    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_price_stock_date"),
        Index("ix_prices_stock_date", "stock_id", "date"),
    )


class IndexComponent(Base):
    """Stock membership in a market index."""
    __tablename__ = "index_components"

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_name = Column(String(50), nullable=False)        # e.g. OMXS30, IBOV, OMXSPI
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    weight = Column(Float)                                  # Percentage weight in index
    added_at = Column(DateTime, default=datetime.utcnow)

    stock = relationship("Stock", back_populates="index_memberships")

    __table_args__ = (
        UniqueConstraint("index_name", "stock_id", name="uq_index_stock"),
    )


class IndexPerformance(Base):
    """Daily performance data for market indices."""
    __tablename__ = "index_performance"

    id = Column(Integer, primary_key=True, autoincrement=True)
    index_symbol = Column(String(20), nullable=False)       # e.g. ^BVSP, ^OMX
    index_name = Column(String(100))
    date = Column(Date, nullable=False)
    close = Column(Float)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)

    __table_args__ = (
        UniqueConstraint("index_symbol", "date", name="uq_index_perf_date"),
        Index("ix_index_perf_symbol_date", "index_symbol", "date"),
    )


# ============================================================================
# Raw Data Models (ELT: Extract Layer)
# ============================================================================

class RawYahooPrice(Base):
    """Raw price data from Yahoo Finance API (stored as-is)."""
    __tablename__ = "raw_yahoo_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    data = Column(Text, nullable=False)  # JSON string from yfinance
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_raw_yahoo_prices_symbol_date", "symbol", "fetched_at"),
    )


class RawYahooFundamental(Base):
    """Raw fundamental data from Yahoo Finance API."""
    __tablename__ = "raw_yahoo_fundamentals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    data = Column(Text, nullable=False)  # JSON string from yfinance.info
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_raw_yahoo_fundamentals_symbol_date", "symbol", "fetched_at"),
    )


class RawIBKRPrice(Base):
    """Raw price data from IBKR API."""
    __tablename__ = "raw_ibkr_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False)
    exchange = Column(String(50))
    data = Column(Text, nullable=False)  # JSON string from IBKR
    fetched_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_raw_ibkr_prices_symbol_date", "symbol", "fetched_at"),
    )


# ============================================================================
# Normalized Real-time Data (ELT: Transform Layer Output)
# ============================================================================

class RealtimePrice(Base):
    """Normalized real-time price data (updated every minute)."""
    __tablename__ = "realtime_prices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False, unique=True)
    price = Column(Float)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    volume = Column(Float)
    change = Column(Float)
    change_percent = Column(Float)
    currency = Column(String(10))
    market_state = Column(String(20))  # REGULAR, PRE, POST, CLOSED
    last_updated = Column(DateTime, default=datetime.utcnow, nullable=False)

    stock = relationship("Stock")

    __table_args__ = (
        Index("ix_realtime_prices_stock", "stock_id"),
    )


class StockMetrics(Base):
    """Calculated technical indicators and performance metrics (updated daily)."""
    __tablename__ = "stock_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    date = Column(Date, nullable=False)
    
    # Performance (%)
    perf_1d = Column(Float)      # 1 day return
    perf_1w = Column(Float)      # 1 week return
    perf_2w = Column(Float)      # 2 weeks return
    perf_1m = Column(Float)      # 1 month return
    perf_3m = Column(Float)      # 3 months return
    perf_1y = Column(Float)      # 1 year return
    perf_ytd = Column(Float)     # Year-to-date return
    
    # Technical Indicators
    rsi_14 = Column(Float)           # RSI (14 periods)
    macd = Column(Float)             # MACD line
    macd_signal = Column(Float)      # MACD signal line
    macd_hist = Column(Float)        # MACD histogram
    ema_20 = Column(Float)           # EMA 20
    ema_50 = Column(Float)           # EMA 50
    sma_200 = Column(Float)          # SMA 200
    
    # Volume
    avg_volume_10d = Column(Float)   # 10-day average volume
    volume_ratio = Column(Float)     # Current volume / avg volume
    
    # Volatility
    volatility_30d = Column(Float)   # 30-day volatility (std dev of returns)
    atr_14 = Column(Float)           # Average True Range (14 periods)
    
    # Price Action
    high_52w = Column(Float)         # 52-week high
    low_52w = Column(Float)          # 52-week low
    distance_52w_high = Column(Float)  # % distance from 52w high
    distance_52w_low = Column(Float)   # % distance from 52w low
    
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    stock = relationship("Stock")
    
    __table_args__ = (
        UniqueConstraint("stock_id", "date", name="uq_stock_metrics_stock_date"),
        Index("ix_stock_metrics_stock", "stock_id"),
        Index("ix_stock_metrics_date", "date"),
    )


class MarketMover(Base):
    """Top gainers/losers by market and period (cache for fast queries)."""
    __tablename__ = "market_movers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market = Column(String(10), nullable=False)      # B3, OMX, NASDAQ, NYSE
    period = Column(String(10), nullable=False)      # 1D, 1W, 1M
    category = Column(String(50), nullable=False)    # top_gainers, top_losers, most_active
    rank = Column(Integer, nullable=False)           # 1-10
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    value = Column(Float, nullable=False)            # Performance % or volume
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    stock = relationship("Stock")
    
    __table_args__ = (
        UniqueConstraint("market", "period", "category", "rank", name="uq_market_mover"),
        Index("ix_market_movers_lookup", "market", "period", "category"),
    )


class OptionMetric(Base):
    """Real-time/Cached option chain data including Greeks and bid/ask."""
    __tablename__ = "option_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_id = Column(Integer, ForeignKey("stocks.id", ondelete="CASCADE"), nullable=False)
    option_symbol = Column(String(50), nullable=False) # e.g. PETR4C300
    strike = Column(Float, nullable=False)
    right = Column(String(5), nullable=False) # CALL/PUT
    expiry = Column(Date, nullable=False)
    
    # Quotes
    bid = Column(Float)
    ask = Column(Float)
    last = Column(Float)
    volume = Column(Integer)
    open_interest = Column(Integer)
    
    # Greeks
    delta = Column(Float)
    gamma = Column(Float)
    theta = Column(Float)
    vega = Column(Float)
    iv = Column(Float)
    
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    stock = relationship("Stock")
    
    __table_args__ = (
        UniqueConstraint("option_symbol", name="uq_option_symbol"),
        Index("ix_option_metrics_stock_expiry", "stock_id", "expiry"),
        Index("ix_option_metrics_expiry", "expiry"),
    )


# ============================================================================
# Scheduler Models
# ============================================================================

class Job(Base):
    """A registered data loader job."""
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True)
    description = Column(Text)
    script_path = Column(String(500), nullable=False)       # Relative to dataloader/scripts/
    cron_expression = Column(String(100))                    # e.g. "0 6 * * *"
    is_active = Column(Boolean, default=True)
    timeout_seconds = Column(Integer, default=300)           # 5 min default
    affected_tables = Column(Text)                           # Comma-separated list of table names
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    runs = relationship("JobRun", back_populates="job", cascade="all, delete-orphan",
                        order_by="JobRun.started_at.desc()")

    def __repr__(self):
        return f"<Job {self.name} (cron={self.cron_expression})>"


class JobRun(Base):
    """Execution log for a job run."""
    __tablename__ = "job_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    finished_at = Column(DateTime)
    status = Column(String(20), default="running")          # running, success, failed, timeout
    exit_code = Column(Integer)
    stdout = Column(Text)
    stderr = Column(Text)
    trigger = Column(String(20), default="cron")            # cron, manual
    duration_seconds = Column(Float)
    records_affected = Column(Integer)                       # Optional: how many rows changed

    job = relationship("Job", back_populates="runs")

    __table_args__ = (
        Index("ix_job_runs_job_status", "job_id", "status"),
        Index("ix_job_runs_started", "started_at"),
    )
