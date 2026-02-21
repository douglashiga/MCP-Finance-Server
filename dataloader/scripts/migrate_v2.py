from dataloader.database import engine, SessionLocal
from sqlalchemy import text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def apply_schema():
    statements = [
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS track_prices BOOLEAN DEFAULT TRUE",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS track_options BOOLEAN DEFAULT FALSE",
        "ALTER TABLE stocks ADD COLUMN IF NOT EXISTS track_fundamentals BOOLEAN DEFAULT TRUE",
        """
        CREATE TABLE IF NOT EXISTS data_quality_logs (
            id SERIAL PRIMARY KEY,
            job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
            stock_id INTEGER REFERENCES stocks(id) ON DELETE CASCADE,
            run_id INTEGER REFERENCES job_runs(id) ON DELETE CASCADE,
            issue_type VARCHAR(50) NOT NULL,
            severity VARCHAR(20) DEFAULT 'warning',
            description TEXT NOT NULL,
            payload TEXT,
            created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT (now() at time zone 'utc')
        )
        """,
        "CREATE INDEX IF NOT EXISTS ix_dq_logs_job ON data_quality_logs(job_id)",
        "CREATE INDEX IF NOT EXISTS ix_dq_logs_stock ON data_quality_logs(stock_id)",
        "CREATE INDEX IF NOT EXISTS ix_dq_logs_type ON data_quality_logs(issue_type)",
        "CREATE INDEX IF NOT EXISTS ix_dq_logs_created ON data_quality_logs(created_at)"
    ]
    
    with engine.connect() as conn:
        for stmt in statements:
            try:
                conn.execute(text(stmt))
                conn.commit()
                logger.info(f"Successfully executed: {stmt[:50]}...")
            except Exception as e:
                logger.error(f"Error executing {stmt[:50]}: {e}")
                conn.rollback()

if __name__ == "__main__":
    apply_schema()
