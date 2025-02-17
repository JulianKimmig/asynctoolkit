import pytest
import asyncio
import importlib
import importlib.metadata

# Import the run_tool function from your package.
# Adjust the import paths if your package structure is different.
from asynctoolkit.base import run_tool
from asynctoolkit.defaults.packageinstaller import PackageInstallerTool

try:
    from pytest_pyodide import run_in_pyodide, copy_files_to_pyodide
    from pathlib import Path

    HAS_PYODIDE_TEST = (
        True and (Path(__file__).parent.parent.parent / "pyodide").exists()
    )
except ImportError:
    HAS_PYODIDE_TEST = False


@pytest.mark.asyncio
async def test_package_installer_extension():
    await PackageInstallerTool().run("colorama", version="<0.4.6")

    dist = importlib.metadata.distribution("colorama")
    assert dist.version == "0.4.5", dist.version

    await PackageInstallerTool().run("colorama", version="==0.4.6", upgrade=True)
    dist = importlib.metadata.distribution("colorama")
    assert dist.version == "0.4.6", dist.version


if HAS_PYODIDE_TEST:

    @copy_files_to_pyodide(
        file_list=[("src/asynctoolkit", "asynctoolkit")],
        install_wheels=True,
        recurse_directories=True,
    )
    @run_in_pyodide
    async def test_package_installer_extension_pyodide(selenium):
        import importlib
        import importlib.metadata
        from asynctoolkit.defaults.packageinstaller import PackageInstallerTool

        await PackageInstallerTool().run("colorama", version="<0.4.6")

        dist = importlib.metadata.distribution("colorama")
        assert dist.version == "0.4.5", dist.version

        await PackageInstallerTool().run("colorama", version="==0.4.6", upgrade=True)
        dist = importlib.metadata.distribution("colorama")
        assert dist.version == "0.4.6", dist.version
