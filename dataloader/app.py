"""
FastAPI application — REST API + static file serving for the DataLoader UI.
Run with: python -m dataloader.app
"""
import logging
import os
import secrets
import re
import csv
import io
from pathlib import Path
from datetime import datetime
from typing import Optional, Any
import asyncio

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dataloader.database import SessionLocal, init_db, engine
from dataloader.models import Job, JobRun, LLMConfig
from dataloader.scheduler import scheduler, SCRIPTS_DIR
from services.option_screener_service import OptionScreenerService

from sqlalchemy import inspect, text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="DataLoader", version="1.0.0")

API_KEY = os.environ.get("DATALOADER_API_KEY")
ALLOW_INSECURE = os.environ.get("DATALOADER_ALLOW_INSECURE", "false").lower() == "true"
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DATALOADER_ALLOWED_ORIGINS", "http://localhost:8001").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (UI)
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
os.makedirs(SCRIPTS_DIR, exist_ok=True)
SCRIPTS_DIR_PATH = Path(SCRIPTS_DIR).resolve()

IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
TYPE_RE = re.compile(r"^\s*([A-Za-z ]+?)\s*(\((\d+)(\s*,\s*(\d+))?\))?\s*$")
ALLOWED_SQL_TYPES = {
    "INTEGER",
    "BIGINT",
    "SMALLINT",
    "FLOAT",
    "REAL",
    "DOUBLE",
    "DOUBLE PRECISION",
    "NUMERIC",
    "DECIMAL",
    "TEXT",
    "VARCHAR",
    "CHAR",
    "BOOLEAN",
    "DATE",
    "DATETIME",
    "TIMESTAMP",
}


def require_admin_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")):
    """Protect administrative endpoints with API key."""
    if ALLOW_INSECURE:
        return

    if not API_KEY:
        raise HTTPException(
            status_code=503,
            detail="DATALOADER_API_KEY is not configured. Set it or enable DATALOADER_ALLOW_INSECURE=true only for development.",
        )

    if not x_api_key or not secrets.compare_digest(x_api_key, API_KEY):
        raise HTTPException(status_code=401, detail="Invalid API key")


def _validate_script_filename(filename: str) -> str:
    """
    Validate and normalize script filename.
    Reject traversal and nested paths.
    """
    if not filename:
        raise HTTPException(400, "Filename is required")

    path_obj = Path(filename)
    if path_obj.name != filename or path_obj.suffix != ".py":
        raise HTTPException(400, "Invalid filename. Only top-level .py filenames are allowed")

    if filename.startswith("."):
        raise HTTPException(400, "Hidden script names are not allowed")

    return filename


def _resolve_script_path(filename: str) -> Path:
    safe_name = _validate_script_filename(filename)
    resolved = (SCRIPTS_DIR_PATH / safe_name).resolve()
    if SCRIPTS_DIR_PATH not in resolved.parents and resolved != SCRIPTS_DIR_PATH:
        raise HTTPException(400, "Invalid script path")
    return resolved


def _validate_identifier(name: str, field_name: str = "identifier") -> str:
    if not name or not IDENTIFIER_RE.fullmatch(name):
        raise HTTPException(400, f"Invalid {field_name}. Use letters, numbers and underscore, starting with letter/underscore.")
    return name


def _quote_ident(name: str) -> str:
    return f'"{name}"'


def _normalize_sql_type(sql_type: str) -> str:
    if not sql_type:
        raise HTTPException(400, "Column type is required")

    m = TYPE_RE.fullmatch(sql_type.strip())
    if not m:
        raise HTTPException(400, f"Invalid SQL type '{sql_type}'")

    base = " ".join(m.group(1).strip().upper().split())
    if base not in ALLOWED_SQL_TYPES:
        raise HTTPException(400, f"Unsupported SQL type '{base}'")

    precision = m.group(3)
    scale = m.group(5)
    if precision:
        if scale:
            return f"{base}({precision},{scale})"
        return f"{base}({precision})"
    return base


def _sql_default_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    # Strings and everything else as quoted literals
    txt = str(value).replace("'", "''")
    return f"'{txt}'"


# ============================================================================
# Pydantic Schemas
# ============================================================================

class JobCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: Optional[str] = "general"
    script_path: str
    cron_expression: Optional[str] = None
    is_active: bool = True
    timeout_seconds: int = 300

class JobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    script_path: Optional[str] = None
    cron_expression: Optional[str] = None
    is_active: Optional[bool] = None
    timeout_seconds: Optional[int] = None

class LLMConfigCreate(BaseModel):
    provider: str
    model_name: str
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    is_active: bool = True
    is_default: bool = False

class LLMConfigUpdate(BaseModel):
    provider: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


class SchemaColumnCreate(BaseModel):
    name: str
    type: str
    nullable: bool = True
    primary_key: bool = False
    default: Optional[Any] = None


class SchemaCreateTableRequest(BaseModel):
    table_name: str
    columns: list[SchemaColumnCreate]


class SchemaAddColumnRequest(BaseModel):
    name: str
    type: str
    nullable: bool = True
    default: Optional[Any] = None


class SchemaRenameRequest(BaseModel):
    new_name: str


def _table_exists(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _column_exists(inspector, table_name: str, column_name: str) -> bool:
    cols = inspector.get_columns(table_name)
    return any(c["name"] == column_name for c in cols)


# ============================================================================
# Lifecycle
# ============================================================================

@app.on_event("startup")
async def startup():
    init_db()
    scheduler.start()
    if ALLOW_INSECURE:
        logger.warning("[SECURITY] DATALOADER_ALLOW_INSECURE=true. API key checks are disabled.")
    elif not API_KEY:
        logger.error("[SECURITY] DATALOADER_API_KEY is not set. Administrative API endpoints will reject requests.")
    logger.info("[APP] DataLoader started on http://0.0.0.0:8001")

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()


# ============================================================================
# API — Schema & Data Browser
# ============================================================================

@app.get("/api/schema")
def get_schema(_auth: None = Depends(require_admin_api_key)):
    """List all tables with columns, types, and foreign keys."""
    inspector = inspect(engine)
    tables = []
    for table_name in inspector.get_table_names():
        columns = []
        for col in inspector.get_columns(table_name):
            columns.append({
                "name": col["name"],
                "type": str(col["type"]),
                "nullable": col.get("nullable", True),
                "primary_key": col.get("primary_key", False) if "primary_key" in col else False,
            })
        
        fks = []
        for fk in inspector.get_foreign_keys(table_name):
            fks.append({
                "column": fk["constrained_columns"],
                "references": f"{fk['referred_table']}.{fk['referred_columns']}",
            })
        
        # Get row count
        with engine.connect() as conn:
            count = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"')).scalar()
        
        tables.append({
            "name": table_name,
            "columns": columns,
            "foreign_keys": fks,
            "row_count": count,
        })
    
    return {"tables": tables}


@app.post("/api/schema/tables")
def create_table(payload: SchemaCreateTableRequest, _auth: None = Depends(require_admin_api_key)):
    table_name = _validate_identifier(payload.table_name, "table_name")
    if not payload.columns:
        raise HTTPException(400, "At least one column is required")

    inspector = inspect(engine)
    if _table_exists(inspector, table_name):
        raise HTTPException(409, f"Table '{table_name}' already exists")

    seen = set()
    column_defs = []
    pk_columns = []

    for col in payload.columns:
        col_name = _validate_identifier(col.name, "column_name")
        if col_name in seen:
            raise HTTPException(400, f"Duplicate column '{col_name}'")
        seen.add(col_name)

        col_type = _normalize_sql_type(col.type)
        parts = [f'{_quote_ident(col_name)} {col_type}']
        if not col.nullable:
            parts.append("NOT NULL")
        if col.default is not None:
            parts.append(f"DEFAULT {_sql_default_literal(col.default)}")
        column_defs.append(" ".join(parts))

        if col.primary_key:
            pk_columns.append(col_name)

    if pk_columns:
        quoted_pk = ", ".join(_quote_ident(c) for c in pk_columns)
        column_defs.append(f"PRIMARY KEY ({quoted_pk})")

    sql = f'CREATE TABLE {_quote_ident(table_name)} ({", ".join(column_defs)})'
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as exc:
        logger.exception("Failed to create table %s", table_name)
        raise HTTPException(400, f"Failed to create table: {exc}")

    return {"status": "created", "table": table_name}


@app.post("/api/schema/tables/{table_name}/columns")
def add_column(table_name: str, payload: SchemaAddColumnRequest, _auth: None = Depends(require_admin_api_key)):
    safe_table = _validate_identifier(table_name, "table_name")
    column_name = _validate_identifier(payload.name, "column_name")
    column_type = _normalize_sql_type(payload.type)

    inspector = inspect(engine)
    if not _table_exists(inspector, safe_table):
        raise HTTPException(404, f"Table '{safe_table}' not found")
    if _column_exists(inspector, safe_table, column_name):
        raise HTTPException(409, f"Column '{column_name}' already exists in '{safe_table}'")

    sql = f'ALTER TABLE {_quote_ident(safe_table)} ADD COLUMN {_quote_ident(column_name)} {column_type}'
    if not payload.nullable:
        sql += " NOT NULL"
    if payload.default is not None:
        sql += f" DEFAULT {_sql_default_literal(payload.default)}"

    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as exc:
        logger.exception("Failed to add column %s to %s", column_name, safe_table)
        raise HTTPException(400, f"Failed to add column: {exc}")

    return {"status": "column_added", "table": safe_table, "column": column_name}


@app.patch("/api/schema/tables/{table_name}")
def rename_table(table_name: str, payload: SchemaRenameRequest, _auth: None = Depends(require_admin_api_key)):
    safe_table = _validate_identifier(table_name, "table_name")
    new_name = _validate_identifier(payload.new_name, "new_name")

    inspector = inspect(engine)
    if not _table_exists(inspector, safe_table):
        raise HTTPException(404, f"Table '{safe_table}' not found")
    if _table_exists(inspector, new_name):
        raise HTTPException(409, f"Table '{new_name}' already exists")

    sql = f'ALTER TABLE {_quote_ident(safe_table)} RENAME TO {_quote_ident(new_name)}'
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as exc:
        logger.exception("Failed to rename table %s to %s", safe_table, new_name)
        raise HTTPException(400, f"Failed to rename table: {exc}")

    return {"status": "renamed", "old_name": safe_table, "new_name": new_name}


@app.patch("/api/schema/tables/{table_name}/columns/{column_name}")
def rename_column(table_name: str, column_name: str, payload: SchemaRenameRequest, _auth: None = Depends(require_admin_api_key)):
    safe_table = _validate_identifier(table_name, "table_name")
    safe_column = _validate_identifier(column_name, "column_name")
    new_name = _validate_identifier(payload.new_name, "new_name")

    inspector = inspect(engine)
    if not _table_exists(inspector, safe_table):
        raise HTTPException(404, f"Table '{safe_table}' not found")
    if not _column_exists(inspector, safe_table, safe_column):
        raise HTTPException(404, f"Column '{safe_column}' not found in '{safe_table}'")
    if _column_exists(inspector, safe_table, new_name):
        raise HTTPException(409, f"Column '{new_name}' already exists in '{safe_table}'")

    sql = (
        f'ALTER TABLE {_quote_ident(safe_table)} '
        f'RENAME COLUMN {_quote_ident(safe_column)} TO {_quote_ident(new_name)}'
    )
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as exc:
        logger.exception("Failed to rename column %s.%s to %s", safe_table, safe_column, new_name)
        raise HTTPException(400, f"Failed to rename column: {exc}")

    return {
        "status": "column_renamed",
        "table": safe_table,
        "old_name": safe_column,
        "new_name": new_name,
    }


@app.delete("/api/schema/tables/{table_name}")
def delete_table(table_name: str, _auth: None = Depends(require_admin_api_key)):
    safe_table = _validate_identifier(table_name, "table_name")
    inspector = inspect(engine)
    if not _table_exists(inspector, safe_table):
        raise HTTPException(404, f"Table '{safe_table}' not found")

    sql = f'DROP TABLE {_quote_ident(safe_table)}'
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as exc:
        logger.exception("Failed to drop table %s", safe_table)
        raise HTTPException(400, f"Failed to delete table: {exc}")

    return {"status": "deleted", "table": safe_table}


@app.delete("/api/schema/tables/{table_name}/columns/{column_name}")
def delete_column(table_name: str, column_name: str, _auth: None = Depends(require_admin_api_key)):
    safe_table = _validate_identifier(table_name, "table_name")
    safe_column = _validate_identifier(column_name, "column_name")

    inspector = inspect(engine)
    if not _table_exists(inspector, safe_table):
        raise HTTPException(404, f"Table '{safe_table}' not found")
    if not _column_exists(inspector, safe_table, safe_column):
        raise HTTPException(404, f"Column '{safe_column}' not found in '{safe_table}'")

    sql = f'ALTER TABLE {_quote_ident(safe_table)} DROP COLUMN {_quote_ident(safe_column)}'
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as exc:
        logger.exception("Failed to drop column %s from %s", safe_column, safe_table)
        raise HTTPException(400, f"Failed to delete column: {exc}")

    return {"status": "column_deleted", "table": safe_table, "column": safe_column}


@app.get("/api/tables/{table_name}")
def browse_table(
    table_name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    search: str = None,
    sort_by: str = None,
    sort_order: str = Query("asc", regex="^(asc|desc)$"),
    _auth: None = Depends(require_admin_api_key),
):
    """Browse data in a table with pagination, search, and sorting."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        raise HTTPException(404, f"Table '{table_name}' not found")
    
    offset = (page - 1) * per_page
    
    with engine.connect() as conn:
        cols = [c["name"] for c in inspector.get_columns(table_name)]
        where_clause = ""
        params = {}
        if search:
            # Search across all columns by text-casting values
            conditions = " OR ".join([f'CAST("{c}" AS TEXT) LIKE :search' for c in cols])
            where_clause = f" WHERE {conditions}"
            params["search"] = f"%{search}%"

        count_q = f'SELECT COUNT(*) FROM "{table_name}"{where_clause}'
        total = conn.execute(text(count_q), params).scalar()

        order_clause = ""
        if sort_by and sort_by in cols:
            # Safe because we verified sort_by is in columns list
            order_clause = f' ORDER BY "{sort_by}" {sort_order.upper()}'

        query = (
            f'SELECT * FROM "{table_name}"{where_clause}'
            f"{order_clause} "
            f"LIMIT :limit OFFSET :offset"
        )
        rows = conn.execute(
            text(query),
            {**params, "limit": per_page, "offset": offset},
        ).fetchall()
        
        data = [dict(zip(cols, row)) for row in rows]
    
    return {
        "table": table_name,
        "columns": cols,
        "data": data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
        }
    }


@app.get("/api/tables/{table_name}/export.csv")
def export_table_csv(
    table_name: str,
    search: str = None,
    _auth: None = Depends(require_admin_api_key),
):
    """Export table data as CSV, optionally filtered by search."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        raise HTTPException(404, f"Table '{table_name}' not found")

    cols = [c["name"] for c in inspector.get_columns(table_name)]
    where_clause = ""
    params = {}
    if search:
        conditions = " OR ".join([f'CAST("{c}" AS TEXT) LIKE :search' for c in cols])
        where_clause = f" WHERE {conditions}"
        params["search"] = f"%{search}%"

    query = f'SELECT * FROM "{table_name}"{where_clause}'
    with engine.connect() as conn:
        rows = conn.execute(text(query), params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    for row in rows:
        writer.writerow(list(row))
    output.seek(0)

    filename = f"{table_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


# ============================================================================
# API — Jobs CRUD
# ============================================================================

@app.get("/api/jobs")
def list_jobs(_auth: None = Depends(require_admin_api_key)):
    """List all data loader jobs."""
    session = SessionLocal()
    try:
        jobs = session.query(Job).order_by(Job.id).all()
        result = []
        for j in jobs:
            last_run = session.query(JobRun).filter(
                JobRun.job_id == j.id
            ).order_by(JobRun.started_at.desc()).first()
            
            # Get next scheduled run
            next_run = None
            for nr in scheduler.get_next_runs():
                if nr["job_key"] == f"job_{j.id}":
                    next_run = nr["next_run"]
                    break
            
            result.append({
                "id": j.id,
                "name": j.name,
                "description": j.description,
                "category": j.category,
                "script_path": j.script_path,
                "cron_expression": j.cron_expression,
                "is_active": j.is_active,
                "timeout_seconds": j.timeout_seconds,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "last_run": {
                    "status": last_run.status,
                    "started_at": last_run.started_at.isoformat(),
                    "duration": last_run.duration_seconds
                } if last_run else None,
                "next_run": next_run,
            })
        return {"jobs": result}
    finally:
        session.close()


@app.post("/api/jobs")
def create_job(job: JobCreate, _auth: None = Depends(require_admin_api_key)):
    """Create a new data loader job."""
    session = SessionLocal()
    try:
        safe_script_name = _validate_script_filename(job.script_path)
        db_job = Job(
            name=job.name,
            description=job.description,
            category=job.category,
            script_path=safe_script_name,
            cron_expression=job.cron_expression,
            is_active=job.is_active,
            timeout_seconds=job.timeout_seconds,
        )
        session.add(db_job)
        session.commit()
        session.refresh(db_job)
        
        # Schedule if active and has cron
        if db_job.is_active and db_job.cron_expression:
            scheduler.reschedule_job(
                db_job.id, db_job.name, db_job.script_path,
                db_job.cron_expression, db_job.timeout_seconds
            )
        
        return {"id": db_job.id, "name": db_job.name, "status": "created"}
    finally:
        session.close()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, _auth: None = Depends(require_admin_api_key)):
    """Get a specific job."""
    session = SessionLocal()
    try:
        j = session.query(Job).filter(Job.id == job_id).first()
        if not j:
            raise HTTPException(404, "Job not found")
        return {
            "id": j.id, "name": j.name, "description": j.description,
            "category": j.category, "script_path": j.script_path, "cron_expression": j.cron_expression,
            "is_active": j.is_active, "timeout_seconds": j.timeout_seconds,
            "created_at": j.created_at.isoformat() if j.created_at else None,
        }
    finally:
        session.close()


@app.put("/api/jobs/{job_id}")
def update_job(job_id: int, updates: JobUpdate, _auth: None = Depends(require_admin_api_key)):
    """Update a job."""
    session = SessionLocal()
    try:
        j = session.query(Job).filter(Job.id == job_id).first()
        if not j:
            raise HTTPException(404, "Job not found")
        
        update_payload = updates.dict(exclude_unset=True)
        if "script_path" in update_payload:
            update_payload["script_path"] = _validate_script_filename(update_payload["script_path"])

        for field, value in update_payload.items():
            setattr(j, field, value)
        j.updated_at = datetime.utcnow()
        session.commit()
        
        # Re-schedule
        if j.is_active and j.cron_expression:
            scheduler.reschedule_job(j.id, j.name, j.script_path, j.cron_expression, j.timeout_seconds)
        else:
            scheduler.remove_job(j.id)
        
        return {"id": j.id, "status": "updated"}
    finally:
        session.close()


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: int, _auth: None = Depends(require_admin_api_key)):
    """Delete a job and all its runs."""
    session = SessionLocal()
    try:
        j = session.query(Job).filter(Job.id == job_id).first()
        if not j:
            raise HTTPException(404, "Job not found")
        scheduler.remove_job(j.id)
        session.delete(j)
        session.commit()
        return {"status": "deleted"}
    finally:
        session.close()


