# AsyncToolkit

**AsyncToolkit** is a lightweight, extensible framework for building and running asynchronous tools in Python. It provides a unified interface for executing asynchronous operations, such as HTTP requests and file system operations, with support for multiple backends. Out of the box, AsyncToolkit comes with several HTTP backends (using libraries such as `aiohttp`, `httpx`, `requests`, and even `pyodide` for browser-based Python environments) and a file system tool. You can also easily register your own custom tools and extensions.

## Features

- **Unified Async Interface:** Standardized API for executing asynchronous operations.
- **Multiple HTTP Backends:** Choose from `aiohttp`, `httpx`, `requests` (wrapped for async), or `pyodide` (in browser environments).
- **Extendable:** Easily register and retrieve custom tools and extensions.
- **Built-in Tools:** Includes sample tools for common tasks like HTTP requests and file system operations.
- **Test Suite:** Comprehensive tests using `pytest` and `tox` to ensure reliability.

## Installation

AsyncToolkit requires Python 3.10 or later. You can install the package and its optional dependencies using pip:

```bash
# Install the core package
pip install asynctoolkit

# For HTTP functionality, install one or more of the following:
pip install aiohttp        # For aiohttp backend
pip install httpx          # For httpx backend
pip install requests       # For requests backend
pip install pyodide        # For pyodide backend (if running in a Pyodide environment)
```

## Quick Start

Here’s a brief example demonstrating how to use AsyncToolkit to perform an HTTP GET request and list directory contents:

```python
import asyncio
from asynctoolkit.base import run_tool

async def main():
    # Example 1: File System Operation
    # Using the "filesystem" tool to list directory contents.
    file_list = await run_tool("filesystem", path=".", operation="list")
    print("Directory Contents:", file_list)

    # Example 2: HTTP Request
    # Using the "http" tool with the default (first registered) HTTP backend.
    TEST_URL = "https://httpbin.org/get"
    async with await run_tool("http", url=TEST_URL, method="GET") as response:
        status = await response.status()
        data = await response.json()
        print("HTTP Status:", status)
        print("Response JSON:", data)

if __name__ == "__main__":
    asyncio.run(main())

```

## Specifying HTTP Extensions

AsyncToolkit's HTTP tool supports multiple extensions. You can explicitly choose which backend to use by specifying the extension parameter:

```python
# Example using the aiohttp backend explicitly
async with await run_tool("http", url="https://httpbin.org/get", method="GET", extension="aiohttp") as response:
    print("HTTP Status (aiohttp):", await response.status())

```

If no extension is specified, the tool will default to the first registered extension.

## Extending AsyncToolkit

You can easily create and register your own asynchronous tools or extend existing ones.

### Creating a Custom Tool

Define a new tool by subclassing AsyncTool and implement the asynchronous run() method:

```python
from asynctoolkit.base import AsyncTool, register_tool

class MyCustomTool(AsyncTool):
    async def run(self, *args, **kwargs):
        # Your custom async operation here
        return "custom_result"

# Register the custom tool under a unique name
register_tool("my_custom", MyCustomTool)

# Running the custom tool later:
import asyncio
from asynctoolkit.base import run_tool

async def run_my_tool():
    result = await run_tool("my_custom")
    print(result)  # Outputs: custom_result

asyncio.run(run_my_tool())

```

### Adding Extensions

For tools that support multiple implementations (like the HTTP tool), you can register extensions. Each extension is simply an asynchronous function that conforms to the tool’s expected interface. See the built-in HTTP tool in `asynctoolkit.defaults.http` for examples using `aiohttp`, `httpx`, `requests`, and `pyodide`.

## License

This project is licensed under the terms of the
[MIT license](LICENCE).
