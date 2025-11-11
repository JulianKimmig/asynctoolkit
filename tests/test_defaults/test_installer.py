import asyncio
import importlib
import importlib.metadata
import sys
import types
from pathlib import Path

import pytest

from asynctoolkit.defaults.packageinstaller import PackageInstallerTool

try:
    from pytest_pyodide import copy_files_to_pyodide, run_in_pyodide

    HAS_PYODIDE_TEST = (Path(__file__).parent.parent.parent / "pyodide").exists()
except ImportError:  # pragma: no cover - only available in CI environments
    HAS_PYODIDE_TEST = False


@pytest.fixture()
def recorded_installer():
    calls = []

    async def installer(package_name: str, version=None, upgrade=False):
        calls.append(
            {
                "package_name": package_name,
                "version": version,
                "upgrade": upgrade,
            }
        )

    PackageInstallerTool.register_extension(
        "test-installer",
        installer,
        overwrite=True,
    )
    return calls


@pytest.mark.asyncio
async def test_package_installer_version_prefix(recorded_installer):
    tool = PackageInstallerTool()
    await tool.run("demo", version="0.1.0", extension="test-installer")
    await tool.run("demo", version=">=0.2.0", extension="test-installer")

    assert recorded_installer[0]["version"] == "==0.1.0"
    assert recorded_installer[1]["version"] == ">=0.2.0"


@pytest.mark.asyncio
async def test_package_installer_upgrade_reload(monkeypatch, recorded_installer):
    tool = PackageInstallerTool()
    module = types.ModuleType("reload_me")
    sys.modules["reload_me"] = module

    class DummyDist:
        def read_text(self, name):
            assert name == "top_level.txt"
            return "reload_me\n"

    reloaded = []

    def fake_reload(mod):
        reloaded.append(mod.__name__)
        return mod

    monkeypatch.setattr(importlib.metadata, "distribution", lambda pkg: DummyDist())
    monkeypatch.setattr(importlib, "reload", fake_reload)

    await tool.run(
        "demo",
        version="1.0.0",
        upgrade=True,
        extension="test-installer",
    )

    assert recorded_installer[-1]["upgrade"] is True
    assert reloaded == ["reload_me"]

    sys.modules.pop("reload_me", None)


@pytest.mark.asyncio
async def test_package_installer_reload_errors_are_swallowed(
    monkeypatch, recorded_installer
):
    tool = PackageInstallerTool()
    module = types.ModuleType("reload_fail")
    sys.modules["reload_fail"] = module

    class DummyDist:
        def read_text(self, name):
            return "reload_fail\n"

    monkeypatch.setattr(importlib.metadata, "distribution", lambda pkg: DummyDist())

    def failing_reload(mod):
        raise RuntimeError("boom")

    monkeypatch.setattr(importlib, "reload", failing_reload)

    await tool.run(
        "demo",
        upgrade=True,
        extension="test-installer",
    )

    sys.modules.pop("reload_fail", None)


@pytest.mark.asyncio
async def test_package_installer_pip_invocation(monkeypatch):
    captured = {}

    class DummyProcess:
        def __init__(self, command):
            captured["command"] = command

        async def communicate(self):
            return b"done", b""

    async def fake_shell(command, stderr=None, stdout=None):
        return DummyProcess(command)

    monkeypatch.setattr(asyncio, "create_subprocess_shell", fake_shell)

    tool = PackageInstallerTool()
    await tool.run(
        "somepackage",
        version="1.2.3",
        upgrade=True,
        extension="pip",
    )

    assert "--upgrade" in captured["command"]
    assert '"somepackage==1.2.3"' in captured["command"]


if HAS_PYODIDE_TEST:

    @copy_files_to_pyodide(
        file_list=[("src/asynctoolkit", "asynctoolkit")],
        install_wheels=True,
        recurse_directories=True,
    )
    @run_in_pyodide
    async def test_package_installer_extension_pyodide(selenium):
        from asynctoolkit.defaults.packageinstaller import PackageInstallerTool

        await PackageInstallerTool().run("colorama", version="<0.4.6")

        dist = importlib.metadata.distribution("colorama")
        assert dist.version == "0.4.5", dist.version

        await PackageInstallerTool().run("colorama", version="==0.4.6", upgrade=True)
        dist = importlib.metadata.distribution("colorama")
        assert dist.version == "0.4.6", dist.version