@app.post("/api/jobs/{job_id}/run")
async def trigger_job(job_id: int, _auth: None = Depends(require_admin_api_key)):
    """Manually trigger a job execution."""
    session = SessionLocal()
    try:
        j = session.query(Job).filter(Job.id == job_id).first()
        if not j:
            raise HTTPException(404, "Job not found")
    finally:
        session.close()
    
    run_id = await scheduler.trigger_job(job_id)
    return {"run_id": run_id, "status": "queued"}


@app.get("/api/queue")
def get_queue_status(_auth: None = Depends(require_admin_api_key)):
    """Get jobs currently in queue or running."""
    session = SessionLocal()
    try:
        queued_runs = session.query(JobRun, Job.name).join(Job).filter(
            JobRun.status.in_(["queued", "running"]),
            JobRun.finished_at.is_(None)
        ).order_by(JobRun.started_at.asc()).all()

        return {"queue": [{
            "id": r.JobRun.id,
            "job_id": r.JobRun.job_id,
            "job_name": r.name,
            "status": r.JobRun.status,
            "started_at": r.JobRun.started_at.isoformat(),
            "trigger": r.JobRun.trigger,
        } for r in queued_runs]}
    finally:
        session.close()


# ============================================================================
# API — Job Runs / Logs
# ============================================================================

