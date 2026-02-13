#!/usr/bin/env python3
"""
Pipeline Health Check — Runs lightweight tests for all registered jobs.
Iterates through the 'jobs' table and executes scripts with the --test flag.
Records results in the 'job_runs' table with status 'success' or 'failed'.
"""
import sys
import os
import subprocess
import logging
import shlex
from datetime import datetime
from typing import List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dataloader.database import SessionLocal
from dataloader.models import Job, JobRun

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pipeline_health_check")

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))

def run_test_for_job(job: Job):
    """Execute a single job script in test mode."""
    logger.info(f"Testing job: {job.name}...")
    
    # Build command
    # If it's a script that supports --test, add it
    # We check if the script is in our "testable" list
    parts = shlex.split(job.script_path)
    if not parts:
        return {
            "status": "failed",
            "stdout": "",
            "stderr": f"Invalid script path for job {job.name}",
            "duration": 0,
            "exit_code": 1
        }

    name_to_script = parts[0]
    full_path = os.path.join(SCRIPTS_DIR, name_to_script)
    
    args = [sys.executable, full_path]
    # Check if we should add --test (only for extractors and metrics)
    if any(k in job.name for k in ["Extract", "Calculate", "Metrics", "Snapshot"]):
        args.append("--test")
    
    # Handle existing arguments in script_path (e.g. --market B3)
    if len(parts) > 1:
        extra_args = parts[1:]
        args.extend(extra_args)
        
    start_time = datetime.utcnow()
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=job.timeout_seconds or 60,
            cwd=os.path.dirname(SCRIPTS_DIR)
        )
        
        duration = (datetime.utcnow() - start_time).total_seconds()
        status = "success" if result.returncode == 0 else "failed"
        
        return {
            "status": status,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration": duration,
            "exit_code": result.returncode
        }
    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        return {
            "status": "failed",
            "stdout": "",
            "stderr": str(e),
            "duration": duration,
            "exit_code": 1
        }

def main():
    session = SessionLocal()
    jobs = session.query(Job).filter(Job.name != "Pipeline Health Check").all()
    
    total = len(jobs)
    passed = 0
    failed = 0
    
    print(f"[PIPELINE HEALTH CHECK] Starting validation for {total} jobs...")
    
    for job in jobs:
        res = run_test_for_job(job)
        
        # Create a JobRun record for the TEST
        run = JobRun(
            job_id=job.id,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            status=res["status"],
            exit_code=res["exit_code"],
            stdout=res["stdout"],
            stderr=res["stderr"],
            duration_seconds=res["duration"],
            trigger="health_check" # Indicating this was a health check run
        )
        session.add(run)
        
        if res["status"] == "success":
            passed += 1
            print(f"  ✅ {job.name}: Passed ({res['duration']:.2f}s)")
        else:
            failed += 1
            print(f"  ❌ {job.name}: Failed")
            if res["stderr"]:
                print(f"     Error: {res['stderr'].strip()[:100]}...")
                
    session.commit()
    session.close()
    
    print("\n" + "="*40)
    print(f"HEALTH CHECK COMPLETE")
    print(f"Passed: {passed} / {total}")
    print(f"Failed: {failed}")
    print("="*40)
    
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    main()
