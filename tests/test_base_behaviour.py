import asyncio
import logging
from typing import Any

import pytest

from asynctoolkit.base import (
    AsyncTool,
    ExtendableTool,
    FileSystemTool,
    get_tool,
    register_tool,
    run_tool,
)
from asynctoolkit.defaults.http import AsyncResponse


class PassthroughResponse(AsyncResponse):
    def __init__(self):
        super().__init__("http://test", None)

    async def text(self) -> str:
        return await super().text()

    async def json(self) -> Any:
        return await super().json()

    async def status(self) -> int:
        return await super().status()

    async def headers(self) -> dict:
        return await super().headers()

    async def reason(self) -> str:
        return await super().reason()

    async def iter_content(self, chunk_size: int = 1024):
        await super().iter_content(chunk_size)
        if False:  # pragma: no cover - required to satisfy async generator syntax
            yield b""

    async def content(self) -> bytes:
        return await super().content()


class StaticResponse(AsyncResponse):
    def __init__(self, status_code: int, reason: Any):
        super().__init__("http://static", None)
        self._status = status_code
        self._reason = reason

    async def text(self) -> str:
        return ""

    async def json(self) -> Any:
        return {}

    async def status(self) -> int:
        return self._status

    async def headers(self) -> dict:
        return {}

    async def reason(self) -> Any:
        return self._reason

    async def iter_content(self, chunk_size: int = 1024):
        yield b""

    async def content(self) -> bytes:
        return b""


def make_tool():
    class LocalTool(ExtendableTool[int]):
        pass

    return LocalTool


@pytest.mark.asyncio
async def test_async_response_base_methods_raise():
    resp = PassthroughResponse()
    with pytest.raises(NotImplementedError):
        await resp.text()
    with pytest.raises(NotImplementedError):
        await resp.json()
    with pytest.raises(NotImplementedError):
        await resp.status()
    with pytest.raises(NotImplementedError):
        await resp.headers()
    with pytest.raises(NotImplementedError):
        await resp.reason()
    with pytest.raises(NotImplementedError):
        await resp.content()
    with pytest.raises(NotImplementedError):
        agen = resp.iter_content()
        await agen.__anext__()


@pytest.mark.asyncio
async def test_async_response_raise_for_status_messages():
    client = StaticResponse(404, b"Bad\xff")
    with pytest.raises(AsyncResponse.HTTPError) as exc:
        await client.raise_for_status()
    assert "Client Error" in str(exc.value)

    server = StaticResponse(502, "Down")
    with pytest.raises(AsyncResponse.HTTPError) as exc:
        await server.raise_for_status()
    assert "Server Error" in str(exc.value)

    ok = StaticResponse(200, "OK")
    await ok.raise_for_status()


@pytest.mark.asyncio
async def test_async_tool_run_must_be_overridden():
    class IncompleteTool(AsyncTool):
        async def run(self):
            return await super().run()

    with pytest.raises(NotImplementedError):
        await IncompleteTool().run()


@pytest.mark.asyncio
async def test_extendable_tool_requires_extension():
    LocalTool = make_tool()
    with pytest.raises(ValueError):
        await LocalTool().run()


@pytest.mark.asyncio
async def test_extendable_tool_extension_flow():
    LocalTool = make_tool()

    async def fail():
        raise RuntimeError("boom")

    async def succeed():
        return 42

    LocalTool.register_extension("fail", fail)
    LocalTool.register_extension("ok", succeed)

    result = await LocalTool().run(extension="all")
    assert result == 42


@pytest.mark.asyncio
async def test_extendable_tool_uses_first_extension_by_default():
    LocalTool = make_tool()

    async def first():
        return "first"

    async def second():
        return "second"

    LocalTool.register_extension("first", first)
    LocalTool.register_extension("second", second)

    assert await LocalTool().run() == "first"


@pytest.mark.asyncio
async def test_extendable_tool_all_failures_logged(caplog):
    caplog.set_level(logging.ERROR)
    LocalTool = make_tool()

    async def fail():
        raise RuntimeError("fail")

    LocalTool.register_extension("fail", fail)

    with pytest.raises(ValueError):
        await LocalTool().run(extension="fail")
    assert "fail" in caplog.text


def test_register_extension_overwrite():
    LocalTool = make_tool()

    async def noop():
        return 1

    LocalTool.register_extension("noop", noop)
    with pytest.raises(ValueError):
        LocalTool.register_extension("noop", noop)
    LocalTool.register_extension("noop", noop, overwrite=True)


def test_get_extension_missing():
    LocalTool = make_tool()
    with pytest.raises(KeyError):
        LocalTool.get_extension("missing")


def test_register_tool_overwrite_logs(caplog):
    class Dummy(AsyncTool):
        async def run(self):
            return "ok"

    register_tool("dummy-tool", Dummy, overwrite=True)
    caplog.set_level(logging.WARNING)
    register_tool("dummy-tool", Dummy, overwrite=True)
    assert "overriding" in caplog.text


def test_get_tool_missing():
    with pytest.raises(KeyError):
        get_tool("does-not-exist")


@pytest.mark.asyncio
async def test_run_tool_success():
    class EchoTool(AsyncTool):
        async def run(self, value):
            return value * 2

    register_tool("echo-tool", EchoTool, overwrite=True)
    assert await run_tool("echo-tool", 3) == 6


@pytest.mark.asyncio
async def test_filesystem_tool_operations(tmp_path):
    (tmp_path / "file.txt").write_text("hello")
    tool = FileSystemTool()
    listing = await tool.run(str(tmp_path))
    assert "file.txt" in listing
    with pytest.raises(NotImplementedError):
        await tool.run(str(tmp_path), operation="delete")
