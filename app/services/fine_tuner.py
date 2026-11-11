import asyncio
import logging
import json
import uuid
from datetime import datetime
from app.db import get_db

logger = logging.getLogger(__name__)


class FineTuneManager:
    #: Job states from which a cancel request is accepted.
    CANCELLABLE = {"draft", "scheduled", "queued", "running"}

    def __init__(self):
        # job_id -> asyncio.Task for jobs currently being executed.
        self.running_jobs = {}

    async def create_job(self, data):
        job_id = str(uuid.uuid4())
        async with get_db() as db:
            await db.execute(
                """INSERT INTO fine_tune_jobs (
                    id, name, description, base_model, method, dataset_source, dataset_format, 
                    hyperparameters, output_model_name, target_node_id, status, schedule_at, created_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id, data.name, data.description, data.base_model, data.method, data.dataset_source, 
                    data.dataset_format, json.dumps(data.hyperparameters), 
                    data.output_model_name, data.target_node_id, 
                    'scheduled' if data.schedule_at else 'queued',
                    data.schedule_at, data.created_by
                )
            )
            await db.commit()
        return job_id

    async def get_jobs(self, status=None):
        async with get_db() as db:
            query = "SELECT * FROM fine_tune_jobs"
            params = []
            if status:
                query += " WHERE status = ?"
                params.append(status)
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_job(self, job_id):
        async with get_db() as db:
            cursor = await db.execute("SELECT * FROM fine_tune_jobs WHERE id = ?", (job_id,))
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def run_scheduler(self):
        while True:
            try:
                jobs = await self.get_jobs(status='queued')
                for job in jobs:
                    if job['id'] not in self.running_jobs:
                        self._start_job(job['id'])
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(15)

    def _start_job(self, job_id):
        """
        Start a job's training task and track it so it can be cancelled.

        Tracking the task (rather than a bare boolean) is what lets
        `cancel_job` actually stop an in-flight run.
        """
        task = asyncio.create_task(self._execute_job(job_id))
        self.running_jobs[job_id] = task
        task.add_done_callback(lambda _t, jid=job_id: self.running_jobs.pop(jid, None))
        return task

    async def cancel_job(self, job_id):
        """
        Cancel a job that is queued, scheduled or running.

        Returns the updated job dict, or ``None`` if no such job exists.
        Raises ``ValueError`` if the job exists but is not in a cancellable state.
        """
        job = await self.get_job(job_id)
        if job is None:
            return None
        if job['status'] not in self.CANCELLABLE:
            raise ValueError(f"Job is not cancellable (status={job['status']})")

        task = self.running_jobs.pop(job_id, None)
        if task is not None and not task.done():
            task.cancel()

        async with get_db() as db:
            await db.execute(
                "UPDATE fine_tune_jobs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
                ("Cancelled by user", datetime.now().isoformat(), job_id),
            )
            await db.commit()
        return await self.get_job(job_id)

    async def delete_job(self, job_id):
        """
        Delete a job record.

        Returns ``True`` if a row was deleted, ``False`` if the job doesn't exist.
        Raises ``ValueError`` if the job is currently running — cancel it first.
        """
        job = await self.get_job(job_id)
        if job is None:
            return False
        if job['status'] == 'running' or job_id in self.running_jobs:
            raise ValueError("Cannot delete a running job; cancel it first")

        async with get_db() as db:
            await db.execute("DELETE FROM fine_tune_jobs WHERE id = ?", (job_id,))
            await db.commit()
        return True

    async def _execute_job(self, job_id):
        try:
            # Placeholder for training logic
            logger.info(f"Starting job {job_id}")
            async with get_db() as db:
                await db.execute("UPDATE fine_tune_jobs SET status = 'running', started_at = ? WHERE id = ?", 
                                 (datetime.now().isoformat(), job_id))
                await db.commit()
            
            # Logic would go here
            await asyncio.sleep(5) 
            
            async with get_db() as db:
                await db.execute("UPDATE fine_tune_jobs SET status = 'completed', finished_at = ? WHERE id = ?", 
                                 (datetime.now().isoformat(), job_id))
                await db.commit()
        except asyncio.CancelledError:
            logger.info(f"Job {job_id} cancelled")
            raise
        finally:
            self.running_jobs.pop(job_id, None)


fine_tuner = FineTuneManager()
