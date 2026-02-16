
from dataloader.database import SessionLocal
from dataloader.models import Stock, SectorTaxonomy, IndustryTaxonomy, RawYahooFundamental, RawIBKRContract

def check_counts():
    session = SessionLocal()
    try:
        n_stocks = session.query(Stock).count()
        n_sectors = session.query(SectorTaxonomy).count()
        n_industries = session.query(IndustryTaxonomy).count()
        n_yahoo = session.query(RawYahooFundamental).count()
        n_ibkr = session.query(RawIBKRContract).count()
        
        print(f"Stocks: {n_stocks}")
        print(f"SectorTaxonomy: {n_sectors}")
        print(f"IndustryTaxonomy: {n_industries}")
        print(f"RawYahooFundamental: {n_yahoo}")
        print(f"RawIBKRContract: {n_ibkr}")
        
        if n_stocks > 0:
            first_stock = session.query(Stock).first()
            print(f"First Stock: {first_stock.symbol} Sector: {first_stock.sector} Industry: {first_stock.industry}")
            
    finally:
        session.close()

if __name__ == "__main__":
    check_counts()