@app.get("/api/jobs/{job_id}/runs")
def get_job_runs(job_id: int, limit: int = Query(20, ge=1, le=100), _auth: None = Depends(require_admin_api_key)):
    """Get execution history for a job."""
    session = SessionLocal()
    try:
        runs = session.query(JobRun).filter(
            JobRun.job_id == job_id
        ).order_by(JobRun.started_at.desc()).limit(limit).all()
        
        return {"runs": [{
            "id": r.id,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "exit_code": r.exit_code,
            "duration_seconds": r.duration_seconds,
            "trigger": r.trigger,
            "records_affected": r.records_affected,
            "has_stderr": bool(r.stderr and r.stderr.strip()),
        } for r in runs]}
    finally:
        session.close()


@app.get("/api/runs")
def get_all_runs(limit: int = Query(50, ge=1, le=200), _auth: None = Depends(require_admin_api_key)):
    """Get all recent runs across all jobs."""
    session = SessionLocal()
    try:
        runs = session.query(JobRun, Job.name).join(Job).order_by(
            JobRun.started_at.desc()
        ).limit(limit).all()
        
        return {"runs": [{
            "id": r.JobRun.id,
            "job_id": r.JobRun.job_id,
            "job_name": r.name,
            "started_at": r.JobRun.started_at.isoformat() if r.JobRun.started_at else None,
            "finished_at": r.JobRun.finished_at.isoformat() if r.JobRun.finished_at else None,
            "status": r.JobRun.status,
            "exit_code": r.JobRun.exit_code,
            "duration_seconds": r.JobRun.duration_seconds,
            "trigger": r.JobRun.trigger,
            "records_affected": r.JobRun.records_affected,
            "has_stderr": bool(r.JobRun.stderr and r.JobRun.stderr.strip()),
        } for r in runs]}
    finally:
        session.close()


