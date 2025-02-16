import pytest
import asyncio

# Import the run_tool function from your package.
# Adjust the import paths if your package structure is different.
from asynctoolkit.base import run_tool
from asynctoolkit.defaults.http import HTTPTool

# Check for optional backend dependencies.
try:
    import aiohttp

    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import httpx

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

try:
    import pyodide

    HAS_PYODIDE = True
except ImportError:
    HAS_PYODIDE = False

try:
    from pytest_pyodide import run_in_pyodide, copy_files_to_pyodide

    HAS_PYODIDE_TEST = True
except ImportError:
    HAS_PYODIDE_TEST = False

# Using https://httpbin.org which echoes back data for GET requests.
TEST_URL = "https://httpbin.org/get"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extension,available",
    [
        ("aiohttp", HAS_AIOHTTP),
        ("requests", HAS_REQUESTS),
        ("httpx", HAS_HTTPX),
    ],
)
async def test_http_tool_extension(extension, available):
    if not available:
        pytest.skip(f"Extension '{extension}' not installed.")
    TEST_URL = "https://httpbin.org/get"
    async with await run_tool(
        "http",
        url=TEST_URL,
        method="GET",
        extension=extension,
    ) as response:
        status = await response.status()
        assert status == 200

        data = await response.json()
        assert "url" in data
        assert data["url"].startswith(TEST_URL)


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
        from asynctoolkit.defaults.http import HTTPTool

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


@pytest.mark.asyncio
async def test_default_extension():
    """
    When no extension is specified (i.e. extension=None), the first
    registered extension should be used.
    """
    TEST_URL = "https://httpbin.org/get"
    async with await run_tool(
        "http",
        url=TEST_URL,
        method="GET",
        extension=None,
    ) as response:
        status = await response.status()
        assert status == 200

        data = await response.json()
        assert "url" in data


@pytest.mark.asyncio
async def test_invalid_extension():
    """
    Verify that specifying an invalid extension name raises a KeyError.
    """
    TEST_URL = "https://httpbin.org/get"
    with pytest.raises(KeyError):
        async with await run_tool(
            "http",
            url=TEST_URL,
            method="GET",
            extension="nonexistent",
        ):
            pass
