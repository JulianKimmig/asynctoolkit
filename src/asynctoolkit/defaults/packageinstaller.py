from typing import Optional
import importlib
import sys
import asyncio

from ..base import register_tool, ExtendableTool


class PackageInstallerTool(ExtendableTool[None]):
    async def run(
        self,
        package_name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ):
        # If a specific version is requested, modify the command accordingly.
        if version:
            # If the version string already starts with a comparison operator, use it directly.
            if version[0] in ("=", "<", ">", "!"):
                version = version
            else:
                version = "==" + version

        res = await super().run(
            package_name=package_name,
            version=version,
            upgrade=upgrade,
        )

        if upgrade:
            # Reload the top-level modules of the package.
            try:
                dist = importlib.metadata.distribution(package_name)
                top_level_modules = dist.read_text("top_level.txt").splitlines()
                for mod in top_level_modules:
                    if mod in sys.modules:
                        try:
                            importlib.reload(sys.modules[mod])
                        except Exception:
                            pass
            except Exception:
                pass

        return res


# Micropip Extension
try:
    import micropip

    async def micropip_install(
        package_name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ):
        # Check if the package is already installed.
        try:
            importlib.metadata.distribution(package_name)
            if upgrade:
                micropip.uninstall(package_name)
            else:
                return
        except importlib.metadata.PackageNotFoundError:
            pass

        if version:
            package_name = f"{package_name}{version}"
        await micropip.install(package_name)

    if sys.platform == "emscripten":
        PackageInstallerTool.register_extension("micropip", micropip_install)
except ImportError:
    pass


# Pip Extension
try:

    async def pip_install(
        package_name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ):
        if version:
            package_name = f'"{package_name}{version}"'
        args = ["install", package_name] + (["--upgrade"] if upgrade else [])
        # Run pip_main in a separate thread to avoid blocking the event loop.
        cmd = [sys.executable, "-m", "pip"] + args
        print(
            " ".join(cmd),
        )
        proc = await asyncio.create_subprocess_shell(
            " ".join(cmd),
            stderr=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()
        print(stdout.decode())
        print(stderr.decode())

    PackageInstallerTool.register_extension("pip", pip_install)
except ImportError:
    pass


register_tool("packageinstaller", PackageInstallerTool)