@app.get("/api/runs/{run_id}/log")
def get_run_log(run_id: int, _auth: None = Depends(require_admin_api_key)):
    """Get full log output for a specific run."""
    session = SessionLocal()
    try:
        r = session.query(JobRun).filter(JobRun.id == run_id).first()
        if not r:
            raise HTTPException(404, "Run not found")
        return {
            "id": r.id,
            "job_id": r.job_id,
            "status": r.status,
            "stdout": r.stdout or "",
            "stderr": r.stderr or "",
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "exit_code": r.exit_code,
            "duration_seconds": r.duration_seconds,
        }
    finally:
        session.close()


@app.get("/api/runs/{run_id}/stream")
async def stream_run_log(run_id: int, _auth: None = Depends(require_admin_api_key)):
    """Stream real-time logs for a running job using SSE."""
    
    async def event_generator():
        last_stdout_len = 0
        last_stderr_len = 0
        

        while True:
            # Get live logs from memory
            live_logs = scheduler.get_live_log(run_id)
            current_stdout = live_logs["stdout"]
            current_stderr = live_logs["stderr"]
            
            # Send new chunks
            if len(current_stdout) > last_stdout_len:
                chunk = current_stdout[last_stdout_len:]
                yield f"event: stdout\ndata: {chunk}\n\n"
                last_stdout_len = len(current_stdout)
            
            if len(current_stderr) > last_stderr_len:
                chunk = current_stderr[last_stderr_len:]
                yield f"event: stderr\ndata: {chunk}\n\n"
                last_stderr_len = len(current_stderr)
            
            # Check if job is finished
            session = SessionLocal()
            run = session.query(JobRun).filter(JobRun.id == run_id).first()
            session.close()
            
            if run and run.status not in ["queued", "running"]:
                 # Send any remaining data from DB to be sure we didn't miss anything in race condition
                final_stdout = run.stdout or ""
                final_stderr = run.stderr or ""
                
                if len(final_stdout) > last_stdout_len:
                    yield f"event: stdout\ndata: {final_stdout[last_stdout_len:]}\n\n"
                
                if len(final_stderr) > last_stderr_len:
                    yield f"event: stderr\ndata: {final_stderr[last_stderr_len:]}\n\n"
                    
                yield f"event: done\ndata: {run.status}\n\n"
                break
            
            await asyncio.sleep(0.5)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ============================================================================
