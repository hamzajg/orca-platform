from fastapi import APIRouter, Depends, HTTPException
from typing import List, Optional
from app.schemas.fine_tune import FineTuneJob, FineTuneJobCreate
from app.services.fine_tuner import fine_tuner
from app.middleware.auth import require_api_key

router = APIRouter(prefix="/api/fine-tune", dependencies=[Depends(require_api_key)])

@router.post("/jobs", response_model=dict)
async def create_job(data: FineTuneJobCreate):
    job_id = await fine_tuner.create_job(data)
    return {"id": job_id}

@router.get("/jobs", response_model=List[dict])
async def list_jobs(status: Optional[str] = None):
    return await fine_tuner.get_jobs(status=status)

@router.get("/jobs/{job_id}", response_model=dict)
async def get_job(job_id: str):
    job = await fine_tuner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/jobs/{job_id}/run")
async def run_job(job_id: str):
    job = await fine_tuner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # Manually trigger execution
    import asyncio
    asyncio.create_task(fine_tuner._execute_job(job_id))
    return {"status": "triggered"}
