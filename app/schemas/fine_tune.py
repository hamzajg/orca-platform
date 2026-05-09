from pydantic import BaseModel
from typing import Optional, Dict, Any

class FineTuneJobCreate(BaseModel):
    name: str
    description: Optional[str] = None
    base_model: str
    method: str  # lora, qlora, full
    dataset_source: str
    dataset_format: str
    hyperparameters: Dict[str, Any]
    output_model_name: str
    target_node_id: Optional[str] = None
    schedule_at: Optional[str] = None
    created_by: Optional[str] = None

class FineTuneJob(FineTuneJobCreate):
    id: str
    status: str
    progress: float
    log: Optional[str] = None
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    created_at: str