# API — Script Upload
# ============================================================================

@app.post("/api/scripts/upload")
async def upload_script(file: UploadFile = File(...), _auth: None = Depends(require_admin_api_key)):
    """Upload a Python script file to the scripts directory."""
    if not file.filename:
        raise HTTPException(400, "Filename is required")

    dest = _resolve_script_path(file.filename)
    with open(dest, "wb") as f:
        content = await file.read()
        f.write(content)
    
    return {"filename": dest.name, "path": dest.name, "size": len(content)}


@app.get("/api/scripts")
def list_scripts(_auth: None = Depends(require_admin_api_key)):
    """List all available scripts."""
    scripts = []
    if os.path.isdir(SCRIPTS_DIR):
        for f in sorted(os.listdir(SCRIPTS_DIR)):
            if f.endswith(".py") and not f.startswith("__"):
                full = os.path.join(SCRIPTS_DIR, f)
                scripts.append({
                    "filename": f,
                    "size": os.path.getsize(full),
                    "modified": datetime.fromtimestamp(os.path.getmtime(full)).isoformat(),
                })
    return {"scripts": scripts}


@app.get("/api/scripts/{filename}")
def get_script_content(filename: str, _auth: None = Depends(require_admin_api_key)):
    """Get the content of a script file."""
    full = _resolve_script_path(filename)
    if not full.is_file():
        raise HTTPException(404, "Script not found")
    with open(full, "r", encoding="utf-8") as f:
        content = f.read()
    return {"filename": full.name, "content": content}


