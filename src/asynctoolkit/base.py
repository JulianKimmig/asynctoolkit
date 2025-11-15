from __future__ import annotations
import asyncio
import logging
from abc import ABC, abstractmethod
from typing import (
    Any,
    Callable,
    Dict,
    Type,
    TypeVar,
    Generic,
    ParamSpec,
    Awaitable,
    Union,
    List,
    Literal,
)

# -----------------------------------------------------------------------------
# Module-level Logger
# -----------------------------------------------------------------------------
logger = logging.getLogger("asynctoolkit.base")

###############################################################################
# Base Tool Interfaces
###############################################################################
R = TypeVar("R")
P = ParamSpec("P")


class AsyncTool(ABC, Generic[R]):
    """
    Abstract base class for asynchronous tools in asynctoolkit.
    Each tool must implement the asynchronous run() method.
    """

    @abstractmethod
    async def run(self, *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Execute the tool's functionality asynchronously.

        Args:
            *args: Positional arguments for the tool.
            **kwargs: Keyword arguments for the tool.

        Returns:
            The result of the tool's operation.
        """
        raise NotImplementedError("AsyncTool subclasses must implement run().")


class ExtendableTool(AsyncTool[R], Generic[R]):
    """
    An extension of AsyncTool that supports registering and retrieving
    extensions. Extensions can provide alternative backends or additional
    functionality for the tool.
    """

    _extensions: Dict[str, Callable[P, Awaitable[R]]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._extensions = {}

    @classmethod
    def register_extension(
        cls, name: str, func: Callable[P, Awaitable[R]], overwrite: bool = False
    ) -> None:
        """
        Register an extension for the tool.

        Args:
            name: A unique name for the extension.
            func: A callable that implements the extension.
            overwrite: If True, replace an existing extension with the same name.
        """
        if name in cls._extensions:
            if not overwrite:
                raise ValueError(
                    f"Extension {name!r} is already registered for tool {cls.__name__}."
                )
            else:
                logger.warning(
                    "Extension %r is already registered for tool %r; overriding.",
                    name,
                    cls.__name__,
                )
        cls._extensions[name] = func
        logger.info("Registered extension %r for tool %r", name, cls.__name__)

    @classmethod
    def get_extension(cls, name: str) -> Callable[P, Awaitable[R]]:
        """
        Retrieve a registered extension.

        Args:
            name: The name of the extension.

        Returns:
            The callable extension.

        Raises:
            KeyError: If the extension is not registered.
        """
        if name not in cls._extensions:
            raise KeyError(
                f"Extension {name!r} not registered for tool {cls.__name__}."
            )
        return cls._extensions[name]

    async def run(
        self,
        *args: P.args,
        extension: Union[List[str], str, Literal["all"], None] = None,
        **kwargs: P.kwargs,
    ) -> R:
        """
        Execute the tool's functionality asynchronously.
        It always tries to run the possible extensions in order
        and returns the first successful result.

        Args:
            *args: Positional arguments for the tool.
            **kwargs: Keyword arguments for the tool.
            extension: The extension(s) to use for the tool (keyword-only).
                If None, the first extension is used.
                If "all", all extensions are checked in order.

        Returns:
            The result of the tool's operation.
        """

        if len(self._extensions) == 0:
            raise ValueError(
                f"Tool {self.__class__.__name__} has no registered extensions."
            )
        if extension is None:
            # Use the first registered extension if none is specified.
            extension = [list(self._extensions.keys())[0]]
        if extension == "all":
            extension = list(self._extensions.keys())
        if isinstance(extension, str):
            extension = [extension]

        errors = {}
        extensions_to_try = extension
        single_extension = len(extensions_to_try) == 1
        for ext in extensions_to_try:
            ex = self.get_extension(ext)
            try:
                return await ex(*args, **kwargs)

            except Exception as exc:
                errors[ext] = exc
                logger.exception(
                    f"Error running tool {self.__class__.__name__} with extension {ext}"
                )
                if single_extension:
                    if isinstance(exc, (TypeError, ValueError)):
                        raise

        raise ValueError(
            f"Could not run tool {self.__class__.__name__} with extensions {extensions_to_try} "
            f"and args {args} and kwargs {kwargs}.\nErrors: {errors}"
        )


###############################################################################
# Tool Registry
###############################################################################
# Global registry mapping tool names to tool classes.
_TOOL_REGISTRY: Dict[str, Type[AsyncTool]] = {}


def register_tool(name: str, tool_cls: Type[AsyncTool], overwrite=False) -> None:
    """
    Register a new asynchronous tool.

    Args:
        name: Unique identifier for the tool.
        tool_cls: A subclass of AsyncTool that implements the tool.
        overwrite: If True, replace any existing tool with the same name.
    """
    if name in _TOOL_REGISTRY and not overwrite:
        raise ValueError(
            f"Tool {name!r} is already registered; use overwrite=True to override."
        )
    if name in _TOOL_REGISTRY:
        logger.warning("Tool %r is already registered; overriding.", name)
    _TOOL_REGISTRY[name] = tool_cls
    logger.info("Registered tool: %r", name)


def get_tool(name: str) -> Type[AsyncTool]:
    """
    Retrieve a registered tool by name.

    Args:
        name: The unique identifier of the tool.

    Returns:
        The tool class.

    Raises:
        KeyError: If the tool is not found.
    """
    if name not in _TOOL_REGISTRY:
        raise KeyError(f"Tool {name!r} not found in registry.")
    return _TOOL_REGISTRY[name]


async def run_tool(name: str, *args, **kwargs) -> Any:
    """
    Instantiate and run a registered tool.

    Args:
        name: The unique identifier of the tool.
        *args, **kwargs: Arguments passed to the tool's run() method.

    Returns:
        The result of the tool's run() method.
    """
    tool_cls = get_tool(name)
    tool_instance = tool_cls()
    return await tool_instance.run(*args, **kwargs)


###############################################################################
# Example Tool Implementations
###############################################################################


class FileSystemTool(AsyncTool):
    """
    Example asynchronous tool for file system operations.
    Provides basic functionality, such as listing directory contents.
    """

    async def run(self, path: str, operation: str = "list") -> Any:
        """
        Execute a file system operation.

        Args:
            path: The file or directory path.
            operation: The operation to perform (e.g., "list", "read", "write").

        Returns:
            The result of the operation.

        Raises:
            NotImplementedError: If the operation is not supported.
        """
        if operation == "list":
            # Use the event loop's executor to run a blocking call asynchronously.
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, lambda: __import__("os").listdir(path)
            )
        else:
            raise NotImplementedError(f"Operation {operation!r} is not implemented.")


# Register the FileSystemTool under the name "filesystem".
register_tool("filesystem", FileSystemTool)


###############################################################################
# Example Extension for HTTPTool Using aiohttp
###############################################################################


###############################################################################
# Future Expansion
###############################################################################
# You can add additional tools for tasks like:
#
# - Asynchronous user input (e.g., using aioconsole)
# - Asynchronous subprocess execution (via asyncio.create_subprocess_exec)
# - Email sending (using aiosmtplib)
# - Clipboard or notification handling
#
# Each tool should follow the AsyncTool interface and be registered with
# register_tool(). If a tool benefits from multiple implementations/backends,
# consider subclassing ExtendableTool and providing extension registration.
#
# For example:
#
# class EmailTool(ExtendableTool):
#     async def run(self, to: str, subject: str, body: str, **kwargs) -> Any:
#         # Use a registered backend (e.g., "aiosmtplib") to send an email.
#         backend = self.get_extension("aiosmtplib")
#         return await backend(to, subject, body, **kwargs)
#
# register_tool("email", EmailTool)
#
# This framework is designed to be extended as you add support for more tasks
# across different libraries/environments.
