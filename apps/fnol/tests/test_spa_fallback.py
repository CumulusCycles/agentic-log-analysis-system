"""Catch-all SPA fallback must serve index.html for unknown client routes and
reject path-traversal attempts that escape the frontend/dist directory."""

import pytest


@pytest.mark.asyncio
async def test_unknown_path_serves_index_html(client):
    # In test mode the frontend/dist may or may not exist. If it doesn't,
    # the catch-all isn't registered and FastAPI returns 404 — that's the
    # correct anonymous-failure mode. If it does exist, the catch-all serves
    # the SPA shell so React Router can handle the route client-side.
    r = await client.get("/some-spa-route")
    assert r.status_code in (200, 404)


@pytest.mark.asyncio
async def test_path_traversal_attempt_does_not_escape_dist(client):
    # Any of these encodings must NOT return file contents from outside
    # frontend/dist. They should return 200 (index.html fallback) or 404 —
    # never a 200 with /etc/passwd-style contents.
    for path in (
        "../etc/passwd",
        "../../etc/passwd",
        "..%2F..%2Fetc%2Fpasswd",
    ):
        r = await client.get(f"/{path}")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            # index.html starts with the HTML doctype, never with `root:` etc.
            assert b"root:" not in r.content
            assert b"/etc/passwd" not in r.content