# ============================================================================
# API — Dashboard Stats
# ============================================================================

@app.get("/api/stats")
def get_stats(_auth: None = Depends(require_admin_api_key)):
    """Get dashboard summary statistics."""
    session = SessionLocal()
    try:
        total_jobs = session.query(Job).count()
        active_jobs = session.query(Job).filter(Job.is_active == True).count()
        total_runs = session.query(JobRun).count()
        successful_runs = session.query(JobRun).filter(JobRun.status == "success").count()
        failed_runs = session.query(JobRun).filter(JobRun.status == "failed").count()
        
        # Data counts
        total_stocks = session.execute(text("SELECT COUNT(*) FROM stocks")).scalar()
        total_prices = session.execute(text("SELECT COUNT(*) FROM historical_prices")).scalar()
        total_dividends = session.execute(text("SELECT COUNT(*) FROM dividends")).scalar()
        total_fundamentals = session.execute(text("SELECT COUNT(*) FROM fundamentals")).scalar()
        
        # Recent failures
        recent_failures = session.query(JobRun, Job.name).join(Job).filter(
            JobRun.status == "failed"
        ).order_by(JobRun.started_at.desc()).limit(5).all()
        
        # Next scheduled runs
        next_runs = scheduler.get_next_runs()
        queue_status = scheduler.get_queue_status()
        
        return {
            "jobs": {"total": total_jobs, "active": active_jobs},
            "runs": {"total": total_runs, "success": successful_runs, "failed": failed_runs},
            "data": {
                "stocks": total_stocks,
                "prices": total_prices,
                "dividends": total_dividends,
                "fundamentals": total_fundamentals,
            },
            "recent_failures": [{
                "job_name": f.name,
                "started_at": f.JobRun.started_at.isoformat(),
                "stderr": (f.JobRun.stderr or "")[:200],
            } for f in recent_failures],
            "next_runs": next_runs[:5],
            "queue": queue_status,
        }
    finally:
        session.close()


# ============================================================================
# API — LLM Configuration
# ============================================================================

# ============================================================================
# API — Options
# ============================================================================

@app.get("/api/options/chain")
def get_option_chain(symbol: str = Query(...), expiry: str = Query(None)):
    """Get option chain for a symbol and optional expiry."""
    result = OptionScreenerService.get_option_chain_snapshot(symbol, expiry)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "Option chain not found"))
    return result


@app.get("/api/options/screener")
def get_option_screener(
    symbol: str = Query(None),
    expiry: str = Query(None),
    right: str = Query(None),
    min_delta: float = Query(None),
    max_delta: float = Query(None),
    min_iv: float = Query(None),
    max_iv: float = Query(None),
    limit: int = Query(50),
):
    """Screen options based on various criteria."""
    result = OptionScreenerService.get_option_screener(
        symbol=symbol,
        expiry=expiry,
        right=right,
        min_delta=min_delta,
        max_delta=max_delta,
        min_iv=min_iv,
        max_iv=max_iv,
        limit=limit
    )
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Option screener error"))
    return result


