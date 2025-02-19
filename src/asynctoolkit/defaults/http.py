from __future__ import annotations
from contextlib import asynccontextmanager, AbstractAsyncContextManager
from typing import Any, Optional
from collections.abc import AsyncIterable
from abc import ABC, abstractmethod
from ..base import register_tool, ExtendableTool


###############################################################################
# AsyncResponse Interface
###############################################################################
class AsyncResponse(ABC):
    """
    Abstract base class defining the asynchronous interface for HTTP responses.
    """

    class AsyncResponseError(Exception):
        """
        Base class for exceptions raised by AsyncResponse implementations.
        """

    class HTTPError(AsyncResponseError):
        """
        Exception raised for HTTP errors.
        """

        def __init__(self, message, response: AsyncResponse):
            super().__init__(message)
            self.response = response

    def __init__(self, url, response):
        self.response: Any = response
        self.url = url

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

    @abstractmethod
    async def reason(self) -> str:
        """
        Asynchronously return the HTTP reason phrase.
        """

    @abstractmethod
    async def iter_content(self, chunk_size: int = 1024) -> AsyncIterable[bytes]:
        """
        Asynchronously return an iterator over the response content.
        """

    async def raise_for_status(self):
        """
        Raise an exception if the response status code is not a successful one.
        """

        status_code = await self.status()
        reason = await self.reason()
        http_error_msg = ""
        if isinstance(self.reason, bytes):
            # We attempt to decode utf-8 first because some servers
            # choose to localize their reason strings. If the string
            # isn't utf-8, we fall back to iso-8859-1 for all other
            # encodings. (See PR #3538)
            try:
                reason = reason.decode("utf-8")
            except UnicodeDecodeError:
                reason = reason.decode("iso-8859-1")

        if 400 <= status_code < 500:
            http_error_msg = f"{status_code} Client Error: {reason} for url: {self.url}"

        elif 500 <= status_code < 600:
            http_error_msg = f"{status_code} Server Error: {reason} for url: {self.url}"

        if http_error_msg:
            raise AsyncResponse.HTTPError(http_error_msg, response=self)


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
        stream: bool = False,
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
            stream=stream,
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

        response: aiohttp.ClientResponse

        def __init__(self, response: aiohttp.ClientResponse):
            super().__init__(response.url, response)

        async def text(self) -> str:
            return await self.response.text()

        async def json(self) -> Any:
            return await self.response.json()

        async def status(self) -> int:
            return self.response.status

        async def headers(self) -> dict:
            return self.response.headers

        async def reason(self) -> str:
            return self.response.reason

        async def iter_content(self, chunk_size: int = 1024) -> AsyncIterable[bytes]:
            async for chunk in self.response.content.iter_chunked(chunk_size):
                yield chunk

    async def _register_aiohttp_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        stream: bool = False,  # aiohttp does not need stream parameter
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

        response: requests.Response

        def __init__(self, response: requests.Response):
            super().__init__(response.url, response)

        async def text(self) -> str:
            return self.response.text

        async def json(self) -> Any:
            return self.response.json()

        async def status(self) -> int:
            return self.response.status_code

        async def headers(self) -> dict:
            return self.response.headers

        async def reason(self) -> str:
            return self.response.reason

        async def iter_content(self, chunk_size: int = 1024) -> AsyncIterable[bytes]:
            for chunk in self.response.iter_content(chunk_size):
                yield chunk

    async def _register_requests_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        stream: bool = False,
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
                stream=stream,
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

        response: httpx.Response

        def __init__(self, response: httpx.Response):
            super().__init__(response.url, response)

        async def text(self) -> str:
            return self.response.text

        async def json(self) -> Any:
            return self.response.json()

        async def status(self) -> int:
            return self.response.status_code

        async def headers(self) -> dict:
            return self.response.headers

        async def reason(self) -> str:
            return self.response.reason_phrase

        async def iter_content(self, chunk_size: int = 1024) -> AsyncIterable[bytes]:
            async for chunk in self.response.aiter_bytes(chunk_size):
                yield chunk

    async def _register_httpx_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        stream: bool = False,  # httpx does not need stream parameter
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
            super().__init__(response.url, response)

        async def text(self) -> str:
            return await self.response.text()

        async def json(self) -> Any:
            return await self.response.json()

        async def status(self) -> int:
            return self.response.status

        async def headers(self) -> dict:
            # Convert headers to a standard Python dict.
            return dict(self.response.headers)

        async def reason(self) -> str:
            return self.response.status_text

        async def iter_content(self, chunk_size: int = 1024) -> AsyncIterable[bytes]:
            b = []
            async for chunk in self.response.js_response.body:
                chunk = list(chunk.to_py())
                b.extend(chunk)
                while len(b) >= chunk_size:
                    # b is of type list[int], so we need to convert it to bytes.
                    yield bytes(b[:chunk_size])
                    b = b[chunk_size:]
            if b:
                yield bytes(b)


    async def _register_pyodide_request(
        url: str,
        method: str = "GET",
        headers: Optional[dict] = None,
        params: Optional[dict] = None,
        data: Optional[Any] = None,
        json: Optional[Any] = None,
        timeout: int = 10,
        stream: bool = False,  # Pyodide fetch does not need stream parameter
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
