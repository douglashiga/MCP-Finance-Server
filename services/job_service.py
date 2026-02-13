"""
Job Management Service — Allows LLM to query, trigger, and monitor
data loader jobs via MCP tools.
"""
import logging
import os
import shlex
from sqlalchemy import func
from dataloader.database import SessionLocal
from dataloader.models import Job, JobRun
from dataloader.scheduler import scheduler, SCRIPTS_DIR

logger = logging.getLogger(__name__)


class JobService:
    @staticmethod
    def _find_job(session, job_name: str):
        """
        Resolve job by name.
        Priority: exact case-insensitive match, then unique partial match.
        """
        exact = session.query(Job).filter(
            func.lower(Job.name) == job_name.lower()
        ).first()
        if exact:
            return exact, None

        partial_matches = session.query(Job).filter(
            Job.name.ilike(f"%{job_name}%")
        ).order_by(Job.name.asc()).limit(5).all()

        if not partial_matches:
            return None, f"Job '{job_name}' not found"

        if len(partial_matches) > 1:
            names = ", ".join(m.name for m in partial_matches[:3])
            return None, f"Ambiguous job name '{job_name}'. Matches: {names}"

        return partial_matches[0], None

    @staticmethod
    def list_jobs():
        """List all registered jobs with status and schedule."""
        session = SessionLocal()
        try:
            jobs = session.query(Job).all()
            data = []
            for job in jobs:
                last_run = session.query(JobRun).filter_by(
                    job_id=job.id
                ).order_by(JobRun.started_at.desc()).first()

                data.append({
                    "id": job.id,
                    "name": job.name,
                    "description": job.description,
                    "script": job.script_path,
                    "cron": job.cron_expression,
                    "is_active": job.is_active,
                    "affected_tables": job.affected_tables,
                    "last_run": {
                        "status": last_run.status if last_run else None,
                        "started_at": str(last_run.started_at) if last_run else None,
                        "duration": last_run.duration_seconds if last_run else None,
                        "records": last_run.records_affected if last_run else None,
                    } if last_run else None,
                })

            return {"success": True, "data": data, "count": len(data)}
        except Exception as e:
            logger.error(f"List jobs error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_job_logs(job_name: str, limit: int = 5):
        """Get recent run logs for a specific job."""
        session = SessionLocal()
        try:
            job, error = JobService._find_job(session, job_name)

            if not job:
                return {"success": False, "error": error}

            runs = session.query(JobRun).filter_by(
                job_id=job.id
            ).order_by(JobRun.started_at.desc()).limit(limit).all()

            data = []
            for run in runs:
                data.append({
                    "id": run.id,
                    "status": run.status,
                    "started_at": str(run.started_at),
                    "finished_at": str(run.finished_at) if run.finished_at else None,
                    "duration_seconds": run.duration_seconds,
                    "records_affected": run.records_affected,
                    "trigger": run.trigger,
                    "stdout": run.stdout[-500:] if run.stdout else None,
                    "stderr": run.stderr[-500:] if run.stderr else None,
                })

            return {
                "success": True,
                "job_name": job.name,
                "data": data,
                "count": len(data),
            }
        except Exception as e:
            logger.error(f"Job logs error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    async def trigger_job(job_name: str):
        """Manually trigger a job execution."""
        session = SessionLocal()
        try:
            job, error = JobService._find_job(session, job_name)

            if not job:
                return {"success": False, "error": error}

            command_parts = shlex.split(job.script_path)
            if not command_parts:
                return {"success": False, "error": f"Invalid script path for job '{job.name}'"}
            script_file = command_parts[0]
            script_path = os.path.join(SCRIPTS_DIR, script_file)
            if not os.path.exists(script_path):
                return {"success": False, "error": f"Script not found: {job.script_path}"}

            run_id = await scheduler.trigger_job(job.id)
            if run_id is None:
                return {"success": False, "error": f"Unable to trigger job '{job.name}'"}

            run = session.query(JobRun).filter(JobRun.id == run_id).first()
            if not run:
                return {"success": False, "error": f"Run {run_id} not found after execution"}

            return {
                "success": True,
                "job_name": job.name,
                "run_id": run_id,
                "status": run.status,
                "duration_seconds": run.duration_seconds,
                "records_affected": run.records_affected,
                "stdout": run.stdout[-500:] if run.stdout else None,
                "stderr": run.stderr[-500:] if run.stderr else None,
            }

        except Exception as e:
            logger.error(f"Trigger job error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def toggle_job(job_name: str, active: bool):
        """Enable or disable a job."""
        session = SessionLocal()
        try:
            job, error = JobService._find_job(session, job_name)

            if not job:
                return {"success": False, "error": error}

            job.is_active = active
            session.commit()

            return {
                "success": True,
                "job_name": job.name,
                "is_active": active,
                "message": f"Job '{job.name}' {'enabled' if active else 'disabled'}",
            }
        except Exception as e:
            logger.error(f"Toggle job error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    def get_job_status():
        """Get overview of all jobs with health status."""
        session = SessionLocal()
        try:
            jobs = session.query(Job).all()
            healthy = 0
            warning = 0
            error = 0

            details = []
            for job in jobs:
                last_run = session.query(JobRun).filter_by(
                    job_id=job.id
                ).order_by(JobRun.started_at.desc()).first()

                status = "no_runs"
                if last_run:
                    status = last_run.status

                if status == "success":
                    healthy += 1
                elif status == "failed" or status == "timeout":
                    error += 1
                else:
                    warning += 1

                details.append({
                    "name": job.name,
                    "active": job.is_active,
                    "cron": job.cron_expression,
                    "last_status": status,
                    "last_run": str(last_run.started_at) if last_run else "never",
                })

            return {
                "success": True,
                "summary": {
                    "total": len(jobs),
                    "healthy": healthy,
                    "warning": warning,
                    "error": error,
                },
                "jobs": details,
            }
        except Exception as e:
            logger.error(f"Job status error: {e}")
            return {"success": False, "error": str(e)}
        finally:
            session.close()

    @staticmethod
    async def run_pipeline_health_check():
        """Manually trigger the pipeline health check runner."""
        return await JobService.trigger_job("Pipeline Health Check")
