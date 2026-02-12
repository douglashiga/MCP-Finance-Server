"""
Job Management Service — Allows LLM to query, trigger, and monitor
data loader jobs via MCP tools.
"""
import logging
import subprocess
import os
from datetime import datetime
from dataloader.database import SessionLocal
from dataloader.models import Job, JobRun

logger = logging.getLogger(__name__)

SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dataloader", "scripts")


class JobService:

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
            job = session.query(Job).filter(
                Job.name.ilike(f"%{job_name}%")
            ).first()

            if not job:
                return {"success": False, "error": f"Job '{job_name}' not found"}

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
    def trigger_job(job_name: str):
        """Manually trigger a job execution."""
        session = SessionLocal()
        try:
            job = session.query(Job).filter(
                Job.name.ilike(f"%{job_name}%")
            ).first()

            if not job:
                return {"success": False, "error": f"Job '{job_name}' not found"}

            script_path = os.path.join(SCRIPTS_DIR, job.script_path)
            if not os.path.exists(script_path):
                return {"success": False, "error": f"Script not found: {job.script_path}"}

            # Create job run record
            run = JobRun(
                job_id=job.id,
                started_at=datetime.utcnow(),
                status="running",
                trigger="manual",
            )
            session.add(run)
            session.commit()
            run_id = run.id

            # Execute script in background
            try:
                result = subprocess.run(
                    ["python", script_path],
                    capture_output=True,
                    text=True,
                    timeout=job.timeout_seconds or 300,
                    cwd=os.path.dirname(SCRIPTS_DIR),
                )

                finished_at = datetime.utcnow()
                duration = (finished_at - run.started_at).total_seconds()

                run.finished_at = finished_at
                run.duration_seconds = duration
                run.exit_code = result.returncode
                run.stdout = result.stdout
                run.stderr = result.stderr
                run.status = "success" if result.returncode == 0 else "failed"

                # Parse records affected
                for line in (result.stdout or "").split("\n"):
                    if line.startswith("RECORDS_AFFECTED="):
                        run.records_affected = int(line.split("=")[1])

                session.commit()

                return {
                    "success": True,
                    "job_name": job.name,
                    "run_id": run_id,
                    "status": run.status,
                    "duration_seconds": duration,
                    "records_affected": run.records_affected,
                    "stdout": result.stdout[-500:] if result.stdout else None,
                    "stderr": result.stderr[-500:] if result.stderr else None,
                }

            except subprocess.TimeoutExpired:
                run.status = "timeout"
                run.finished_at = datetime.utcnow()
                session.commit()
                return {"success": False, "error": f"Job timed out after {job.timeout_seconds}s"}

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
            job = session.query(Job).filter(
                Job.name.ilike(f"%{job_name}%")
            ).first()

            if not job:
                return {"success": False, "error": f"Job '{job_name}' not found"}

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
    def run_pipeline_health_check():
        """Manually trigger the pipeline health check runner."""
        return JobService.trigger_job("Pipeline Health Check")
