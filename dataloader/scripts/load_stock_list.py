#!/usr/bin/env python3
"""
Load Stock List — Populates stocks and index_components tables.
Covers: OMXS30, Ibovespa/B3 top stocks, Nasdaq Stockholm, plus key comparison stocks.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from dataloader.database import SessionLocal, init_db
from dataloader.models import Stock, IndexComponent

# ============================================================================
# Stock definitions
# ============================================================================

OMXS30_STOCKS = [
    {"symbol": "ABB.ST", "name": "ABB Ltd", "sector": "Industrials", "industry": "Electrical Equipment"},
    {"symbol": "ALFA.ST", "name": "Alfa Laval", "sector": "Industrials", "industry": "Machinery"},
    {"symbol": "ASSA-B.ST", "name": "ASSA ABLOY B", "sector": "Industrials", "industry": "Security"},
    {"symbol": "ATCO-A.ST", "name": "Atlas Copco A", "sector": "Industrials", "industry": "Machinery"},
    {"symbol": "ATCO-B.ST", "name": "Atlas Copco B", "sector": "Industrials", "industry": "Machinery"},
    {"symbol": "AZN.ST", "name": "AstraZeneca", "sector": "Healthcare", "industry": "Pharmaceuticals"},
    {"symbol": "BOL.ST", "name": "Boliden", "sector": "Materials", "industry": "Mining"},
    {"symbol": "ELUX-B.ST", "name": "Electrolux B", "sector": "Consumer Discretionary", "industry": "Household Appliances"},
    {"symbol": "ERIC-B.ST", "name": "Ericsson B", "sector": "Technology", "industry": "Telecom Equipment"},
    {"symbol": "ESSITY-B.ST", "name": "Essity B", "sector": "Consumer Staples", "industry": "Hygiene Products"},
    {"symbol": "EVO.ST", "name": "Evolution", "sector": "Consumer Discretionary", "industry": "Gaming"},
    {"symbol": "GETI-B.ST", "name": "Getinge B", "sector": "Healthcare", "industry": "Medical Devices"},
    {"symbol": "HEXA-B.ST", "name": "Hexagon B", "sector": "Technology", "industry": "Measurement Technology"},
    {"symbol": "HM-B.ST", "name": "H&M B", "sector": "Consumer Discretionary", "industry": "Retail"},
    {"symbol": "INVE-B.ST", "name": "Investor B", "sector": "Financials", "industry": "Investment Company"},
    {"symbol": "KINV-B.ST", "name": "Kinnevik B", "sector": "Financials", "industry": "Investment Company"},
    {"symbol": "NDA-SE.ST", "name": "Nordea", "sector": "Financials", "industry": "Banking"},
    {"symbol": "SAND.ST", "name": "Sandvik", "sector": "Industrials", "industry": "Machinery"},
    {"symbol": "SCA-B.ST", "name": "SCA B", "sector": "Materials", "industry": "Forest Products"},
    {"symbol": "SEB-A.ST", "name": "SEB A", "sector": "Financials", "industry": "Banking"},
    {"symbol": "SHB-A.ST", "name": "Handelsbanken A", "sector": "Financials", "industry": "Banking"},
    {"symbol": "SINCH.ST", "name": "Sinch", "sector": "Technology", "industry": "Cloud Communications"},
    {"symbol": "SKA-B.ST", "name": "Skanska B", "sector": "Industrials", "industry": "Construction"},
    {"symbol": "SKF-B.ST", "name": "SKF B", "sector": "Industrials", "industry": "Bearings"},
    {"symbol": "SWED-A.ST", "name": "Swedbank A", "sector": "Financials", "industry": "Banking"},
    {"symbol": "SWMA.ST", "name": "Swedish Match", "sector": "Consumer Staples", "industry": "Tobacco"},
    {"symbol": "TEL2-B.ST", "name": "Tele2 B", "sector": "Telecom", "industry": "Telecommunications"},
    {"symbol": "TELIA.ST", "name": "Telia Company", "sector": "Telecom", "industry": "Telecommunications"},
    {"symbol": "VOLV-B.ST", "name": "Volvo B", "sector": "Industrials", "industry": "Trucks & Machinery"},
    {"symbol": "NIBE-B.ST", "name": "NIBE Industrier B", "sector": "Industrials", "industry": "Climate Solutions"},
]

B3_STOCKS = [
    {"symbol": "PETR4.SA", "name": "Petrobras PN", "sector": "Energy", "industry": "Oil & Gas"},
    {"symbol": "VALE3.SA", "name": "Vale", "sector": "Materials", "industry": "Mining"},
    {"symbol": "ITUB4.SA", "name": "Itaú Unibanco PN", "sector": "Financials", "industry": "Banking"},
    {"symbol": "BBDC4.SA", "name": "Bradesco PN", "sector": "Financials", "industry": "Banking"},
    {"symbol": "ABEV3.SA", "name": "Ambev", "sector": "Consumer Staples", "industry": "Beverages"},
    {"symbol": "B3SA3.SA", "name": "B3 S.A.", "sector": "Financials", "industry": "Stock Exchange"},
    {"symbol": "BBAS3.SA", "name": "Banco do Brasil", "sector": "Financials", "industry": "Banking"},
    {"symbol": "WEGE3.SA", "name": "WEG", "sector": "Industrials", "industry": "Electrical Equipment"},
    {"symbol": "RENT3.SA", "name": "Localiza", "sector": "Consumer Discretionary", "industry": "Car Rental"},
    {"symbol": "SUZB3.SA", "name": "Suzano", "sector": "Materials", "industry": "Pulp & Paper"},
    {"symbol": "JBSS3.SA", "name": "JBS", "sector": "Consumer Staples", "industry": "Meat Processing"},
    {"symbol": "GGBR4.SA", "name": "Gerdau PN", "sector": "Materials", "industry": "Steel"},
    {"symbol": "CSNA3.SA", "name": "CSN", "sector": "Materials", "industry": "Steel"},
    {"symbol": "MGLU3.SA", "name": "Magazine Luiza", "sector": "Consumer Discretionary", "industry": "E-commerce"},
    {"symbol": "LREN3.SA", "name": "Lojas Renner", "sector": "Consumer Discretionary", "industry": "Retail"},
    {"symbol": "RADL3.SA", "name": "Raia Drogasil", "sector": "Healthcare", "industry": "Pharmacy"},
    {"symbol": "HAPV3.SA", "name": "Hapvida", "sector": "Healthcare", "industry": "Health Insurance"},
    {"symbol": "CPLE6.SA", "name": "Copel PNB", "sector": "Utilities", "industry": "Electric Utilities"},
    {"symbol": "CMIG4.SA", "name": "Cemig PN", "sector": "Utilities", "industry": "Electric Utilities"},
    {"symbol": "VIVT3.SA", "name": "Telefônica Brasil", "sector": "Telecom", "industry": "Telecommunications"},
]

US_STOCKS = [
    # Tech Giants (FAANG+)
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Technology", "industry": "Consumer Electronics"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "sector": "Technology", "industry": "Software"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "sector": "Technology", "industry": "Internet"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary", "industry": "E-commerce"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "Technology", "industry": "Social Media"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "Consumer Discretionary", "industry": "Automotive"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "sector": "Technology", "industry": "Semiconductors"},
    
    # Finance
    {"symbol": "JPM", "name": "JPMorgan Chase \u0026 Co.", "sector": "Financials", "industry": "Banking"},
    {"symbol": "BAC", "name": "Bank of America Corp.", "sector": "Financials", "industry": "Banking"},
    {"symbol": "WFC", "name": "Wells Fargo \u0026 Company", "sector": "Financials", "industry": "Banking"},
    
    # Healthcare
    {"symbol": "JNJ", "name": "Johnson \u0026 Johnson", "sector": "Healthcare", "industry": "Pharmaceuticals"},
    {"symbol": "PFE", "name": "Pfizer Inc.", "sector": "Healthcare", "industry": "Pharmaceuticals"},
    {"symbol": "UNH", "name": "UnitedHealth Group", "sector": "Healthcare", "industry": "Health Insurance"},
    
    # Consumer
    {"symbol": "KO", "name": "The Coca-Cola Company", "sector": "Consumer Staples", "industry": "Beverages"},
    {"symbol": "PEP", "name": "PepsiCo Inc.", "sector": "Consumer Staples", "industry": "Beverages"},
    {"symbol": "WMT", "name": "Walmart Inc.", "sector": "Consumer Staples", "industry": "Retail"},
    {"symbol": "HD", "name": "The Home Depot", "sector": "Consumer Discretionary", "industry": "Home Improvement"},
    
    # Industrials
    {"symbol": "BA", "name": "Boeing Company", "sector": "Industrials", "industry": "Aerospace"},
    {"symbol": "CAT", "name": "Caterpillar Inc.", "sector": "Industrials", "industry": "Machinery"},
    
    # Energy
    {"symbol": "XOM", "name": "Exxon Mobil Corporation", "sector": "Energy", "industry": "Oil \u0026 Gas"},
]

# Extra stocks for specific user comparison questions
EXTRA_COMPARISON_STOCKS = [
    {"symbol": "PETR3.SA", "name": "Petrobras ON", "sector": "Energy", "industry": "Oil & Gas", "exchange": "B3", "country": "Brazil", "currency": "BRL"},
]


def main():
    init_db()
    session = SessionLocal()
    count = 0

    try:
        # --- OMXS30 ---
        for s in OMXS30_STOCKS:
            existing = session.query(Stock).filter_by(symbol=s["symbol"], exchange="OMX").first()
            if not existing:
                stock = Stock(
                    symbol=s["symbol"], name=s["name"], exchange="OMX",
                    sector=s["sector"], industry=s.get("industry"),
                    currency="SEK", country="Sweden",
                )
                session.add(stock)
                session.flush()
                # Add to OMXS30 index
                session.add(IndexComponent(index_name="OMXS30", stock_id=stock.id))
                # Also add to OMXSPI
                session.add(IndexComponent(index_name="OMXSPI", stock_id=stock.id))
                count += 1
            else:
                # Ensure index membership exists
                if not session.query(IndexComponent).filter_by(index_name="OMXS30", stock_id=existing.id).first():
                    session.add(IndexComponent(index_name="OMXS30", stock_id=existing.id))
                if not session.query(IndexComponent).filter_by(index_name="OMXSPI", stock_id=existing.id).first():
                    session.add(IndexComponent(index_name="OMXSPI", stock_id=existing.id))

        # --- B3 ---
        for s in B3_STOCKS:
            existing = session.query(Stock).filter_by(symbol=s["symbol"], exchange="B3").first()
            if not existing:
                stock = Stock(
                    symbol=s["symbol"], name=s["name"], exchange="B3",
                    sector=s["sector"], industry=s.get("industry"),
                    currency="BRL", country="Brazil",
                )
                session.add(stock)
                session.flush()
                session.add(IndexComponent(index_name="IBOV", stock_id=stock.id))
                count += 1

        # --- US (NASDAQ/NYSE) ---
        for s in US_STOCKS:
            # Determine exchange (simplified logic)
            exchange = "NASDAQ" if s["symbol"] in ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA"] else "NYSE"
            
            existing = session.query(Stock).filter_by(symbol=s["symbol"]).first()
            if not existing:
                stock = Stock(
                    symbol=s["symbol"], name=s["name"], exchange=exchange,
                    sector=s["sector"], industry=s.get("industry"),
                    currency="USD", country="USA",
                )
                session.add(stock)
                session.flush()
                # Add to S&P 500 index (most of these are in it)
                session.add(IndexComponent(index_name="SPX", stock_id=stock.id))
                count += 1

        # --- Extra comparison stocks ---
        for s in EXTRA_COMPARISON_STOCKS:
            existing = session.query(Stock).filter_by(symbol=s["symbol"], exchange=s["exchange"]).first()
            if not existing:
                stock = Stock(**s)
                session.add(stock)
                count += 1

        session.commit()
        print(f"[STOCK LOADER] Loaded {count} new stocks")
        print(f"RECORDS_AFFECTED={count}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()


if __name__ == "__main__":
    main()
