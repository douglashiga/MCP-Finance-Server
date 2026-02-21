import logging
import json
from datetime import datetime
from typing import Optional, Any, Dict
from dataloader.database import SessionLocal
from dataloader.models import DataQualityLog

logger = logging.getLogger(__name__)

class DataQualityService:
    @staticmethod
    def log_issue(
        job_id: int, 
        issue_type: str, 
        description: str, 
        stock_id: Optional[int] = None, 
        run_id: Optional[int] = None,
        severity: str = "warning",
        payload: Optional[Any] = None
    ):
        """Log a data quality issue to the database."""
        session = SessionLocal()
        try:
            # Convert payload to JSON string if it's not a string already
            payload_str = None
            if payload is not None:
                if isinstance(payload, (dict, list)):
                    payload_str = json.dumps(payload, default=str)
                else:
                    payload_str = str(payload)

            log_entry = DataQualityLog(
                job_id=job_id,
                stock_id=stock_id,
                run_id=run_id,
                issue_type=issue_type,
                severity=severity,
                description=description,
                payload=payload_str,
                created_at=datetime.utcnow()
            )
            session.add(log_entry)
            session.commit()
            
            log_msg = f"[DQ][{severity.upper()}] Job {job_id} | Stock {stock_id} | {issue_type}: {description}"
            if severity == "critical":
                logger.error(log_msg)
            elif severity == "error":
                logger.error(log_msg)
            else:
                logger.warning(log_msg)
                
        except Exception as e:
            logger.error(f"Failed to log Data Quality issue: {e}")
            session.rollback()
        finally:
            session.close()

    @staticmethod
    def get_recent_issues(limit: int = 50):
        """Get the most recent data quality issues."""
        session = SessionLocal()
        try:
            from dataloader.models import Job, Stock
            query = session.query(DataQualityLog).order_by(DataQualityLog.created_at.desc())
            results = query.limit(limit).all()
            
            data = []
            for log in results:
                data.append({
                    "id": log.id,
                    "job_name": log.job.name if log.job else "Unknown",
                    "ticker": log.stock.symbol if log.stock else None,
                    "issue_type": log.issue_type,
                    "severity": log.severity,
                    "description": log.description,
                    "created_at": log.created_at.isoformat(),
                    "payload": log.payload
                })
            return data
        finally:
            session.close()
