"""
Job scheduler — runs data loader Python scripts on cron schedules.
Uses APScheduler with a SQLite job store for persistence.
"""
import asyncio
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from dataloader.database import SessionLocal
from dataloader.models import Job, JobRun

logger = logging.getLogger(__name__)

# Base dir for scripts
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")


class JobScheduler:
    """Manages scheduled execution of data loader scripts."""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self._running_processes: dict[int, subprocess.Popen] = {}

    def start(self):
        """Start the scheduler and load active jobs from the database."""
        self.scheduler.start()
        self._load_jobs_from_db()
        logger.info("[SCHEDULER] Started with %d jobs", len(self.scheduler.get_jobs()))

    def shutdown(self):
        """Gracefully shut down the scheduler."""
        self.scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Shutdown complete")

    def _load_jobs_from_db(self):
        """Load all active jobs from DB and schedule them."""
        session = SessionLocal()
        try:
            jobs = session.query(Job).filter(Job.is_active == True).all()
            for job in jobs:
                if job.cron_expression:
                    self._add_job(job.id, job.name, job.script_path, job.cron_expression, job.timeout_seconds)
        finally:
            session.close()

    def _add_job(self, job_id: int, name: str, script_path: str, cron_expr: str, timeout: int = 300):
        """Add or replace a scheduled job."""
        job_key = f"job_{job_id}"

        # Remove existing job if any
        existing = self.scheduler.get_job(job_key)
        if existing:
            self.scheduler.remove_job(job_key)

        try:
            trigger = CronTrigger.from_crontab(cron_expr)
            self.scheduler.add_job(
                self._execute_job,
                trigger=trigger,
                id=job_key,
                name=name,
                args=[job_id, script_path, timeout],
                replace_existing=True,
                misfire_grace_time=60,
            )
            logger.info(f"[SCHEDULER] Registered job '{name}' (cron={cron_expr})")
        except Exception as e:
            logger.error(f"[SCHEDULER] Failed to register job '{name}': {e}")

    def remove_job(self, job_id: int):
        """Remove a job from the scheduler."""
        job_key = f"job_{job_id}"
        existing = self.scheduler.get_job(job_key)
        if existing:
            self.scheduler.remove_job(job_key)
            logger.info(f"[SCHEDULER] Removed job {job_id}")

    def reschedule_job(self, job_id: int, name: str, script_path: str, cron_expr: str, timeout: int = 300):
        """Update a job's schedule."""
        self._add_job(job_id, name, script_path, cron_expr, timeout)

    async def trigger_job(self, job_id: int) -> Optional[int]:
        """Manually trigger a job. Returns the run_id."""
        session = SessionLocal()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            script_path = job.script_path
            timeout = job.timeout_seconds
        finally:
            session.close()

        run_id = await self._execute_job(job_id, script_path, timeout, trigger="manual")
        return run_id

    async def _execute_job(self, job_id: int, script_path: str, timeout: int = 300, trigger: str = "cron") -> int:
        """Execute a Python script and record the results."""
        session = SessionLocal()
        run = JobRun(
            job_id=job_id,
            started_at=datetime.utcnow(),
            status="running",
            trigger=trigger,
        )
        session.add(run)
        session.commit()
        run_id = run.id

        # Resolve full script path
        full_path = os.path.join(SCRIPTS_DIR, script_path)
        if not os.path.isabs(script_path):
            full_path = os.path.join(SCRIPTS_DIR, script_path)
        else:
            full_path = script_path

        logger.info(f"[SCHEDULER] Executing job {job_id}: {full_path}")

        start_time = time.time()
        try:
            # Run the script as a subprocess
            process = await asyncio.create_subprocess_exec(
                sys.executable, full_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),  # Project root
                env={**os.environ, "PYTHONPATH": os.path.dirname(os.path.dirname(os.path.abspath(__file__)))},
            )

            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )
                exit_code = process.returncode
                status = "success" if exit_code == 0 else "failed"
            except asyncio.TimeoutError:
                process.kill()
                await process.communicate()
                stdout_bytes = b""
                stderr_bytes = b"Job timed out after {timeout} seconds"
                exit_code = -1
                status = "timeout"

            duration = time.time() - start_time
            stdout_text = stdout_bytes.decode("utf-8", errors="replace")[-50000:]  # Last 50KB
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")[-50000:]

            # Parse records_affected from stdout if present
            records_affected = None
            for line in stdout_text.splitlines():
                if line.startswith("RECORDS_AFFECTED="):
                    try:
                        records_affected = int(line.split("=")[1])
                    except (ValueError, IndexError):
                        pass

            # Update the run record
            run = session.query(JobRun).filter(JobRun.id == run_id).first()
            run.finished_at = datetime.utcnow()
            run.status = status
            run.exit_code = exit_code
            run.stdout = stdout_text
            run.stderr = stderr_text
            run.duration_seconds = round(duration, 2)
            run.records_affected = records_affected
            session.commit()

            logger.info(f"[SCHEDULER] Job {job_id} finished: status={status}, duration={duration:.1f}s")

        except Exception as e:
            duration = time.time() - start_time
            run = session.query(JobRun).filter(JobRun.id == run_id).first()
            run.finished_at = datetime.utcnow()
            run.status = "failed"
            run.stderr = str(e)
            run.duration_seconds = round(duration, 2)
            session.commit()
            logger.error(f"[SCHEDULER] Job {job_id} error: {e}")
        finally:
            session.close()

        return run_id

    def get_next_runs(self) -> list[dict]:
        """Get upcoming scheduled runs."""
        result = []
        for job in self.scheduler.get_jobs():
            next_run = job.next_run_time
            result.append({
                "job_key": job.id,
                "name": job.name,
                "next_run": next_run.isoformat() if next_run else None,
            })
        return result


# Global instance
scheduler = JobScheduler()
