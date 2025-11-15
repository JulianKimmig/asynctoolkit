import io
import json
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

import pytest

from asynctoolkit.base import run_tool
from asynctoolkit.defaults.http import AsyncResponse, HTTPTool

try:  # Optional backends
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:  # pragma: no cover - best effort environment detection
    HAS_AIOHTTP = False

try:
    import requests

    HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    HAS_REQUESTS = False

try:
    import httpx

    HAS_HTTPX = True
except ImportError:  # pragma: no cover
    HAS_HTTPX = False

try:
    import pyodide

    HAS_PYODIDE = True
except ImportError:  # pragma: no cover
    HAS_PYODIDE = False

try:  # Optional Pyodide integration tests
    from pytest_pyodide import copy_files_to_pyodide, run_in_pyodide

    HAS_PYODIDE_TEST = (Path(__file__).parent.parent.parent / "pyodide").exists()
except ImportError:  # pragma: no cover
    HAS_PYODIDE_TEST = False


def _extensions():
    return [
        ("aiohttp", HAS_AIOHTTP),
        ("requests", HAS_REQUESTS),
        ("httpx", HAS_HTTPX),
    ]


def _schedule_json(httpserver, path, payload, *, status=200, method="GET", headers=None):
    httpserver.expect_request(path, method=method).respond_with_json(
        payload, headers=headers or {}, status=status
    )
    return httpserver.url_for(path)


def _schedule_data(httpserver, path, payload: bytes, *, status=200, method="GET"):
    httpserver.expect_request(path, method=method).respond_with_data(
        payload, status=status
    )
    return httpserver.url_for(path)


class _DummyAsyncResponse(AsyncResponse):
    def __init__(self, status=200, reason="OK", body=b"", headers=None):
        super().__init__("http://example", None)
        self._status = status
        self._reason = reason
        self._body = body
        self._headers = headers or {}

    async def text(self) -> str:
        if isinstance(self._body, bytes):
            return self._body.decode("utf-8", errors="ignore")
        return str(self._body)

    async def json(self):
        try:
            return json.loads(await self.text())
        except json.JSONDecodeError:
            return {}

    async def status(self) -> int:
        return self._status

    async def headers(self) -> dict:
        return dict(self._headers)

    async def reason(self):
        return self._reason

    async def iter_content(self, chunk_size: int = 1024):
        yield self._body

    async def content(self) -> bytes:
        if isinstance(self._body, bytes):
            return self._body
        return str(self._body).encode()


@pytest.mark.asyncio
@pytest.mark.parametrize("extension,available", _extensions())
async def test_http_tool_extension_local(httpserver, extension, available):
    if not available:
        pytest.skip(f"Extension '{extension}' not installed.")

    payload = {"message": "ok", "path": "/json"}
    url = _schedule_json(
        httpserver,
        "/json",
        payload,
        headers={"X-Test": "value"},
    )

    async with await run_tool(
        "http",
        url=url,
        method="GET",
        headers={"Accept": "application/json"},
        params={"foo": "bar"},
        extension=extension,
    ) as response:
        assert await response.status() == 200
        assert await response.reason()
        headers = await response.headers()
        assert headers.get("X-Test") == "value"
        assert json.loads(await response.text()) == payload
        assert await response.json() == payload


@pytest.mark.asyncio
@pytest.mark.parametrize("extension,available", _extensions())
async def test_http_content_method(httpserver, extension, available):
    if not available:
        pytest.skip(f"Extension '{extension}' not installed.")

    body = json.dumps({"chunked": True}).encode()
    url = _schedule_data(httpserver, "/content", body)

    async with await run_tool(
        "http",
        url=url,
        method="GET",
        extension=extension,
    ) as response:
        assert await response.content() == body


@pytest.mark.asyncio
@pytest.mark.parametrize("extension,available", _extensions())
async def test_http_iter_content(httpserver, extension, available):
    if not available:
        pytest.skip(f"Extension '{extension}' not installed.")

    body = json.dumps({"stream": True}).encode()
    url = _schedule_data(httpserver, "/stream", body)

    async with await run_tool(
        "http",
        url=url,
        method="GET",
        extension=extension,
        stream=True,
    ) as response:
        collected = bytearray()
        async for chunk in response.iter_content(5):
            assert len(chunk) <= 5
            collected.extend(chunk)
        assert collected == body


@pytest.mark.asyncio
@pytest.mark.parametrize("extension,available", _extensions())
async def test_http_raise_for(httpserver, extension, available):
    if not available:
        pytest.skip(f"Extension '{extension}' not installed.")

    url = _schedule_json(
        httpserver,
        "/missing",
        {"error": "nope"},
        status=404,
    )

    async with await run_tool(
        "http",
        url=url,
        method="GET",
        extension=extension,
    ) as response:
        with pytest.raises(AsyncResponse.HTTPError):
            await response.raise_for_status()


@pytest.mark.asyncio
async def test_http_conflicting_payloads():
    tool = HTTPTool()
    with pytest.raises(ValueError, match="data and json"):
        await tool.run("http://example", data={"a": 1}, json={"b": 2})


@pytest.mark.asyncio
async def test_async_response_raise_for_status_decodes_bytes_reason():
    reason_bytes = b"\xff"
    response = _DummyAsyncResponse(status=500, reason=reason_bytes)
    with pytest.raises(AsyncResponse.HTTPError) as excinfo:
        await response.raise_for_status()
    assert "500 Server Error" in str(excinfo.value)
    assert "ÿ" in str(excinfo.value)


