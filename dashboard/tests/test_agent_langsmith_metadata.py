"""Verify every `graph.ainvoke` carries `session_id` + `jwt_sub` in `config.metadata`.

The router builds the `config={"configurable": {"thread_id": ...}, "metadata": {...}}`
dict — LangSmith picks up the metadata and exposes it as filterable run
properties. We spy on the graph's `ainvoke` to capture exactly what the
router passes.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_chat_invocation_carries_session_id_and_jwt_sub_in_metadata(
    app_instance, valid_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spy on the agent graph's ainvoke to confirm the config metadata
    contains both `session_id` and `jwt_sub`."""
    from httpx import ASGITransport, AsyncClient

    captured: list[dict] = []
    real_ainvoke = app_instance.state.agent_graph.ainvoke

    async def _spy(state, config=None, **kwargs):
        captured.append(config or {})
        return await real_ainvoke(state, config=config, **kwargs)

    monkeypatch.setattr(app_instance.state.agent_graph, "ainvoke", _spy)

    transport = ASGITransport(app=app_instance, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        await ac.post(
            "/api/chat",
            json={"message": "hello"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )

    assert captured, "graph.ainvoke was never called"
    config = captured[0]
    assert "configurable" in config
    assert "thread_id" in config["configurable"]
    assert config["configurable"]["thread_id"].startswith("admin:")
    metadata = config.get("metadata") or {}
    assert "session_id" in metadata
    assert metadata["jwt_sub"] == "admin"
    assert metadata["dry_run"] is True


@pytest.mark.asyncio
async def test_thread_id_is_jwt_sub_colon_session_id(
    app_instance, valid_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`thread_id` is `f"{jwt_sub}:{session_id}"` — proves we don't accidentally
    leak across users by reusing a bare `session_id` as the thread key."""
    from httpx import ASGITransport, AsyncClient

    captured: list[dict] = []
    real_ainvoke = app_instance.state.agent_graph.ainvoke

    async def _spy(state, config=None, **kwargs):
        captured.append(config or {})
        return await real_ainvoke(state, config=config, **kwargs)

    monkeypatch.setattr(app_instance.state.agent_graph, "ainvoke", _spy)

    transport = ASGITransport(app=app_instance, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.post(
            "/api/chat",
            json={"message": "hello", "session_id": "my-session-xyz"},
            headers={"Authorization": f"Bearer {valid_token}"},
        )
    assert response.status_code == 200
    assert captured[0]["configurable"]["thread_id"] == "admin:my-session-xyz"
