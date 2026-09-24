from __future__ import annotations

import importlib
import shutil
import socket
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path, monkeypatch):
    from desk import io_utils

    original = io_utils.ROOT
    shutil.copytree(original / "configs", tmp_path / "configs")
    paths = {
        "ROOT": tmp_path,
        "CONFIG_DIR": tmp_path / "configs",
        "DATA_DIR": tmp_path / "data",
        "RAW_DIR": tmp_path / "data/raw",
        "FEATURE_DIR": tmp_path / "data/features",
        "ARTIFACT_DIR": tmp_path / "data/artifacts",
        "DB_PATH": tmp_path / "data/artifacts/desk.sqlite",
        "TRUST_PATH": tmp_path / "data/artifacts/trust.yaml",
        "REF_PATH": tmp_path / "data/artifacts/feature_reference.yaml",
        "POLICY_PATH": tmp_path / "configs/policy.md",
        "PENDING_PATH": tmp_path / "data/artifacts/policy_pending.md",
        "HISTORY_DIR": tmp_path / "data/artifacts/policy_history",
        "RUNS_PATH": tmp_path / "data/artifacts/runs.yaml",
        "REGISTRY_PATH": tmp_path / "data/artifacts/registry.yaml",
    }
    for source in (original / "src/desk").glob("*.py"):
        module = importlib.import_module(f"desk.{source.stem}")
        for name, path in paths.items():
            if hasattr(module, name) and isinstance(getattr(module, name), Path):
                monkeypatch.setattr(module, name, path)
    io_utils.ensure_dirs()

    def no_network(*args, **kwargs):
        raise AssertionError("Network access is forbidden in unit tests")

    monkeypatch.setattr(socket.socket, "connect", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