@app.get("/api/llm-config")
def list_llm_configs(_auth: None = Depends(require_admin_api_key)):
    session = SessionLocal()
    try:
        configs = session.query(LLMConfig).order_by(LLMConfig.id).all()
        return {"configs": [{
            "id": c.id,
            "provider": c.provider,
            "model_name": c.model_name,
            "api_base": c.api_base,
            "is_active": c.is_active,
            "is_default": c.is_default
        } for c in configs]}
    finally:
        session.close()

@app.post("/api/llm-config")
def create_llm_config(config: LLMConfigCreate, _auth: None = Depends(require_admin_api_key)):
    session = SessionLocal()
    try:
        # If set as default, unset others
        if config.is_default:
            session.query(LLMConfig).update({LLMConfig.is_default: False})
        
        new_config = LLMConfig(
            provider=config.provider,
            model_name=config.model_name,
            api_key=config.api_key,
            api_base=config.api_base,
            is_active=config.is_active,
            is_default=config.is_default
        )
        session.add(new_config)
        session.commit()
        return {"status": "created", "id": new_config.id}
    finally:
        session.close()

@app.put("/api/llm-config/{config_id}")
def update_llm_config(config_id: int, updates: LLMConfigUpdate, _auth: None = Depends(require_admin_api_key)):
    session = SessionLocal()
    try:
        config = session.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(404, "Config not found")
            
        data = updates.dict(exclude_unset=True)
        
        if data.get("is_default"):
             session.query(LLMConfig).update({LLMConfig.is_default: False})

        for k, v in data.items():
            setattr(config, k, v)
            
        config.updated_at = datetime.utcnow()
        session.commit()
        return {"status": "updated", "id": config.id}
    finally:
        session.close()

@app.delete("/api/llm-config/{config_id}")
def delete_llm_config(config_id: int, _auth: None = Depends(require_admin_api_key)):
    session = SessionLocal()
    try:
        config = session.query(LLMConfig).filter(LLMConfig.id == config_id).first()
        if not config:
            raise HTTPException(404, "Config not found")
        
        session.delete(config)
        session.commit()
        return {"status": "deleted"}
    finally:
        session.close()


# ============================================================================
# Static Files — Serve UI
# ============================================================================

# Assets mount point (React bundle)
app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")



@app.get("/api/options/avanza/expirations")
def get_avanza_expirations(symbol: str = Query(...)):
    """Get available expiration dates for a symbol from local DB (Avanza data)."""
    session = SessionLocal()
    try:
        stock = session.query(Stock).filter(Stock.symbol.ilike(f"%{symbol}%")).first()
        if not stock:
            raise HTTPException(404, f"Stock {symbol} not found")
        
        # Get unique expiries
        expiries = session.query(OptionMetric.expiry).filter(
            OptionMetric.stock_id == stock.id
        ).distinct().order_by(OptionMetric.expiry.asc()).all()
        
        return {"success": True, "expirations": [str(e[0]) for e in expiries]}
    finally:
        session.close()

@app.get("/api/options/avanza/chain")
def get_avanza_chain(symbol: str = Query(...), expiry: str = Query(None)):
    """Get Avanza-style option chain (grouped by strike)."""
    result = OptionScreenerService.get_option_chain_snapshot(symbol, expiry)
    if not result.get("success"):
        raise HTTPException(404, result.get("error", "Option chain not found"))
    
    # Group by strike for the Avanza layout (CALL | Strike | PUT)
    data = result["data"]
    grouped = {}
    for row in data:
        strike = row["strike"]
        if strike not in grouped:
            grouped[strike] = {"strike": strike, "call": None, "put": None}
        
        if row["right"] == "CALL":
            grouped[strike]["call"] = row
        else:
            grouped[strike]["put"] = row
            
    # Convert to sorted list
    rows = sorted(grouped.values(), key=lambda x: x["strike"])
    
    return {
        "success": True,
        "symbol": result["symbol"],
        "expiry": expiry,
        "rows": rows,
        "as_of": result.get("as_of_datetime")
    }


@app.get("/{full_path:path}")
async def serve_ui(full_path: str):
    """Serve the React UI or fallback to index.html for SPA routing."""
    # Catch-all for API to avoid serving index.html on missing endpoints
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
        
    # Check if file exists in static dir
    file_path = os.path.join(STATIC_DIR, full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
        
    # Default to index.html for SPA
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return HTMLResponse("<h1>DataLoader</h1><p>UI not found. Place index.html in dataloader/static/</p>")





# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
