import io
import json
import ssl
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

import pytest

from asynctoolkit.base import run_tool
from asynctoolkit.defaults.http import (
    AsyncResponse,
    HTTPTool,
    MockHTTPRequest,
    MockHTTPResponse,
)

try:  # Optional backends
    import aiohttp  # noqa: F401

    HAS_AIOHTTP = True
except ImportError:  # pragma: no cover - best effort environment detection
    HAS_AIOHTTP = False

try:
    import requests  # noqa: F401

    HAS_REQUESTS = True
except ImportError:  # pragma: no cover
    HAS_REQUESTS = False

try:
    import httpx  # noqa: F401

    HAS_HTTPX = True
except ImportError:  # pragma: no cover
    HAS_HTTPX = False

try:
    import pyodide  # noqa: F401

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


def _schedule_json(
    httpserver, path, payload, *, status=200, method="GET", headers=None
):
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


class _FakeRequestsResponse:
    def __init__(self, url="http://example", body=b'{"ok": true}'):
        self.url = url
        self.text = body.decode("utf-8")
        self._body = body
        self.status_code = 200
        self.headers = {"Content-Type": "application/json"}
        self.reason = "OK"

    def json(self):
        return json.loads(self.text)

    def iter_content(self, chunk_size=1024):
        for idx in range(0, len(self._body), chunk_size):
            yield self._body[idx : idx + chunk_size]


class _FakeHttpxResponse:
    def __init__(self, url="http://example", body=b'{"ok": true}'):
        self.url = url
        self.text = body.decode("utf-8")
        self._body = body
        self.status_code = 200
        self.headers = {"Content-Type": "application/json"}
        self.reason_phrase = "OK"

    def json(self):
        return json.loads(self.text)

    async def aiter_bytes(self, chunk_size=1024):
        for idx in range(0, len(self._body), chunk_size):
            yield self._body[idx : idx + chunk_size]

    async def aread(self):
        return self._body


class _FakeAiohttpContent:
    def __init__(self, body: bytes):
        self._body = body

    async def iter_chunked(self, chunk_size: int):
        for idx in range(0, len(self._body), chunk_size):
            yield self._body[idx : idx + chunk_size]


class _FakeAiohttpResponse:
    def __init__(self, url="http://example", body=b'{"ok": true}'):
        self.url = url
        self.status = 200
        self.headers = {"Content-Type": "application/json"}
        self.reason = "OK"
        self._body = body
        self.content = _FakeAiohttpContent(body)

    async def text(self):
        return self._body.decode("utf-8")

    async def json(self):
        return json.loads(await self.text())

    async def read(self):
        return self._body


