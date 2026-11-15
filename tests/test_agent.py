"""Tests for the in-gateway agent (services/agent.py)."""

import pytest

from app.services import agent as agent_svc


class FakeNode:
    id = "n1"
    label = "worker-1"
    host = "10.0.0.1"
    port = 11434
    enabled = True

    class _Status:
        value = "healthy"

    status = _Status()
    available_models = ["llama3.2"]


class FakeRegistry:
    def get_all_nodes(self):
        return [FakeNode()]

    def get_all_models(self):
        return {"n1": ["llama3.2"]}

    async def get_next_node(self, model=None):
        return FakeNode()


@pytest.fixture
def registry():
    return FakeRegistry()


def test_build_tools_read_only():
    tools = agent_svc.build_tools(FakeRegistry())
    names = {t["function"]["name"] for t in tools}
    assert names == {"list_nodes", "list_models", "get_metrics", "list_fine_tune_jobs"}


@pytest.mark.asyncio
async def test_execute_tool_unknown_name(registry):
    result = await agent_svc.execute_tool(registry, "nope", {})
    assert result["ok"] is False


@pytest.mark.asyncio
async def test_execute_tool_nodes(registry):
    result = await agent_svc.execute_tool(registry, "list_nodes", {})
    assert result["ok"] is True
    assert result["result"]["nodes"][0]["host"] == "10.0.0.1"


@pytest.mark.asyncio
async def test_execute_tool_metrics_bad_window_falls_back(registry):
    # invalid window should surface an error result, not raise
    result = await agent_svc.execute_tool(registry, "get_metrics", {"window": "bogus"})
    assert "ok" in result


@pytest.mark.asyncio
async def test_chat_no_tool_calls_returns_reply(registry):
    async def chat_fn(reg, model, messages, tools):
        return {"content": "All nodes healthy.", "tool_calls": []}

    out = await agent_svc.chat(registry, "how are nodes?", chat_fn=chat_fn)
    assert out["reply"] == "All nodes healthy."
    assert out["tool_trace"] == []


@pytest.mark.asyncio
async def test_chat_runs_tool_loop(registry):
    calls = []

    async def chat_fn(reg, model, messages, tools):
        calls.append(len(messages))
        if len(calls) == 1:
            return {
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "list_nodes",
                            "arguments": "{}",
                        }
                    }
                ],
            }
        # second call: assert tool result was appended
        assert any(m.get("role") == "tool" for m in messages)
        return {"content": "1 node is healthy.", "tool_calls": []}

    out = await agent_svc.chat(registry, "node status?", chat_fn=chat_fn)
    assert out["reply"] == "1 node is healthy."
    assert len(out["tool_trace"]) == 1
    assert out["tool_trace"][0]["tool"] == "list_nodes"


@pytest.mark.asyncio
async def test_chat_iteration_budget(registry):
    async def chat_fn(reg, model, messages, tools):
        return {
            "content": "",
            "tool_calls": [{"function": {"name": "list_models", "arguments": {}}}],
        }

    out = await agent_svc.chat(registry, "loop", chat_fn=chat_fn)
    assert "budget" in out["reply"].lower() or out["tool_trace"]
    assert len(out["tool_trace"]) <= agent_svc.MAX_ITERATIONS
