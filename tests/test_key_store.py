"""
KeyStore — named API keys with revoke/enable, rate limits and usage counters.

This is the auth layer's source of truth: a bug here either locks everyone
out or lets a revoked key keep working. Runs against a throwaway SQLite file
via the same temp_db pattern as test_fine_tuner.py.
"""
import pytest

from app.config import get_settings
from app.db import get_db, init_db
from app.services.key_store import KeyStore


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the app at a per-test SQLite file and reset the settings cache."""
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "platform.db"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture()
async def store(temp_db):
    await init_db()
    ks = KeyStore()
    await ks.startup(frozenset())
    yield ks
    # record_usage() flushes in the background; let those writes finish so no
    # aiosqlite worker thread is left alive when the interpreter exits.
    await ks.drain()


class TestBootstrap:
    async def test_bootstrap_keys_are_imported(self, temp_db):
        await init_db()
        ks = KeyStore()
        await ks.startup(frozenset({"env-key-1", "env-key-2"}))

        names = {k.name for k in ks.list_keys()}
        assert names == {"bootstrap-1", "bootstrap-2"}
        assert ks.validate("env-key-1") is not None
        assert ks.validate("env-key-2") is not None

    async def test_bootstrap_import_is_idempotent(self, temp_db):
        await init_db()
        ks = KeyStore()
        await ks.startup(frozenset({"env-key-1"}))
        await ks.startup(frozenset({"env-key-1"}))
        assert len(ks.list_keys()) == 1


class TestCreateAndValidate:
    async def test_create_generates_usable_key(self, store):
        key = await store.create_key("laptop-dev")
        assert len(key.key) == 64  # secrets.token_hex(32)
        assert store.validate(key.key) is key

    async def test_duplicate_name_rejected(self, store):
        await store.create_key("dup")
        with pytest.raises(ValueError, match="already exists"):
            await store.create_key("dup")

    async def test_validate_rejects_unknown_key(self, store):
        assert store.validate("not-a-real-key") is None

    async def test_key_hint_never_leaks_full_key(self, store):
        key = await store.create_key("hinted")
        assert key.key_hint == key.key[:8]
        assert key.key not in key.key_hint
        assert key.to_dict()["key"] is None  # hidden unless reveal_key=True


class TestRevokeEnableDelete:
    async def test_revoke_blocks_validation(self, store):
        await store.create_key("temp")
        key = next(k for k in store.list_keys() if k.name == "temp")

        assert await store.revoke_key("temp") is True
        assert store.validate(key.key) is None

        assert await store.enable_key("temp") is True
        assert store.validate(key.key) is key

    async def test_revoke_unknown_returns_false(self, store):
        assert await store.revoke_key("ghost") is False
        assert await store.enable_key("ghost") is False
        assert await store.delete_key("ghost") is False

    async def test_delete_removes_key(self, store):
        key = await store.create_key("doomed")
        assert await store.delete_key("doomed") is True
        assert store.validate(key.key) is None
        assert all(k.name != "doomed" for k in store.list_keys())


class TestRateLimitAndUsage:
    async def test_rate_limit_roundtrip(self, store):
        await store.create_key("limited", rate_limit_rpm=60)
        key = next(k for k in store.list_keys() if k.name == "limited")
        assert key.rate_limit_rpm == 60

        assert await store.update_rate_limit("limited", 120) is True
        assert key.rate_limit_rpm == 120
        assert await store.update_rate_limit("ghost", 10) is False

    async def test_record_usage_bumps_counter(self, store):
        key = await store.create_key("counted")
        assert key.request_count == 0
        assert key.last_used is None

        await store.record_usage(key.key)
        # record_usage mutates the in-memory object synchronously; the DB
        # flush is a background task we don't need to await here.
        assert key.request_count == 1
        assert key.last_used is not None

        await store.record_usage(key.key)
        assert key.request_count == 2

    async def test_usage_on_unknown_key_is_ignored(self, store):
        await store.record_usage("never-existed")  # must not raise
