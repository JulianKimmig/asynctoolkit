import pytest
import asyncio

from asynctoolkit.base import register_tool, get_tool, AsyncTool


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
