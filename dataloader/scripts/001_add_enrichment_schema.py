"""
Migration script to add:
1. `llm_configs` table.
2. `category` column to `jobs` table (if missing).
"""
import logging
from sqlalchemy import text, inspect
from dataloader.database import engine
from dataloader.models import LLMConfig, Base

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    inspector = inspect(engine)
    
    # 1. Create llm_configs table if not exists
    if "llm_configs" not in inspector.get_table_names():
        logger.info("Creating table 'llm_configs'...")
        LLMConfig.__table__.create(engine)
        logger.info("Table 'llm_configs' created.")
    else:
        logger.info("Table 'llm_configs' already exists.")

    # 2. Add 'category' column to 'jobs' table if not exists
    jobs_columns = [col["name"] for col in inspector.get_columns("jobs")]
    if "category" not in jobs_columns:
        logger.info("Adding column 'category' to table 'jobs'...")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN category VARCHAR(50) DEFAULT 'general'"))
        logger.info("Column 'category' added.")
    else:
        logger.info("Column 'category' already exists in 'jobs'.")

if __name__ == "__main__":
    try:
        migrate()
        logger.info("Migration completed successfully.")
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        exit(1)
