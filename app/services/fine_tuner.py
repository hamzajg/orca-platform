import asyncio
import logging
import json
import uuid
from datetime import datetime
from app.db import get_db

logger = logging.getLogger(__name__)

class FineTuneManager:
    def __init__(self):
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
                        asyncio.create_task(self._execute_job(job['id']))
            except Exception as e:
                logger.error(f"Scheduler error: {e}")
            await asyncio.sleep(15)

    async def _execute_job(self, job_id):
        self.running_jobs[job_id] = True
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
        finally:
            del self.running_jobs[job_id]

fine_tuner = FineTuneManager()
