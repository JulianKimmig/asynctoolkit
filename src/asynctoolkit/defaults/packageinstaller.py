from typing import Optional
import importlib
import sys

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
            # reload the top-level modules of the package
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


try:
    import micropip

    async def micropip_install(
        package_name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ):
        # check if the package is already installed

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

try:
    import pip

    async def pip_install(
        package_name: str,
        version: Optional[str] = None,
        upgrade: bool = False,
    ):
        try:
            from pip._internal import main as pip_main
        except ImportError:
            # Fallback for older versions of pip
            from pip import main as pip_main

        if version:
            package_name = f"{package_name}{version}"
        pip_main(["install", package_name] + (["--upgrade"] if upgrade else []))

    PackageInstallerTool.register_extension("pip", pip_install)
except ImportError:
    pass


register_tool("packageinstaller", PackageInstallerTool)
