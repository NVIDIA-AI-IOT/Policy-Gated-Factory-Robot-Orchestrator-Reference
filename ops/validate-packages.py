# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Build and smoke-test standalone Python artifacts without running host services.

Run with Python 3.12 and the CI-pinned uv on PATH. All outputs and the installed
wheel environment live in a temporary directory outside the source checkout.
"""

from __future__ import annotations

import argparse
from email.parser import BytesParser
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile


ROOT = Path(__file__).resolve().parents[1]
PROJECTS = (
    "pgfr-spine",
    "pgfr-console",
    "packages/connector-sdk",
    "packages/conformance-kit",
    "servers/pgfr-chat",
    "servers/pgfr-workflows",
    "servers/policy-gated-factory-robot-orchestrator-reference-mcp",
)
LEGAL_FILES = ("LICENSE", "NOTICE", "THIRD-PARTY-NOTICES.md")
HATCHLING = "hatchling==1.32.0"


def run(*args: str, cwd: Path) -> None:
    subprocess.run(args, cwd=cwd, check=True)


def legal_files(*, sync: bool = False) -> None:
    for project in PROJECTS:
        for name in LEGAL_FILES:
            canonical = (ROOT / name).read_bytes()
            target = ROOT / project / name
            if sync:
                target.write_bytes(canonical)
            if not target.is_file() or target.read_bytes() != canonical:
                raise ValueError(f"{target}: run python ops/validate-packages.py --sync-legal")


def check_metadata(data: bytes, label: str) -> None:
    metadata = BytesParser().parsebytes(data)
    if metadata["License-Expression"] != "Apache-2.0":
        raise ValueError(f"{label}: missing Apache-2.0 License-Expression")
    if sorted(metadata.get_all("License-File", [])) != sorted(LEGAL_FILES):
        raise ValueError(f"{label}: missing legal file metadata")


def check_wheel(wheel: Path, project: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError(f"{wheel}: duplicate archive entries")
        metadata_name, = (name for name in names if name.endswith(".dist-info/METADATA"))
        check_metadata(archive.read(metadata_name), str(wheel))
        dist_info = metadata_name.rsplit("/", 1)[0]
        for name in LEGAL_FILES:
            if archive.read(f"{dist_info}/licenses/{name}") != (ROOT / name).read_bytes():
                raise ValueError(f"{wheel}: incorrect {name}")
        # Check actual source bytes, including Console's HTML and JavaScript.
        for source in (project / "src").rglob("*"):
            if not source.is_file() or "__pycache__" in source.parts or source.suffix == ".pyc":
                continue
            name = source.relative_to(project / "src").as_posix()
            if archive.read(name) != source.read_bytes():
                raise ValueError(f"{wheel}: missing or changed package file {name}")


SMOKE = r'''
import asyncio
import importlib
import os
from importlib.metadata import distribution
from importlib.resources import files
from pathlib import Path
import sys

import httpx
from pgfr_console.app import STATIC_DIR, build_app
from policy_gated_factory_robot_orchestrator_reference.floor.service import build_app as build_floor_app

projects = {
    "policy_gated_factory_robot_orchestrator_reference": "policy_gated_factory_robot_orchestrator_reference",
    "pgfr-console": "pgfr_console.app",
    "pgfr-connector-sdk": "pgfr_connector_sdk",
    "pgfr-conformance": "pgfr_conformance.kit",
    "pgfr-chat": "pgfr_chat.app",
    "pgfr-workflows": "pgfr_workflows.app",
    "pgfr-mcp": "pgfr_mcp.server",
}
for name, module_name in projects.items():
    module = importlib.import_module(module_name)
    assert Path(module.__file__).resolve().is_relative_to(Path(sys.prefix)), module_name
    dist = distribution(name)
    assert dist.read_text("direct_url.json") is not None, name
    assert '"editable": true' not in dist.read_text("direct_url.json"), name
    for entry in dist.entry_points:
        if entry.group == "console_scripts":
            assert callable(entry.load()), entry.name
            assert (Path(sys.executable).parent / entry.name).is_file(), entry.name

async def check_console():
    # ASGITransport does not start lifespan/background upstream polling.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_app()), base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert response.content == (STATIC_DIR / "index.html").read_bytes()
        for asset in STATIC_DIR.rglob("*"):
            if asset.is_file():
                response = await client.get("/static/" + asset.relative_to(STATIC_DIR).as_posix())
                assert response.status_code == 200, asset
                assert response.content == asset.read_bytes(), asset

async def check_floor():
    # Exercise standalone startup with the bundled scene, never host settings.
    os.environ["PGFR_FLOOR_BACKEND"] = "mock"
    for name in ("PGFR_FLOOR_SCENE", "PGFR_FLOOR_POLICY", "PGFR_JOURNAL_DIR"):
        os.environ.pop(name, None)
    resource = files("policy_gated_factory_robot_orchestrator_reference.floor").joinpath("scene.example.yaml")
    assert resource.is_file(), "default scene missing from installed wheel"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=build_floor_app()), base_url="http://test") as client:
        response = await client.get("/v1/health")
        assert response.status_code == 200, response.text
        assert response.json()["backend"] == "mock"
        response = await client.post("/v1/floor-state", json={})
        assert response.status_code == 200, response.text
        assert {endpoint["id"] for endpoint in response.json()["endpoints"]} == {"amr_franka_1", "amr_franka_2", "conveyor_1"}
        response = await client.post("/v1/perceive", json={"target": "table_1"})
        assert response.status_code == 200, response.text
        assert response.json()["counts"] == {"red": 2, "green": 1}

asyncio.run(check_console())
asyncio.run(check_floor())
print("Installed-wheel imports, entry points, Console HTTP assets and default floor startup/read endpoints passed.")
'''


def validate(work: Path) -> None:
    wheels = []
    for name in (*PROJECTS, "connectors/TEMPLATE", "servers/TEMPLATE"):
        project = ROOT / name
        config = tomllib.loads((project / "pyproject.toml").read_text())
        if config["build-system"]["requires"] != [HATCHLING]:
            raise ValueError(f"{project}: expected pinned {HATCHLING}")
        if name not in PROJECTS:
            continue
        output = work / name.replace("/", "-")
        output.mkdir()
        print(f"Validating {name}", flush=True)
        # Explicitly rebuild from the source archive in an unrelated directory:
        # package metadata/resources must not depend on monorepo siblings.
        run("uv", "build", "--no-sources", "--sdist", str(project), "--out-dir", str(output), cwd=work)
        sdist, = output.glob("*.tar.gz")
        with tarfile.open(sdist) as archive:
            names = archive.getnames()
            if len(names) != len(set(names)):
                raise ValueError(f"{sdist}: duplicate archive entries")
            prefix, = {name.split("/", 1)[0] for name in names}
            for legal in LEGAL_FILES:
                member = archive.getmember(f"{prefix}/{legal}")
                if not member.isfile():
                    raise ValueError(f"{sdist}: {legal} must be a regular file")
                stream = archive.extractfile(member)
                if stream is None or stream.read() != (ROOT / legal).read_bytes():
                    raise ValueError(f"{sdist}: incorrect {legal}")
            metadata = archive.extractfile(f"{prefix}/PKG-INFO")
            if metadata is None:
                raise ValueError(f"{sdist}: missing metadata")
            check_metadata(metadata.read(), str(sdist))
        run("uv", "build", "--no-sources", "--wheel", str(sdist), "--out-dir", str(output), cwd=work)
        wheel, = output.glob("*.whl")
        check_wheel(wheel, project)
        wheels.append(str(wheel))
        direct = output / "direct"
        run("uv", "build", "--no-sources", "--wheel", str(project), "--out-dir", str(direct), cwd=work)
        direct_wheel, = direct.glob("*.whl")
        check_wheel(direct_wheel, project)

    environment = work / "installed"
    run("uv", "venv", "--python", sys.executable, str(environment), cwd=work)
    python = environment / "bin/python"
    # Resolve published dependency metadata as a wheel consumer would. Component
    # locks are tested separately; combining them can require conflicting pins.
    # All local wheels are supplied together so Workflows resolves the built Chat.
    run("uv", "pip", "install", "--python", str(python), *wheels, cwd=work)
    run("uv", "pip", "check", "--python", str(python), cwd=work)
    run(str(python), "-I", "-c", SMOKE, cwd=work)
    for command in ("policy_gated_factory_robot_orchestrator_reference", "pgfr-conformance"):
        run(str(environment / "bin" / command), "--help", cwd=work)
    print(f"All {len(PROJECTS)} source distributions and installed wheels passed.", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync-legal", action="store_true", help="copy canonical root legal files into all packages, then exit")
    args = parser.parse_args()
    legal_files(sync=args.sync_legal)
    if not args.sync_legal:
        with tempfile.TemporaryDirectory(prefix="pgfr-packages-") as work:
            validate(Path(work))


if __name__ == "__main__":
    main()
