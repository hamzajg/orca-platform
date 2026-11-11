"""
Unit tests for the fine-tune job lifecycle (create / cancel / delete).

These run against a throwaway SQLite file — no server, no Ollama, no network.
"""
import asyncio

import pytest

from app.config import get_settings
from app.db import get_db, init_db
from app.schemas.fine_tune import FineTuneJobCreate
from app.services.fine_tuner import FineTuneManager


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the app at a per-test SQLite file and reset the settings cache."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "platform.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def make_job(**overrides) -> FineTuneJobCreate:
    data = dict(
        name="demo-job",
        base_model="llama3.2",
        method="lora",
        dataset_source="/tmp/dataset.jsonl",
        dataset_format="alpaca",
        hyperparameters={"epochs": 3},
        output_model_name="demo-lora",
    )
    data.update(overrides)
    return FineTuneJobCreate(**data)


async def _set_status(job_id: str, status: str) -> None:
    async with get_db() as db:
        await db.execute("UPDATE fine_tune_jobs SET status = ? WHERE id = ?", (status, job_id))
        await db.commit()


class TestCreateJob:
    async def test_create_defaults_to_queued(self, temp_db):
        await init_db()
        mgr = FineTuneManager()

        job_id = await mgr.create_job(make_job())

        job = await mgr.get_job(job_id)
        assert job is not None
        assert job["status"] == "queued"
        assert job["name"] == "demo-job"
        assert job["description"] is None

    async def test_schedule_at_yields_scheduled_status(self, temp_db):
        await init_db()
        mgr = FineTuneManager()

        job_id = await mgr.create_job(make_job(schedule_at="2030-01-01T00:00:00"))

        assert (await mgr.get_job(job_id))["status"] == "scheduled"

    async def test_get_jobs_filters_by_status(self, temp_db):
        await init_db()
        mgr = FineTuneManager()
        queued_id = await mgr.create_job(make_job(name="a"))
        await mgr.create_job(make_job(name="b", schedule_at="2030-01-01T00:00:00"))

        queued = await mgr.get_jobs(status="queued")

        assert [j["id"] for j in queued] == [queued_id]


class TestCancelJob:
    async def test_cancel_queued_job_marks_failed(self, temp_db):
        await init_db()
        mgr = FineTuneManager()
        job_id = await mgr.create_job(make_job())

        job = await mgr.cancel_job(job_id)

        assert job["status"] == "failed"
        assert job["error"] == "Cancelled by user"
        assert job["finished_at"] is not None

    async def test_cancel_unknown_job_returns_none(self, temp_db):
        await init_db()
        mgr = FineTuneManager()

        assert await mgr.cancel_job("does-not-exist") is None

    async def test_cancel_completed_job_raises(self, temp_db):
        await init_db()
        mgr = FineTuneManager()
        job_id = await mgr.create_job(make_job())
        await _set_status(job_id, "completed")

        with pytest.raises(ValueError):
            await mgr.cancel_job(job_id)

    async def test_cancel_running_job_stops_task(self, temp_db):
        await init_db()
        mgr = FineTuneManager()
        job_id = await mgr.create_job(make_job())

        task = mgr._start_job(job_id)
        await asyncio.sleep(0.1)  # let _execute_job flip the row to 'running'
        assert (await mgr.get_job(job_id))["status"] == "running"

        job = await mgr.cancel_job(job_id)

        assert job["status"] == "failed"
        assert job_id not in mgr.running_jobs
        with pytest.raises(asyncio.CancelledError):
            await task

    async def test_start_job_is_tracked(self, temp_db):
        await init_db()
        mgr = FineTuneManager()
        job_id = await mgr.create_job(make_job())

        task = mgr._start_job(job_id)

        assert mgr.running_jobs[job_id] is task
        await mgr.cancel_job(job_id)


class TestDeleteJob:
    async def test_delete_removes_row(self, temp_db):
        await init_db()
        mgr = FineTuneManager()
        job_id = await mgr.create_job(make_job())

        assert await mgr.delete_job(job_id) is True
        assert await mgr.get_job(job_id) is None

    async def test_delete_unknown_job_returns_false(self, temp_db):
        await init_db()
        mgr = FineTuneManager()

        assert await mgr.delete_job("nope") is False

    async def test_delete_running_job_raises(self, temp_db):
        await init_db()
        mgr = FineTuneManager()
        job_id = await mgr.create_job(make_job())
        await _set_status(job_id, "running")

        with pytest.raises(ValueError):
            await mgr.delete_job(job_id)