@pytest.mark.asyncio
async def test_http_tool_forwards_request_kwargs():
    captured = []
    extension_name = f"_capture_{uuid.uuid4().hex}"

    async def capture_extension(**kwargs):
        captured.append(kwargs)

        @asynccontextmanager
        async def _ctx():
            yield _DummyAsyncResponse()

        return _ctx()

    HTTPTool.register_extension(extension_name, capture_extension)

    tool = HTTPTool()
    files = {"upload": ("sample.txt", io.BytesIO(b"abc"), "text/plain")}
    cookies = {"session": "abc"}
    headers = {"X-Test": "1"}
    params = {"q": "1"}
    body = b"payload"

    async with await tool.run(
        "http://example",
        method="POST",
        headers=headers,
        params=params,
        data=body,
        files=files,
        cookies=cookies,
        stream=True,
        timeout=5,
        extension=extension_name,
    ):
        pass

    assert captured[0]["headers"] == headers
    assert captured[0]["params"] == params
    assert captured[0]["data"] == body
    assert captured[0]["files"] == files
    assert captured[0]["cookies"] == cookies
    assert captured[0]["stream"] is True
    assert captured[0]["timeout"] == 5

    async with await tool.run(
        "http://example/json",
        method="PUT",
        json={"a": 1},
        extension=extension_name,
    ):
        pass

    assert captured[1]["json"] == {"a": 1}
    assert "data" not in captured[1]


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
async def test_http_aiohttp_files_and_validation(httpserver, tmp_path):
    file_path = tmp_path / "sample.txt"
    file_path.write_text("payload")
    file_obj = io.BytesIO(file_path.read_bytes())
    file_obj.name = "sample.txt"
    body = {"uploaded": True}
    url = _schedule_json(
        httpserver,
        "/upload",
        body,
        method="POST",
    )

    async with await run_tool(
        "http",
        url=url,
        method="POST",
        data={"field": "value"},
        files={
            "upload": ("sample.txt", file_obj, "text/plain"),
        },
        cookies={"a": "b"},
        extension="aiohttp",
    ) as response:
        assert await response.json() == body

    with pytest.raises(TypeError):
        await run_tool(
            "http",
            url=url,
            method="POST",
            data=b"not mapping",
            files={"upload": io.BytesIO(b"data")},
            extension="aiohttp",
        )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
async def test_http_aiohttp_invalid_file_tuple(httpserver):
    url = _schedule_json(httpserver, "/invalid", {"ok": True}, method="POST")
    with pytest.raises(ValueError):
        await run_tool(
            "http",
            url=url,
            method="POST",
            data={"field": "value"},
            files={"upload": ("only_name",)},
            extension="aiohttp",
        )


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
async def test_http_aiohttp_file_object_uses_name(httpserver):
    url = _schedule_json(httpserver, "/upload-object", {"ok": True}, method="POST")
    file_obj = io.BytesIO(b"payload")
    file_obj.name = "object-name.txt"

    async with await run_tool(
        "http",
        url=url,
        method="POST",
        files={"upload": file_obj},
        extension="aiohttp",
    ) as response:
        assert await response.json() == {"ok": True}


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
async def test_http_aiohttp_timeout_fallback(monkeypatch, httpserver):
    url = _schedule_json(httpserver, "/timeout", {"status": "ok"})

    def fake_timeout(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "asynctoolkit.defaults.http.aiohttp.ClientTimeout", fake_timeout
    )

    async with await run_tool(
        "http",
        url=url,
        method="GET",
        timeout=5,
        extension="aiohttp",
    ) as response:
        assert await response.json() == {"status": "ok"}


if HAS_PYODIDE_TEST:

    @copy_files_to_pyodide(
        file_list=[("src/asynctoolkit", "asynctoolkit")],
        install_wheels=True,
        recurse_directories=True,
    )
    @run_in_pyodide
    async def test_http_tool_extension_pyodide(selenium):
        import os

        from asynctoolkit.base import run_tool

        TEST_URL = "https://httpbin.org/get"

        async with await run_tool(
            "http",
            url=TEST_URL,
            method="GET",
            extension="pyodide",
        ) as response:
            status = await response.status()
            assert status == 200

            data = await response.json()
            assert "url" in data
            assert data["url"].startswith(TEST_URL)

    @copy_files_to_pyodide(
        file_list=[("src/asynctoolkit", "asynctoolkit")],
        install_wheels=True,
        recurse_directories=True,
    )
    @run_in_pyodide
    async def test_http_raise_for_pyodide(selenium):
        import os

        from asynctoolkit.base import run_tool
        from asynctoolkit.defaults.http import AsyncResponse

        TEST_URL = "https://httpbin.org/status/404"

        async with await run_tool(
            "http",
            url=TEST_URL,
            method="GET",
            extension="pyodide",
        ) as response:
            try:
                await response.raise_for_status()
                raise ValueError("Expected HTTPError")
            except AsyncResponse.HTTPError:
                pass

    @copy_files_to_pyodide(
        file_list=[("src/asynctoolkit", "asynctoolkit")],
        install_wheels=True,
        recurse_directories=True,
    )
    @run_in_pyodide
    async def test_http_iter_content_pyodide(selenium):
        import os

        from asynctoolkit.base import run_tool

        TEST_URL = "https://httpbin.org/get"

        async with await run_tool(
            "http",
            url=TEST_URL,
            method="GET",
            extension="pyodide",
            stream=True,
        ) as response:
            content = b""
            async for chunk in response.iter_content(11):
                assert len(chunk) <= 11
                content += chunk

            assert content
            data = json.loads(content)
            assert "url" in data
            assert data["url"].startswith(TEST_URL)
