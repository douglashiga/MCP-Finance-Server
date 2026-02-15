#!/usr/bin/env python3
"""
Load US Stocks (ELT Extractor)
Source: ftp.nasdaqtrader.com (nasdaqlisted.txt, otherlisted.txt)
"""
import sys
import os
import json
import ftplib
import io
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal, init_db
from dataloader.models import RawUSStock

FTP_HOST = "ftp.nasdaqtrader.com"
FTP_DIR = "SymbolDirectory"
FILES = {
    "nasdaq": "nasdaqlisted.txt",
    "other": "otherlisted.txt"
}

def fetch_ftp_file(filename):
    """Download a file from Nasdaq FTP into memory."""
    print(f"[LOADER-US] Downloading {filename} from {FTP_HOST}...")
    try:
        ftp = ftplib.FTP(FTP_HOST)
        ftp.login()
        ftp.cwd(FTP_DIR)
        
        bio = io.BytesIO()
        ftp.retrbinary(f"RETR {filename}", bio.write)
        ftp.quit()
        
        bio.seek(0)
        return bio.read().decode("utf-8")
    except Exception as e:
        print(f"[ERROR] Failed to download {filename}: {e}")
        return None

def parse_txt_data(content, source_type):
    """Parse pipe-delimited data from Nasdaq FTP."""
    lines = content.splitlines()
    if not lines:
        return []
        
    # Header usually: Symbol|Security Name|...
    header = lines[0].split("|")
    # Last line is usually file creation time: File Creation Time: ...
    data_lines = lines[1:-1] 
    
    parsed = []
    for line in data_lines:
        parts = line.split("|")
        if len(parts) < 2:
            continue
            
        # Create a dict based on header (if lengths match, else manual)
        # Usually reliable.
        row_dict = {}
        for i, val in enumerate(parts):
            if i < len(header):
                row_dict[header[i]] = val
        
        symbol = row_dict.get("Symbol") or row_dict.get("ACT Symbol") # ACT Symbol in otherlisted?
        if not symbol:
            continue
            
        parsed.append({
            "symbol": symbol,
            "source": source_type,
            "data": row_dict
        })
    return parsed

def main():
    init_db()
    session = SessionLocal()
    
    count_new = 0
    count_updated = 0
    
    try:
        # 1. NASDAQ
        content_nasdaq = fetch_ftp_file(FILES["nasdaq"])
        if content_nasdaq:
            rows = parse_txt_data(content_nasdaq, "NASDAQ")
            print(f"[LOADER-US] Processing {len(rows)} NASDAQ records...")
            for row in rows:
                json_str = json.dumps(row["data"])
                sym = row["symbol"]
                
                existing = session.query(RawUSStock).filter_by(symbol=sym).first()
                if not existing:
                    session.add(RawUSStock(symbol=sym, source="NASDAQ", data=json_str, fetched_at=datetime.now(timezone.utc)))
                    count_new += 1
                else:
                    existing.data = json_str
                    existing.source = "NASDAQ" 
                    existing.fetched_at = datetime.now(timezone.utc)
                    count_updated += 1
        
        # 2. OTHER (NYSE, AMEX, etc)
        content_other = fetch_ftp_file(FILES["other"])
        if content_other:
            rows = parse_txt_data(content_other, "OTHER")
            print(f"[LOADER-US] Processing {len(rows)} OTHER records...")
            for row in rows:
                json_str = json.dumps(row["data"])
                sym = row["symbol"]
                
                existing = session.query(RawUSStock).filter_by(symbol=sym).first()
                if not existing:
                    session.add(RawUSStock(symbol=sym, source="OTHER", data=json_str, fetched_at=datetime.now(timezone.utc)))
                    count_new += 1
                else:
                    existing.data = json_str
                    existing.source = "OTHER"
                    existing.fetched_at = datetime.now(timezone.utc)
                    count_updated += 1

        session.commit()
        print(f"[LOADER-US] Finished. New: {count_new}, Updated: {count_updated}")
        print(f"RECORDS_AFFECTED={count_new + count_updated}")

    except Exception as e:
        session.rollback()
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        session.close()

if __name__ == "__main__":
    main()
