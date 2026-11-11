#!/usr/bin/env python3
"""Behaviour tests for src/pre-commit."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.machinery import SourceFileLoader
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "src" / "pre-commit"


def _load_script():
    loader = SourceFileLoader("prompt_default_branch_commit", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load src/pre-commit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(args: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "commit.gpgsign"
    env["GIT_CONFIG_VALUE_0"] = "false"
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )


def _init_work(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    _git(["init", "-b", "master"], work)
    _git(["config", "user.email", "t@example.com"], work)
    _git(["config", "user.name", "Test"], work)
    _git(["commit", "--allow-empty", "-m", "init"], work)


@contextmanager
def _repo() -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "work"
        _init_work(work)
        yield work


@contextmanager
def _repo_with_origin(head: str) -> Iterator[Path]:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        bare = base / "origin.git"
        work = base / "work"
        subprocess.run(
            ["git", "init", "--bare", "-b", "master", str(bare)],
            check=True,
            capture_output=True,
            text=True,
        )
        _init_work(work)
        _git(["remote", "add", "origin", str(bare)], work)
        _git(["push", "origin", "master"], work)
        if head != "master":
            _git(["checkout", "-b", head], work)
            _git(["push", "origin", head], work)
            _git(["checkout", "master"], work)
        _git(["symbolic-ref", "HEAD", f"refs/heads/{head}"], bare)
        _git(["remote", "set-head", "origin", head], work)
        show = _git(["remote", "show", "origin"], work)
        if f"HEAD branch: {head}" not in show.stdout:
            raise RuntimeError(show.stdout)
        yield work


@contextmanager
def _preserve_cwd() -> Iterator[None]:
    previous = os.getcwd()
    try:
        yield
    finally:
        os.chdir(previous)


class ScriptedTty:
    """Stand-in for /dev/tty. main() uses it as a context manager."""

    def __init__(self, answers: list[str]) -> None:
        self.answers = list(answers)
        self.written: list[str] = []

    def write(self, text: str) -> None:
        self.written.append(text)

    def flush(self) -> None:
        return None

    def readline(self) -> str:
        if not self.answers:
            return ""
        return self.answers.pop(0)

    def close(self) -> None:
        return None

    def __enter__(self) -> ScriptedTty:
        return self

    def __exit__(self, *args: object) -> None:
        return None


def _question(tty: ScriptedTty) -> str:
    return "".join(tty.written)


def test_resolve_git_returns_executable():
    path = _load_script().resolve_git()
    assert os.access(path, os.X_OK)


def test_header_defaults():
    source = SCRIPT.read_text(encoding="utf-8")
    mod = _load_script()
    assert source.splitlines()[0] == "#!/usr/bin/env python3"
    assert "# STOP HERE" not in source
    assert os.access(SCRIPT, os.X_OK)
    assert isinstance(mod.__version__, str) and mod.__version__
    assert mod.REMOTE_LOOKUP is False


def test_flag_off_ignores_origin_head():
    mod = _load_script()
    with _repo_with_origin("trunk") as work, _preserve_cwd():
        os.chdir(work)
        mod.REMOTE_LOOKUP = False
        assert mod.default_branch() == "master"


def test_non_bool_lookup_flag_stays_on_master():
    mod = _load_script()
    with _repo_with_origin("trunk") as work, _preserve_cwd():
        os.chdir(work)
        mod.REMOTE_LOOKUP = "yes"
        assert mod.default_branch() == "master"


def test_flag_on_uses_origin_head():
    mod = _load_script()
    with _repo_with_origin("trunk") as work, _preserve_cwd():
        os.chdir(work)
        mod.REMOTE_LOOKUP = True
        assert mod.default_branch() == "trunk"


def test_flag_on_missing_origin_falls_back_to_master():
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        mod.REMOTE_LOOKUP = True
        assert mod.default_branch() == "master"
        tty = ScriptedTty(["yes\n"])
        mod.open_tty = lambda: tty
        assert mod.main() == 0
        assert "commit to the master branch" in _question(tty)


def test_flag_on_deleted_remote_head_looks_up_and_falls_back_to_master(monkeypatch):
    mod = _load_script()
    with _repo_with_origin("master") as work, _preserve_cwd():
        os.chdir(work)
        _git(["remote", "set-head", "origin", "-d"], work)
        show = _git(["remote", "show", "origin"], work)
        assert "HEAD branch:" in show.stdout
        mod.REMOTE_LOOKUP = True
        remote_show_count = 0
        real_run = mod.subprocess.run

        def counting_run(cmd, *args, **kwargs):
            nonlocal remote_show_count
            if isinstance(cmd, list) and "remote" in cmd and "show" in cmd and "origin" in cmd:
                remote_show_count += 1
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", counting_run)
        assert mod.default_branch() == "master"
        assert remote_show_count >= 1
        tty = ScriptedTty(["yes\n"])
        mod.open_tty = lambda: tty
        assert mod.main() == 0
        assert "commit to the master branch" in _question(tty)


def test_flag_on_unknown_head_parser_falls_back_to_master(monkeypatch):
    mod = _load_script()
    with _repo_with_origin("master") as work, _preserve_cwd():
        os.chdir(work)
        mod.REMOTE_LOOKUP = True
        remote_show_count = 0
        real_run = mod.subprocess.run

        def fake_run(cmd, *args, **kwargs):
            nonlocal remote_show_count
            if isinstance(cmd, list) and "remote" in cmd and "show" in cmd and "origin" in cmd:
                remote_show_count += 1
                return subprocess.CompletedProcess(
                    cmd,
                    0,
                    stdout="  HEAD branch: (unknown)\n",
                    stderr="",
                )
            return real_run(cmd, *args, **kwargs)

        monkeypatch.setattr(mod.subprocess, "run", fake_run)
        assert mod.default_branch() == "master"
        assert remote_show_count == 1


def test_first_commit_on_master_prompts():
    mod = _load_script()
    with tempfile.TemporaryDirectory() as tmp, _preserve_cwd():
        work = Path(tmp) / "work"
        work.mkdir()
        _git(["init", "-b", "master"], work)
        os.chdir(work)
        tty = ScriptedTty(["yes\n"])
        mod.open_tty = lambda: tty
        assert mod.main() == 0
        assert "commit to the master branch" in _question(tty)


def test_yes_on_master_allows_commit():
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        tty = ScriptedTty(["yes\n"])
        mod.open_tty = lambda: tty
        assert mod.main() == 0
        assert "commit to the master branch" in _question(tty)


def test_no_and_blank_abort():
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        no_tty = ScriptedTty(["no\n"])
        mod.open_tty = lambda: no_tty
        assert mod.main() == 1
        blank = _load_script()
        blank_tty = ScriptedTty(["\n", "no\n"])
        blank.open_tty = lambda: blank_tty
        assert blank.main() == 1
        assert blank_tty.written.count(blank_tty.written[0]) >= 2


def test_invalid_then_yes_allows_commit():
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        tty = ScriptedTty(["maybe\n", "yes\n"])
        mod.open_tty = lambda: tty
        assert mod.main() == 0
        assert "commit to the master branch" in _question(tty)


def test_other_branch_does_not_open_tty():
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        _git(["checkout", "-b", "feature"], work)

        def fail_if_called():
            raise AssertionError("open_tty should not be called")

        mod.open_tty = fail_if_called
        assert mod.main() == 0


def test_flag_on_other_branch_does_not_open_tty():
    mod = _load_script()
    with _repo_with_origin("trunk") as work, _preserve_cwd():
        os.chdir(work)
        _git(["checkout", "-b", "feature"], work)
        mod.REMOTE_LOOKUP = True

        def fail_if_called():
            raise AssertionError("open_tty should not be called")

        mod.open_tty = fail_if_called
        assert mod.main() == 0


def test_no_tty_on_master_allows_commit():
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        mod.open_tty = lambda: None
        assert mod.main() == 0


def test_stdin_yes_does_not_answer_the_prompt(monkeypatch):
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("yes\n"))
        tty = ScriptedTty(["no\n"])
        mod.open_tty = lambda: tty
        assert mod.main() == 1


def test_detached_head_allows_commit():
    mod = _load_script()
    with _repo() as work, _preserve_cwd():
        os.chdir(work)
        _git(["checkout", "--detach"], work)

        def fail_if_called():
            raise AssertionError("open_tty should not be called")

        mod.open_tty = fail_if_called
        assert mod.main() == 0
