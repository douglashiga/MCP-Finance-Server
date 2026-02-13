"""
Job scheduler — runs data loader Python scripts on cron schedules.
Uses APScheduler with a SQLite job store for persistence.
"""
import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from typing import Optional, Dict, Any

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
        self._job_queue: asyncio.Queue[Optional[Dict[str, Any]]] = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None

    def start(self):
        """Start the scheduler and load active jobs from the database."""
        self.scheduler.start()
        self._recover_stuck_runs()
        self._load_jobs_from_db()
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._queue_worker())
        logger.info("[SCHEDULER] Started with %d jobs", len(self.scheduler.get_jobs()))

    def shutdown(self):
        """Gracefully shut down the scheduler."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
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

    def _recover_stuck_runs(self):
        """
        On scheduler startup, close orphan queued/running runs left by crashes/restarts.
        This prevents permanent deduplication locks.
        """
        session = SessionLocal()
        try:
            stale_runs = session.query(JobRun).filter(
                JobRun.status.in_(["queued", "running"]),
                JobRun.finished_at.is_(None),
            ).all()

            now = datetime.utcnow()
            for run in stale_runs:
                run.status = "failed"
                run.finished_at = now
                existing_stderr = run.stderr or ""
                suffix = "Recovered as failed on scheduler startup"
                run.stderr = f"{existing_stderr}\n{suffix}".strip()

            if stale_runs:
                session.commit()
                logger.warning("[SCHEDULER] Recovered %d stale queued/running runs", len(stale_runs))
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
                self._enqueue_scheduled_job,
                trigger=trigger,
                id=job_key,
                name=name,
                args=[job_id, script_path, timeout],
                replace_existing=True,
                misfire_grace_time=60,
                coalesce=True,
                max_instances=1,
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
        """Manually enqueue a job. Returns the queued run_id."""
        session = SessionLocal()
        try:
            job = session.query(Job).filter(Job.id == job_id).first()
            if not job:
                return None
            script_path = job.script_path
            timeout = job.timeout_seconds
        finally:
            session.close()

        return await self._enqueue_job(job_id, script_path, timeout, trigger="manual")

    async def _enqueue_scheduled_job(self, job_id: int, script_path: str, timeout: int = 300):
        """APScheduler callback: enqueue cron job for sequential execution."""
        await self._enqueue_job(job_id, script_path, timeout, trigger="cron")

    async def _enqueue_job(self, job_id: int, script_path: str, timeout: int = 300, trigger: str = "manual") -> int:
        """Create queued run and push it to the single-worker queue."""
        session = SessionLocal()
        try:
            existing = session.query(JobRun).filter(
                JobRun.job_id == job_id,
                JobRun.status.in_(["queued", "running"]),
                JobRun.finished_at.is_(None),
            ).order_by(JobRun.started_at.desc()).first()
            if existing:
                logger.info(
                    "[SCHEDULER] Skip enqueue for job %s (%s already %s)",
                    job_id, existing.id, existing.status
                )
                return existing.id

            run = JobRun(
                job_id=job_id,
                started_at=datetime.utcnow(),
                status="queued",
                trigger=trigger,
            )
            session.add(run)
            session.commit()
            run_id = run.id

            await self._job_queue.put({
                "run_id": run_id,
                "job_id": job_id,
                "script_path": script_path,
                "timeout": timeout,
                "trigger": trigger,
            })
            logger.info(
                "[SCHEDULER] Queued job %s (run_id=%s, trigger=%s, queue_size=%s)",
                job_id, run_id, trigger, self._job_queue.qsize(),
            )
            return run_id

        except Exception as e:
            logger.error(f"[SCHEDULER] Failed to enqueue job {job_id}: {e}")
            raise
        finally:
            session.close()

    async def _queue_worker(self):
        """Single worker that executes queued jobs sequentially."""
        logger.info("[SCHEDULER] Queue worker started")
        while True:
            item = await self._job_queue.get()
            if item is None:
                self._job_queue.task_done()
                break

            try:
                await self._run_job_item(item)
            except Exception as e:
                logger.error(f"[SCHEDULER] Queue worker item failed: {e}")
            finally:
                self._job_queue.task_done()

    async def _run_job_item(self, item: Dict[str, Any]):
        """Execute one queued item and persist final status."""
        run_id = item["run_id"]
        job_id = item["job_id"]
        script_path = item["script_path"]
        timeout = item["timeout"]

        session = SessionLocal()
        try:
            run = session.query(JobRun).filter(JobRun.id == run_id).first()
            if not run:
                logger.error("[SCHEDULER] Run %s not found before execution", run_id)
                return
            run.status = "running"
            run.started_at = datetime.utcnow()
            session.commit()
        finally:
            session.close()

        # Parse command and arguments
        import shlex
        parts = shlex.split(script_path)
        script_file = parts[0]
        script_args = parts[1:]

        # Resolve full script path
        if not os.path.isabs(script_file):
            full_path = os.path.join(SCRIPTS_DIR, script_file)
        else:
            full_path = script_file

        logger.info(f"[SCHEDULER] Executing job {job_id}: {full_path} {' '.join(script_args)}")

        start_time = time.time()
        status = "failed"
        exit_code = -1
        stdout_text = ""
        stderr_text = ""
        records_affected = None

        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, full_path, *script_args,
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
                stderr_bytes = f"Job timed out after {timeout} seconds".encode("utf-8")
                exit_code = -1
                status = "timeout"

            stdout_text = stdout_bytes.decode("utf-8", errors="replace")[-50000:]  # Last 50KB
            stderr_text = stderr_bytes.decode("utf-8", errors="replace")[-50000:]

            for line in stdout_text.splitlines():
                if line.startswith("RECORDS_AFFECTED="):
                    try:
                        records_affected = int(line.split("=")[1])
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            stderr_text = str(e)
            status = "failed"
            logger.error(f"[SCHEDULER] Job {job_id} runtime error: {e}")
        finally:
            duration = time.time() - start_time
            session = SessionLocal()
            try:
                run = session.query(JobRun).filter(JobRun.id == run_id).first()
                if run:
                    run.finished_at = datetime.utcnow()
                    run.status = status
                    run.exit_code = exit_code
                    run.stdout = stdout_text
                    run.stderr = stderr_text
                    run.duration_seconds = round(duration, 2)
                    run.records_affected = records_affected
                    session.commit()
            finally:
                session.close()

            logger.info(f"[SCHEDULER] Job {job_id} finished: status={status}, duration={duration:.1f}s")

    def get_queue_status(self) -> dict:
        """Queue runtime status for UI/diagnostics."""
        active_run = None
        session = SessionLocal()
        try:
            running = session.query(JobRun).filter(
                JobRun.status == "running",
                JobRun.finished_at.is_(None),
            ).order_by(JobRun.started_at.desc()).first()
            if running:
                active_run = {"run_id": running.id, "job_id": running.job_id}
        finally:
            session.close()

        return {
            "queue_size": self._job_queue.qsize(),
            "worker_alive": bool(self._worker_task and not self._worker_task.done()),
            "active_run": active_run,
        }

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