class _FakeAiohttpRequestContext:
    def __init__(self, response: _FakeAiohttpResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeAiohttpClientSession:
    def __init__(self, calls: list[dict]):
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def request(self, method, url, **kwargs):
        self._calls.append(
            {
                "method": method,
                "url": url,
                "kwargs": kwargs,
            }
        )
        return _FakeAiohttpRequestContext(_FakeAiohttpResponse(url=url))


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
async def test_http_tool_forwards_verify_request_kwarg():
    captured = []
    extension_name = f"_capture_verify_{uuid.uuid4().hex}"
    ssl_context = ssl.create_default_context()

    async def capture_extension(**kwargs):
        captured.append(kwargs)

        @asynccontextmanager
        async def _ctx():
            yield _DummyAsyncResponse()

        return _ctx()

    HTTPTool.register_extension(extension_name, capture_extension)

    tool = HTTPTool()

    async with await tool.run(
        "http://example/verify-false",
        extension=extension_name,
        verify=False,
    ):
        pass

    async with await tool.run(
        "http://example/verify-path",
        extension=extension_name,
        verify="/tmp/internal-ca.pem",
    ):
        pass

    async with await tool.run(
        "http://example/verify-context",
        extension=extension_name,
        verify=ssl_context,
    ):
        pass

    async with await tool.run(
        "http://example/verify-default",
        extension=extension_name,
    ):
        pass

    assert captured[0]["verify"] is False
    assert captured[1]["verify"] == "/tmp/internal-ca.pem"
    assert captured[2]["verify"] is ssl_context
    assert "verify" not in captured[3]


@pytest.mark.asyncio
async def test_http_tool_rejects_invalid_verify_type():
    tool = HTTPTool()

    with pytest.raises(TypeError, match="verify"):
        await tool.run("http://example/invalid-verify", verify=object())


@pytest.mark.asyncio
async def test_http_mock_extension_uses_request_handler():
    captured = []
    file_obj = io.BytesIO(b"abc")

    async def handler(request: MockHTTPRequest) -> MockHTTPResponse:
        captured.append(request)
        assert request.url == "http://example/mock"
        assert request.method == "POST"
        assert request.headers == {"X-Test": "1"}
        assert request.params == {"page": "2"}
        assert request.data == b"payload"
        assert request.json is None
        assert request.timeout == 7
        assert request.stream is True
        assert request.files == {"upload": ("sample.txt", file_obj)}
        assert request.cookies == {"session": "cookie"}
        return MockHTTPResponse(
            status=201,
            reason="Created",
            headers={"X-Mocked": "yes"},
            json={"ok": True},
        )

    async with await run_tool(
        "http",
        url="http://example/mock",
        method="POST",
        headers={"X-Test": "1"},
        params={"page": "2"},
        data=b"payload",
        timeout=7,
        stream=True,
        files={"upload": ("sample.txt", file_obj)},
        cookies={"session": "cookie"},
        extension="mock",
        request_handler=handler,
    ) as response:
        assert await response.status() == 201
        assert await response.reason() == "Created"
        assert await response.headers() == {"X-Mocked": "yes"}
        assert await response.json() == {"ok": True}
        assert await response.text() == '{"ok": true}'

    assert len(captured) == 1


@pytest.mark.asyncio
async def test_http_mock_extension_requires_request_handler():
    tool = HTTPTool()

    with pytest.raises(ValueError, match="request_handler"):
        await tool.run("http://example/mock", extension="mock")


@pytest.mark.asyncio
async def test_http_mock_request_handler_defaults_to_mock_extension():
    seen = []

    def handler(request: MockHTTPRequest) -> MockHTTPResponse:
        seen.append(request)
        assert request.extra == {}
        return MockHTTPResponse(json={"ok": True})

    async with await run_tool(
        "http",
        url="http://example/default-mock",
        method="GET",
        request_handler=handler,
    ) as response:
        assert await response.json() == {"ok": True}

    assert len(seen) == 1


@pytest.mark.asyncio
async def test_http_mock_extension_exposes_verify():
    ssl_context = ssl.create_default_context()
    seen = []

    def handler(request: MockHTTPRequest) -> MockHTTPResponse:
        seen.append(request.verify)
        return MockHTTPResponse(json={"ok": True})

    async with await run_tool(
        "http",
        url="http://example/mock-verify-false",
        method="GET",
        verify=False,
        request_handler=handler,
    ) as response:
        assert await response.json() == {"ok": True}

    async with await run_tool(
        "http",
        url="http://example/mock-verify-path",
        method="GET",
        verify="/tmp/internal-ca.pem",
        request_handler=handler,
    ) as response:
        assert await response.json() == {"ok": True}

    async with await run_tool(
        "http",
        url="http://example/mock-verify-context",
        method="GET",
        verify=ssl_context,
        request_handler=handler,
    ) as response:
        assert await response.json() == {"ok": True}

    assert seen[0] is False
    assert seen[1] == "/tmp/internal-ca.pem"
    assert seen[2] is ssl_context


@pytest.mark.asyncio
async def test_http_mock_extension_supports_binary_bodies():
    body = b"streamed-body"

    def handler(request: MockHTTPRequest) -> MockHTTPResponse:
        assert request.method == "GET"
        return MockHTTPResponse(
            status=202,
            reason="Accepted",
            headers={"Content-Type": "application/octet-stream"},
            body=body,
        )

    async with await run_tool(
        "http",
        url="http://example/binary",
        method="GET",
        extension="mock",
        request_handler=handler,
        stream=True,
    ) as response:
        assert await response.content() == body

        chunks = []
        async for chunk in response.iter_content(4):
            assert len(chunk) <= 4
            chunks.append(chunk)

    assert b"".join(chunks) == body


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_REQUESTS, reason="requests not available")
async def test_http_requests_verify_forwarding(monkeypatch):
    captured = []

    def fake_request(*args, **kwargs):
        captured.append(kwargs)
        return _FakeRequestsResponse(url=kwargs["url"])

    monkeypatch.setattr("asynctoolkit.defaults.http.requests.request", fake_request)

    async with await run_tool(
        "http",
        url="http://example/requests-false",
        method="GET",
        extension="requests",
        verify=False,
    ) as response:
        assert await response.json() == {"ok": True}

    async with await run_tool(
        "http",
        url="http://example/requests-path",
        method="GET",
        extension="requests",
        verify="/tmp/internal-ca.pem",
    ) as response:
        assert await response.json() == {"ok": True}

    async with await run_tool(
        "http",
        url="http://example/requests-default",
        method="GET",
        extension="requests",
    ) as response:
        assert await response.json() == {"ok": True}

    assert captured[0]["verify"] is False
    assert captured[1]["verify"] == "/tmp/internal-ca.pem"
    assert "verify" not in captured[2]


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_HTTPX, reason="httpx not available")
async def test_http_httpx_verify_forwarding(monkeypatch):
    client_kwargs = []
    ssl_context = ssl.create_default_context()

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            client_kwargs.append(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return _FakeHttpxResponse(url=url)

    monkeypatch.setattr("asynctoolkit.defaults.http.httpx.AsyncClient", FakeAsyncClient)

    async with await run_tool(
        "http",
        url="http://example/httpx-false",
        method="GET",
        extension="httpx",
        verify=False,
    ) as response:
        assert await response.json() == {"ok": True}

    async with await run_tool(
        "http",
        url="http://example/httpx-path",
        method="GET",
        extension="httpx",
        verify="/tmp/internal-ca.pem",
    ) as response:
        assert await response.json() == {"ok": True}

    async with await run_tool(
        "http",
        url="http://example/httpx-context",
        method="GET",
        extension="httpx",
        verify=ssl_context,
    ) as response:
        assert await response.json() == {"ok": True}

    async with await run_tool(
        "http",
        url="http://example/httpx-default",
        method="GET",
        extension="httpx",
    ) as response:
        assert await response.json() == {"ok": True}

    assert client_kwargs[0]["verify"] is False
    assert client_kwargs[1]["verify"] == "/tmp/internal-ca.pem"
    assert client_kwargs[2]["verify"] is ssl_context
    assert "verify" not in client_kwargs[3]


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
async def test_http_aiohttp_verify_false_maps_to_ssl_false(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "asynctoolkit.defaults.http.aiohttp.ClientSession",
        lambda: _FakeAiohttpClientSession(calls),
    )

    async with await run_tool(
        "http",
        url="http://example/aiohttp-false",
        method="GET",
        extension="aiohttp",
        verify=False,
    ) as response:
        assert await response.json() == {"ok": True}

    assert calls[0]["kwargs"]["ssl"] is False


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
async def test_http_aiohttp_verify_context_passes_through(monkeypatch):
    calls = []
    ssl_context = ssl.create_default_context()

    monkeypatch.setattr(
        "asynctoolkit.defaults.http.aiohttp.ClientSession",
        lambda: _FakeAiohttpClientSession(calls),
    )

    async with await run_tool(
        "http",
        url="http://example/aiohttp-context",
        method="GET",
        extension="aiohttp",
        verify=ssl_context,
    ) as response:
        assert await response.json() == {"ok": True}

    assert calls[0]["kwargs"]["ssl"] is ssl_context


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
@pytest.mark.parametrize(
    ("path_kind", "expected_kwargs"),
    [
        ("file", {"cafile": "ca.pem"}),
        ("dir", {"capath": "ca-dir"}),
    ],
)
async def test_http_aiohttp_verify_path_builds_ssl_context(
    monkeypatch, tmp_path, path_kind, expected_kwargs
):
    calls = []
    context_calls = []
    created_context = ssl.create_default_context()

    monkeypatch.setattr(
        "asynctoolkit.defaults.http.aiohttp.ClientSession",
        lambda: _FakeAiohttpClientSession(calls),
    )

    def fake_create_default_context(**kwargs):
        context_calls.append(kwargs)
        return created_context

    monkeypatch.setattr(
        "asynctoolkit.defaults.http.ssl.create_default_context",
        fake_create_default_context,
    )

    if path_kind == "file":
        verify_path = tmp_path / "ca.pem"
        verify_path.write_text("dummy cert")
    else:
        verify_path = tmp_path / "ca-dir"
        verify_path.mkdir()

    async with await run_tool(
        "http",
        url="http://example/aiohttp-path",
        method="GET",
        extension="aiohttp",
        verify=str(verify_path),
    ) as response:
        assert await response.json() == {"ok": True}

    expected = {key: str(verify_path) for key in expected_kwargs}
    assert context_calls == [expected]
    assert calls[0]["kwargs"]["ssl"] is created_context


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
async def test_http_aiohttp_verify_invalid_path_raises(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setattr(
        "asynctoolkit.defaults.http.aiohttp.ClientSession",
        lambda: _FakeAiohttpClientSession(calls),
    )

    with pytest.raises(ValueError, match="verify"):
        await run_tool(
            "http",
            url="http://example/aiohttp-invalid-path",
            method="GET",
            extension="aiohttp",
            verify=str(tmp_path / "missing.pem"),
        )

    assert calls == []


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_AIOHTTP, reason="aiohttp not available")
@pytest.mark.parametrize("verify", [None, True])
async def test_http_aiohttp_verify_default_does_not_override_ssl(monkeypatch, verify):
    calls = []

    monkeypatch.setattr(
        "asynctoolkit.defaults.http.aiohttp.ClientSession",
        lambda: _FakeAiohttpClientSession(calls),
    )

    kwargs = {
        "url": "http://example/aiohttp-default",
        "method": "GET",
        "extension": "aiohttp",
    }
    if verify is not None:
        kwargs["verify"] = verify

    async with await run_tool("http", **kwargs) as response:
        assert await response.json() == {"ok": True}

    assert "ssl" not in calls[0]["kwargs"]


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_PYODIDE, reason="pyodide not available")
@pytest.mark.parametrize(
    "verify", [False, "/tmp/internal-ca.pem", ssl.create_default_context()]
)
async def test_http_pyodide_verify_rejects_unsupported_values(verify):
    with pytest.raises((ValueError, NotImplementedError), match="verify"):
        await run_tool(
            "http",
            url="https://example.invalid",
            method="GET",
            extension="pyodide",
            verify=verify,
        )


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
