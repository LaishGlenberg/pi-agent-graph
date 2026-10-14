"""Tests for pi-cli config loading."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from pi_agent_graph import loader as loader_mod
from pi_agent_graph.errors import (
    ConfigNotFoundError,
    ConfigParseError,
    PiAgentGraphError,
    PiCliNotFoundError,
    SavedConfigNotFoundError,
)
from pi_agent_graph.loader import (
    ConfigLoader,
    default_config_dir,
    parse_dry_run,
    resolve_active_config,
    resolve_config_path,
)


def write_config(path: Path, data: object) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in ("PI_CLI_CONFIG", "PI_CLI_CONFIG_DIR", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(var, raising=False)
    return monkeypatch


# -- path resolution -------------------------------------------------------
def test_resolve_config_path_explicit_file(tmp_path):
    path = tmp_path / "config.json"
    assert resolve_config_path(path) == path


def test_resolve_config_path_directory(tmp_path):
    assert resolve_config_path(tmp_path) == tmp_path / "config.json"


def test_resolve_config_path_env_file(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_CLI_CONFIG", str(tmp_path / "c.json"))
    assert resolve_config_path() == tmp_path / "c.json"


def test_resolve_config_path_config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PI_CLI_CONFIG_DIR", str(tmp_path))
    assert resolve_config_path() == tmp_path / "config.json"


def test_resolve_config_path_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert resolve_config_path() == tmp_path / "pi-cli" / "config.json"


def test_default_config_dir_home(monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/fakehome")))
    assert default_config_dir() == Path("/fakehome/.config/pi-cli")


def test_resolve_active_config_follows_path_pointer(tmp_path):
    target_dir = tmp_path / "other"
    target_dir.mkdir()
    write_config(target_dir / "config.json", {"agents": {"x": "pi"}})
    root = write_config(tmp_path / "config.json", {"path": str(target_dir)})
    assert resolve_active_config(root) == target_dir / "config.json"


def test_resolve_active_config_ignores_missing_pointer_target(tmp_path):
    root = write_config(tmp_path / "config.json", {"path": str(tmp_path / "gone")})
    assert resolve_active_config(root) == root


# -- reading ---------------------------------------------------------------
def test_list_agents(tmp_path):
    path = write_config(tmp_path / "config.json", {"agents": {"b": "pi", "a": "pi"}})
    assert ConfigLoader(path).list() == ["b", "a"]


def test_list_agents_empty_when_missing_key(tmp_path):
    path = write_config(tmp_path / "config.json", {})
    assert ConfigLoader(path).list() == []


def test_get_raw(tmp_path):
    path = write_config(tmp_path / "config.json", {"agents": {"a": "pi-cli -e x"}})
    assert ConfigLoader(path).get_raw("a") == "pi-cli -e x"


def test_get_raw_missing_lists_available(tmp_path):
    path = write_config(tmp_path / "config.json", {"agents": {"a": "pi"}})
    with pytest.raises(SavedConfigNotFoundError) as exc:
        ConfigLoader(path).get_raw("nope")
    assert "available: a" in str(exc.value)


def test_get_raw_non_string(tmp_path):
    path = write_config(tmp_path / "config.json", {"agents": {"a": ["pi"]}})
    with pytest.raises(ConfigParseError):
        ConfigLoader(path).get_raw("a")


def test_missing_config(tmp_path):
    with pytest.raises(ConfigNotFoundError):
        ConfigLoader(tmp_path / "nope.json").list()


def test_invalid_json(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ConfigParseError):
        ConfigLoader(path).list()


def test_non_object_config(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigParseError):
        ConfigLoader(path).list()


def test_agents_not_object(tmp_path):
    path = write_config(tmp_path / "config.json", {"agents": [1]})
    with pytest.raises(ConfigParseError):
        ConfigLoader(path).list()


# -- get() resolution ------------------------------------------------------
def test_get_resolves_via_runner(tmp_path, monkeypatch):
    path = write_config(tmp_path / "config.json", {"agents": {"worker": "pi-cli -s x"}})
    captured: dict = {}

    def fake_runner(argv, env):
        captured["argv"] = list(argv)
        captured["env"] = dict(env)
        return subprocess.CompletedProcess(argv, 0, "pi -ne 'a b' --name worker", "")

    monkeypatch.setattr(loader_mod.shutil, "which", lambda name: "/usr/bin/pi-cli")
    result = ConfigLoader(path, runner=fake_runner).get("worker")
    assert result == ["pi", "-ne", "a b", "--name", "worker"]
    assert captured["argv"] == ["/usr/bin/pi-cli", "--dry-run", "-i", "worker"]
    assert captured["env"]["PI_CLI_CONFIG"] == str(path)


def test_get_missing_name_does_not_run(tmp_path):
    path = write_config(tmp_path / "config.json", {"agents": {}})
    calls: list = []
    loader = ConfigLoader(path, runner=lambda argv, env: calls.append(argv))
    with pytest.raises(SavedConfigNotFoundError):
        loader.get("nope")
    assert calls == []


def test_get_pi_cli_missing(tmp_path, monkeypatch):
    path = write_config(tmp_path / "config.json", {"agents": {"a": "pi"}})
    monkeypatch.setattr(loader_mod.shutil, "which", lambda name: None)
    with pytest.raises(PiCliNotFoundError):
        ConfigLoader(path, pi_cli_bin="definitely-not-real-xyz").get("a")


def test_get_nonzero_exit(tmp_path, monkeypatch):
    path = write_config(tmp_path / "config.json", {"agents": {"a": "pi"}})

    def fake_runner(argv, env):
        return subprocess.CompletedProcess(argv, 1, "", "boom")

    monkeypatch.setattr(loader_mod.shutil, "which", lambda name: "/usr/bin/pi-cli")
    with pytest.raises(PiAgentGraphError) as exc:
        ConfigLoader(path, runner=fake_runner).get("a")
    assert "boom" in str(exc.value)


# -- parse_dry_run ---------------------------------------------------------
def test_parse_dry_run_empty():
    with pytest.raises(PiAgentGraphError):
        parse_dry_run("   \n")


def test_parse_dry_run_quotes():
    assert parse_dry_run("pi --system-prompt 'a b' -- x") == [
        "pi",
        "--system-prompt",
        "a b",
        "--",
        "x",
    ]
