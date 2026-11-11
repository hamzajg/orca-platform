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
    fine_tuner._start_job(job_id)
    return {"status": "triggered"}

@router.post("/jobs/{job_id}/cancel", response_model=dict)
async def cancel_job(job_id: str):
    try:
        job = await fine_tuner.cancel_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.delete("/jobs/{job_id}", response_model=dict)
async def delete_job(job_id: str):
    try:
        deleted = await fine_tuner.delete_job(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if not deleted:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "deleted", "id": job_id}

