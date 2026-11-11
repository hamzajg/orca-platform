import pytest
from app.main import app
from app.services.rate_limiter import RateLimiter


def test_expected_routes_are_registered():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/health" in paths
    assert "/api/info" in paths
    assert any(path.startswith("/v1/") for path in paths)


@pytest.mark.asyncio
async def test_rate_limiter_allows_within_limit_and_blocks_after():
    limiter = RateLimiter()

    assert (await limiter.check("test-key", limit=2))[0] is True
    assert (await limiter.check("test-key", limit=2))[0] is True

    allowed, retry_after = await limiter.check("test-key", limit=2)
    assert allowed is False
    assert retry_after >= 0


@pytest.mark.asyncio
async def test_rate_limiter_zero_means_unlimited():
    limiter = RateLimiter()
    for _ in range(10):
        allowed, _ = await limiter.check("unlimited", limit=0)
        assert allowed is True
