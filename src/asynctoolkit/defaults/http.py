from contextlib import asynccontextmanager, AbstractAsyncContextManager
from typing import Any, Optional
from abc import ABC, abstractmethod
from ..base import register_tool, ExtendableTool


###############################################################################
# AsyncResponse Interface
###############################################################################
class AsyncResponse(ABC):
    """
    Abstract base class defining the asynchronous interface for HTTP responses.
    """

    @abstractmethod
    async def text(self) -> str:
        """
        Asynchronously return the response body as a string.
        """
        pass

    @abstractmethod
    async def json(self) -> Any:
        """
        Asynchronously return the JSON-decoded content of the response.
        """
        pass

    @abstractmethod
    async def status(self) -> int:
        """
        Asynchronously return the HTTP status code.
        """
        pass

    @abstractmethod
    async def headers(self) -> dict:
        """
        Asynchronously return the HTTP headers.
        """
        pass


class HTTPTool(ExtendableTool[AbstractAsyncContextManager[AsyncResponse]]):
    """
    Example asynchronous tool for performing HTTP requests.
    This tool uses registered extensions to support different HTTP backends.
    """

    async def run(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        extension=None,
    ) -> AbstractAsyncContextManager[AsyncResponse]:
        """
        Execute an HTTP request using a registered backend extension.

        Args:
            url: The URL to request.
            method: HTTP method to use (e.g., "GET", "POST", etc.).
            headers: Optional HTTP headers.
            params: Optional query parameters.
            data: Optional request body data.
            json: Optional JSON data to send in the request body.
            timeout: Request timeout in seconds.

        Returns:
            The result of the HTTP request.
        """

        if data is not None and json is not None:
            raise ValueError(
                "data and json parameters can not be used at the same time"
            )

        return await super().run(
            url=url,
            method=method,
            headers=headers,
            params=params,
            data=data,
            json=json,
            timeout=timeout,
            extension=extension,
        )


# Register the HTTPTool under the name "http".
register_tool("http", HTTPTool)


###############################################################################
# aiohttp Implementation
###############################################################################
try:
    import aiohttp

    class AiohttpResponse(AsyncResponse):
        """
        AsyncResponse implementation wrapping aiohttp.ClientResponse.
        """

        def __init__(self, response: aiohttp.ClientResponse):
            self.response = response

        async def text(self) -> str:
            return await self.response.text()

        async def json(self) -> Any:
            return await self.response.json()

        async def status(self) -> int:
            return self.response.status

        async def headers(self) -> dict:
            return self.response.headers

    async def _register_aiohttp_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        **kwargs,
    ) -> AbstractAsyncContextManager[AsyncResponse]:
        """
        Perform an HTTP request using aiohttp.
        """

        @asynccontextmanager
        async def _request_context():
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    json=json,
                    timeout=timeout,
                    **kwargs,
                ) as response:
                    yield AiohttpResponse(response)

        return _request_context()

    HTTPTool.register_extension("aiohttp", _register_aiohttp_request)
except ImportError:
    pass

###############################################################################
# requests Implementation (Synchronous, wrapped for async)
###############################################################################
try:
    import requests

    class RequestsResponse(AsyncResponse):
        """
        AsyncResponse implementation wrapping requests.Response.

        Note:
            This implementation executes synchronously, so it may block the event loop.
        """

        def __init__(self, response: requests.Response):
            self.response = response

        async def text(self) -> str:
            return self.response.text

        async def json(self) -> Any:
            return self.response.json()

        async def status(self) -> int:
            return self.response.status_code

        async def headers(self) -> dict:
            return self.response.headers

    async def _register_requests_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        **kwargs,
    ) -> AbstractAsyncContextManager[AsyncResponse]:
        """
        Perform an HTTP request using the requests library.
        """

        @asynccontextmanager
        async def _request_context():
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                json=json,
                timeout=timeout,
                **kwargs,
            )
            yield RequestsResponse(response)

        return _request_context()

    HTTPTool.register_extension("requests", _register_requests_request)
except ImportError:
    pass

###############################################################################
# httpx Implementation
###############################################################################
try:
    import httpx

    class HttpxResponse(AsyncResponse):
        """
        AsyncResponse implementation wrapping httpx.Response.
        """

        def __init__(self, response: httpx.Response):
            self.response = response

        async def text(self) -> str:
            return self.response.text

        async def json(self) -> Any:
            return self.response.json()

        async def status(self) -> int:
            return self.response.status_code

        async def headers(self) -> dict:
            return self.response.headers

    async def _register_httpx_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        **kwargs,
    ) -> AbstractAsyncContextManager[HttpxResponse]:
        """
        Perform an HTTP request using httpx.
        """

        @asynccontextmanager
        async def _request_context():
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    params=params,
                    data=data,
                    json=json,
                    **kwargs,
                )
                yield HttpxResponse(response)

        return _request_context()

    HTTPTool.register_extension("httpx", _register_httpx_request)
except ImportError:
    pass

###############################################################################
# Pyodide fetch Implementation
###############################################################################
try:
    # In Pyodide environments, pyodide.http provides pyfetch.
    from pyodide.http import pyfetch
    from urllib.parse import urlencode, urlsplit, urlunsplit
    import json as json_lib

    class PyodideResponse(AsyncResponse):
        """
        AsyncResponse implementation wrapping Pyodide's fetch response.
        """

        def __init__(self, response):
            self.response = response

        async def text(self) -> str:
            return await self.response.text()

        async def json(self) -> Any:
            return await self.response.json()

        async def status(self) -> int:
            return self.response.status

        async def headers(self) -> dict:
            # Convert headers to a standard Python dict.
            return dict(self.response.headers)

    async def _register_pyodide_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        **kwargs,
    ) -> AbstractAsyncContextManager[AsyncResponse]:
        """
        Perform an HTTP request using Pyodide's fetch API.

        Note:
            - If 'params' is provided, they are URL-encoded and appended to the URL.
            - If 'json' is provided, it is serialized to JSON and the appropriate
              Content-Type header is set.
        """

        @asynccontextmanager
        async def _request_context():
            nonlocal url, headers, params, data, json, timeout, kwargs

            # Append query parameters if provided.
            if params:
                scheme, netloc, path, query, fragment = urlsplit(url)
                extra = urlencode(params)
                query = f"{query}&{extra}" if query else extra
                url = urlunsplit((scheme, netloc, path, query, fragment))

            # Prepare request body.
            body = None
            if json is not None:
                body = json_lib.dumps(json)
                headers = headers or {}
                headers.setdefault("Content-Type", "application/json")
            elif data is not None:
                body = data

            response = await pyfetch(
                url,
                headers=headers,
                method=method,
                timeout=timeout,
                body=body,
                **kwargs,
            )
            yield PyodideResponse(response)

        return _request_context()

    HTTPTool.register_extension("pyodide", _register_pyodide_request)
except ImportError:
    pass
