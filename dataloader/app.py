"""
FastAPI application — REST API + static file serving for the DataLoader UI.
Run with: python -m dataloader.app
"""
import logging
import os
import secrets
from pathlib import Path
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from dataloader.database import SessionLocal, init_db, engine
from dataloader.models import Job, JobRun
from dataloader.scheduler import scheduler, SCRIPTS_DIR

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


# ============================================================================
# Pydantic Schemas
# ============================================================================

class JobCreate(BaseModel):
    name: str
    description: Optional[str] = None
    script_path: str
    cron_expression: Optional[str] = None
    is_active: bool = True
    timeout_seconds: int = 300

class JobUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    script_path: Optional[str] = None
    cron_expression: Optional[str] = None
    is_active: Optional[bool] = None
    timeout_seconds: Optional[int] = None


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


@app.get("/api/tables/{table_name}")
def browse_table(
    table_name: str,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=500),
    search: str = None,
    _auth: None = Depends(require_admin_api_key),
):
    """Browse data in a table with pagination and optional search."""
    inspector = inspect(engine)
    if table_name not in inspector.get_table_names():
        raise HTTPException(404, f"Table '{table_name}' not found")
    
    offset = (page - 1) * per_page
    
    with engine.connect() as conn:
        # Get total count
        count_q = f'SELECT COUNT(*) FROM "{table_name}"'
        total = conn.execute(text(count_q)).scalar()
        
        # Get column names
        cols = [c["name"] for c in inspector.get_columns(table_name)]
        
        # Build query
        query = f'SELECT * FROM "{table_name}"'
        if search:
            # Search across text columns
            text_cols = [c["name"] for c in inspector.get_columns(table_name)
                        if "CHAR" in str(c["type"]).upper() or "TEXT" in str(c["type"]).upper()]
            if text_cols:
                conditions = " OR ".join([f'"{c}" LIKE :search' for c in text_cols])
                query += f" WHERE {conditions}"
        
        query += f" LIMIT {per_page} OFFSET {offset}"
        
        if search:
            rows = conn.execute(text(query), {"search": f"%{search}%"}).fetchall()
        else:
            rows = conn.execute(text(query)).fetchall()
        
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
            "script_path": j.script_path, "cron_expression": j.cron_expression,
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
    return {"run_id": run_id, "status": "executed"}


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
        }
    finally:
        session.close()


# ============================================================================
# Static Files — Serve UI
# ============================================================================

# Assets mount point (React bundle)
app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")), name="assets")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


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
