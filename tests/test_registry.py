import pytest

from asynctoolkit.base import (
    register_tool,
    get_tool,
    AsyncTool,
    ExtendableTool,
)


# A simple dummy tool for testing purposes.
class DummyTool(AsyncTool):
    async def run(self):
        return "dummy_result"


@pytest.mark.asyncio
async def test_register_and_get_tool():
    # Register the dummy tool under a unique name.
    register_tool("dummy", DummyTool, overwrite=True)
    tool_cls = get_tool("dummy")
    tool_instance = tool_cls()
    result = await tool_instance.run()
    assert result == "dummy_result"


def test_register_duplicate_tool():
    # Register a dummy tool.
    register_tool("dummy_dup", DummyTool, overwrite=True)
    # Attempting to register it again without overwrite=True should raise a ValueError.
    with pytest.raises(ValueError):
        register_tool("dummy_dup", DummyTool, overwrite=False)


def _make_extendable_tool():
    class _SampleTool(ExtendableTool[str]):
        pass

    return _SampleTool


@pytest.mark.asyncio
async def test_extendable_tool_requires_extension():
    Tool = _make_extendable_tool()
    with pytest.raises(ValueError):
        await Tool().run()


@pytest.mark.asyncio
async def test_extendable_tool_runs_default_extension():
    Tool = _make_extendable_tool()

    async def ext_one(*args, **kwargs):
        return "one"

    Tool.register_extension("first", ext_one)
    result = await Tool().run()
    assert result == "one"


@pytest.mark.asyncio
async def test_extendable_tool_extension_all_recovers_from_errors():
    Tool = _make_extendable_tool()

    async def failing(*args, **kwargs):
        raise RuntimeError("boom")

    async def succeeding(*args, **kwargs):
        return "two"

    Tool.register_extension("fail", failing)
    Tool.register_extension("ok", succeeding)

    result = await Tool().run(extension="all")
    assert result == "two"


@pytest.mark.asyncio
async def test_extendable_tool_raises_when_all_extensions_fail():
    Tool = _make_extendable_tool()

    async def failing_one(*args, **kwargs):
        raise RuntimeError("one failed")

    async def failing_two(*args, **kwargs):
        raise RuntimeError("two failed")

    Tool.register_extension("one", failing_one)
    Tool.register_extension("two", failing_two)

    with pytest.raises(ValueError) as excinfo:
        await Tool().run(extension=["one", "two"])

    message = str(excinfo.value)
    assert "one" in message and "two" in message


def test_extendable_tool_get_extension_missing():
    Tool = _make_extendable_tool()
    with pytest.raises(KeyError):
        Tool.get_extension("missing")


@pytest.mark.asyncio
async def test_extendable_tool_overwrite_register_logs_warning(caplog):
    Tool = _make_extendable_tool()

    async def ext_one(*args, **kwargs):
        return "old"

    async def ext_two(*args, **kwargs):
        return "new"

    Tool.register_extension("dup", ext_one)
    with caplog.at_level("WARNING"):
        Tool.register_extension("dup", ext_two, overwrite=True)
    assert "overriding" in caplog.text

    result = await Tool().run(extension="dup")
    assert result == "new"
