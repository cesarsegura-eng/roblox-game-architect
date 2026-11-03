"""Tests for the fail-closed Lute syntax bridge and its bounded child process."""

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from sandbox import parser as parser_module
from sandbox.parser import (
    DEFAULT_MEMORY_LIMIT_BYTES,
    MAX_SOURCE_BYTES,
    MAX_SOURCE_CHARACTERS,
    MAX_STDERR_BYTES,
    MAX_STDOUT_BYTES,
    PINNED_LUTE_VERSION,
    LuteSyntaxParser,
    LuteUnavailableError,
    LuteVersionError,
    SourceRejectedError,
    SyntaxCheckResult,
    _ProcessResult,
    _run_bounded,
)

_LINUX = sys.platform.startswith("linux")
_MIB = 1024 * 1024


@dataclass
class _FakeLute:
    commands: list[list[str]] = field(default_factory=list)
    kwargs: list[dict[str, Any]] = field(default_factory=list)
    source_paths: list[Path] = field(default_factory=list)


def _install_fake_lute(monkeypatch: pytest.MonkeyPatch, *, version: str = "1.0.0") -> _FakeLute:
    fake = _FakeLute()

    def fake_which(executable: str) -> str:
        assert executable == "lute"
        return "C:/tools/lute.exe"

    def fake_run(command: list[str], **kwargs: Any) -> _ProcessResult:
        fake.commands.append(command)
        fake.kwargs.append(kwargs)
        if command[1] == "--version":
            return _ProcessResult(returncode=0, stdout=f"{version}\n".encode())
        if command[1] == "run":
            source_path = Path(command[-1])
            fake.source_paths.append(source_path)
            valid = source_path.read_text(encoding="utf-8") != "invalid syntax"
            return _ProcessResult(
                returncode=0, stdout=b'{"syntax_valid":%s}' % (b"true" if valid else b"false")
            )
        raise AssertionError(f"unexpected Lute arguments: {command!r}")

    monkeypatch.setattr("sandbox.parser.shutil.which", fake_which)
    monkeypatch.setattr("sandbox.parser._run_bounded", fake_run)
    return fake


def _replace_runner(monkeypatch: pytest.MonkeyPatch, result: _ProcessResult | Exception) -> None:
    def runner(command: list[str], **kwargs: Any) -> _ProcessResult:
        del command, kwargs
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("sandbox.parser._run_bounded", runner)


# --- parse(): contract, input bounds and fail-closed paths -----------------------


def test_pinned_lute_version_is_verified_before_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()

    assert fake.commands == [["C:/tools/lute.exe", "--version"]]
    assert PINNED_LUTE_VERSION == "1.0.0"
    assert parser.parse("local value = 1") == SyntaxCheckResult(syntax_valid=True)
    assert len(fake.commands) == 2


def test_syntax_error_is_returned_as_invalid_without_raw_diagnostic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()

    assert parser.parse("invalid syntax") == SyntaxCheckResult(syntax_valid=False)


def test_wrong_lute_version_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_lute(monkeypatch, version="1.0.1")

    with pytest.raises(LuteVersionError, match=r"expected Lute 1\.0\.0"):
        LuteSyntaxParser()


def test_missing_lute_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sandbox.parser.shutil.which", lambda executable: None)

    with pytest.raises(LuteUnavailableError, match="not installed"):
        LuteSyntaxParser()


def test_source_above_limit_is_rejected_before_running_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()
    fake.commands.clear()

    with pytest.raises(SourceRejectedError, match="100000"):
        parser.parse("a" * (MAX_SOURCE_CHARACTERS + 1))
    assert fake.commands == []


def test_byte_limit_is_the_utf8_form_of_the_character_limit() -> None:
    assert MAX_SOURCE_BYTES == MAX_SOURCE_CHARACTERS * 4


def test_largest_allowed_source_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()
    # 100,000 four-byte code points is exactly the byte limit.
    source = "\U0001f600" * MAX_SOURCE_CHARACTERS

    assert len(source.encode("utf-8")) == MAX_SOURCE_BYTES
    assert parser.parse(source) == SyntaxCheckResult(syntax_valid=True)
    assert len(fake.commands) == 2


def test_source_above_byte_limit_is_rejected_before_running_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()
    fake.commands.clear()
    monkeypatch.setattr("sandbox.parser.MAX_SOURCE_BYTES", 10)

    # Four characters, eight bytes: within 10 bytes. Six characters, twelve bytes: over.
    assert parser.parse("\u00e9" * 4) == SyntaxCheckResult(syntax_valid=True)
    fake.commands.clear()
    with pytest.raises(SourceRejectedError, match="UTF-8 bytes"):
        parser.parse("\u00e9" * 6)
    assert fake.commands == []


@pytest.mark.parametrize("source", ["a\x00b", "\ud800"])
def test_source_with_nul_or_lone_surrogate_is_rejected(source: str) -> None:
    with pytest.raises(SourceRejectedError):
        object.__new__(LuteSyntaxParser).parse(source)


def test_checker_output_must_be_exact_json_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()

    _replace_runner(
        monkeypatch, _ProcessResult(returncode=0, stdout=b'{"syntax_valid":true,"extra":true}')
    )
    with pytest.raises(LuteUnavailableError, match="invalid result"):
        parser.parse("local value = 1")


def test_nonzero_checker_exit_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()

    _replace_runner(monkeypatch, _ProcessResult(returncode=2, stdout=b""))
    with pytest.raises(LuteUnavailableError, match="checker failed"):
        parser.parse("local value = 1")


def test_runner_failure_propagates_as_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()

    _replace_runner(monkeypatch, LuteUnavailableError("the Lute process could not complete"))
    with pytest.raises(LuteUnavailableError, match="could not complete"):
        parser.parse("local value = 1")


def test_non_utf8_checker_output_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()

    _replace_runner(monkeypatch, _ProcessResult(returncode=0, stdout=b"\xff\xfe"))
    with pytest.raises(LuteUnavailableError, match="malformed output"):
        parser.parse("local value = 1")


def test_errors_never_echo_source_or_process_output(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()
    source = "local SECRET_SOURCE_MARKER = 1"

    _replace_runner(monkeypatch, _ProcessResult(returncode=0, stdout=b"SECRET_OUTPUT_MARKER"))
    with pytest.raises(LuteUnavailableError) as raised:
        parser.parse(source)
    message = str(raised.value)
    assert "SECRET_SOURCE_MARKER" not in message
    assert "SECRET_OUTPUT_MARKER" not in message


def test_staged_source_is_removed_after_success_and_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser()

    parser.parse("local value = 1")
    assert fake.source_paths
    assert not fake.source_paths[-1].parent.exists()

    _replace_runner(monkeypatch, LuteUnavailableError("the Lute process could not complete"))
    seen: list[Path] = []
    real_temp = parser_module.tempfile.TemporaryDirectory

    class Recording(real_temp):  # type: ignore[type-arg, misc]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            seen.append(Path(self.name))

    monkeypatch.setattr("sandbox.parser.tempfile.TemporaryDirectory", Recording)
    with pytest.raises(LuteUnavailableError):
        parser.parse("local value = 1")
    assert seen
    assert not seen[0].exists()


def test_every_run_is_given_the_configured_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install_fake_lute(monkeypatch)
    parser = LuteSyntaxParser(memory_limit_bytes=256 * _MIB)
    parser.parse("local value = 1")

    assert len(fake.kwargs) == 2
    for kwargs in fake.kwargs:
        assert kwargs["memory_limit_bytes"] == 256 * _MIB
        assert kwargs["max_stdout_bytes"] == MAX_STDOUT_BYTES
        assert kwargs["max_stderr_bytes"] == MAX_STDERR_BYTES
        assert kwargs["timeout_seconds"] > 0
    assert fake.kwargs[1]["timeout_seconds"] == parser._timeout_seconds
    assert LuteSyntaxParser(memory_limit_bytes=1).parse is not None
    assert DEFAULT_MEMORY_LIMIT_BYTES > 0


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "1024"])
def test_invalid_memory_limit_is_rejected(monkeypatch: pytest.MonkeyPatch, bad: object) -> None:
    _install_fake_lute(monkeypatch)

    with pytest.raises(ValueError, match="memory_limit_bytes"):
        LuteSyntaxParser(memory_limit_bytes=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", [0, -1, float("inf"), float("nan"), True])
def test_invalid_timeout_is_rejected(monkeypatch: pytest.MonkeyPatch, bad: float) -> None:
    _install_fake_lute(monkeypatch)

    with pytest.raises(ValueError, match="timeout_seconds"):
        LuteSyntaxParser(timeout_seconds=bad)


def test_child_environment_is_reduced_to_the_allowed_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "must-not-leak")
    monkeypatch.setenv("PATH", os.environ.get("PATH", "x"))

    environment = LuteSyntaxParser._environment()

    assert "LLM_API_KEY" not in environment
    assert set(environment) <= set(parser_module._CHILD_ENVIRONMENT_KEYS)


# --- _run_bounded(): real stand-in child processes --------------------------------


class _Recorder:
    """Capture the processes started by `_run_bounded` so cleanup can be checked."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.processes: list[subprocess.Popen[bytes]] = []
        recorder = self
        real = subprocess.Popen

        class Recording(real):  # type: ignore[type-arg, misc]
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                recorder.processes.append(self)

        monkeypatch.setattr("sandbox.parser.subprocess.Popen", Recording)

    def assert_reaped(self) -> None:
        assert self.processes, "no process was started"
        for process in self.processes:
            assert process.returncode is not None
            assert process.stdout is not None
            assert process.stdout.closed
            assert process.stderr is not None
            assert process.stderr.closed


def _run_child(
    code: str,
    *,
    timeout_seconds: float = 20.0,
    max_stdout_bytes: int = MAX_STDOUT_BYTES,
    max_stderr_bytes: int = MAX_STDERR_BYTES,
    memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
) -> _ProcessResult:
    return _run_bounded(
        [sys.executable, "-c", code],
        cwd=Path.cwd(),
        env=os.environ.copy(),
        timeout_seconds=timeout_seconds,
        max_stdout_bytes=max_stdout_bytes,
        max_stderr_bytes=max_stderr_bytes,
        memory_limit_bytes=memory_limit_bytes,
    )


_linux_only = pytest.mark.skipif(not _LINUX, reason="the memory limit is only implemented on Linux")


@pytest.fixture
def unlimited_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start stand-in children WITHOUT a memory limit, to test caps, timeout and cleanup.

    This replaces only the platform launcher, so it says nothing about the memory
    limit; that is covered by the Linux-only tests below, which use the real one.
    """

    def launch(
        command: list[str], cwd: Path, env: dict[str, str], memory_limit_bytes: int
    ) -> tuple[subprocess.Popen[bytes], Any]:
        del memory_limit_bytes
        return parser_module._popen(command, cwd=cwd, env=env), lambda: None

    monkeypatch.setattr("sandbox.parser._launch", launch)


def test_output_within_limits_is_returned(
    unlimited_launch: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder(monkeypatch)

    result = _run_child("import sys; print('ok'); sys.stderr.write('warn')")

    assert result.returncode == 0
    assert result.stdout.strip() == b"ok"
    recorder.assert_reaped()


def test_nonzero_exit_is_reported_not_raised(
    unlimited_launch: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder(monkeypatch)

    result = _run_child("import sys; sys.exit(3)")

    assert result.returncode == 3
    recorder.assert_reaped()


def test_excess_stdout_kills_and_reaps_the_child(
    unlimited_launch: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder(monkeypatch)
    started = time.monotonic()

    with pytest.raises(LuteUnavailableError, match="output limit") as raised:
        _run_child(
            "import sys, time; sys.stdout.write('SECRET_CHILD_MARKER' * 1000);"
            " sys.stdout.flush(); time.sleep(60)",
            max_stdout_bytes=1024,
        )

    assert time.monotonic() - started < 30
    assert "SECRET_CHILD_MARKER" not in str(raised.value)
    recorder.assert_reaped()


def test_excess_stderr_kills_and_reaps_the_child(
    unlimited_launch: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder(monkeypatch)
    started = time.monotonic()

    with pytest.raises(LuteUnavailableError, match="output limit") as raised:
        _run_child(
            "import sys, time; sys.stderr.write('SECRET_CHILD_MARKER' * 1000);"
            " sys.stderr.flush(); time.sleep(60)",
            max_stderr_bytes=1024,
        )

    assert time.monotonic() - started < 30
    assert "SECRET_CHILD_MARKER" not in str(raised.value)
    recorder.assert_reaped()


def test_timeout_kills_and_reaps_the_child(
    unlimited_launch: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = _Recorder(monkeypatch)
    started = time.monotonic()

    with pytest.raises(LuteUnavailableError, match="could not complete"):
        _run_child("import time; time.sleep(60)", timeout_seconds=0.5)

    assert time.monotonic() - started < 30
    recorder.assert_reaped()


@_linux_only
def test_memory_limit_stops_a_child_that_allocates_too_much(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _Recorder(monkeypatch)

    result = _run_child(
        "data = bytearray(768 * 1024 * 1024); data[-1] = 1; print('allocated')",
        memory_limit_bytes=256 * _MIB,
    )

    assert result.returncode != 0
    assert b"allocated" not in result.stdout
    recorder.assert_reaped()


@_linux_only
def test_memory_limit_still_lets_a_small_child_run(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = _Recorder(monkeypatch)

    result = _run_child(
        "data = bytearray(16 * 1024 * 1024); data[-1] = 1; print('allocated')",
        memory_limit_bytes=256 * _MIB,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == b"allocated"
    recorder.assert_reaped()


@pytest.mark.parametrize("platform", ["win32", "darwin", "freebsd14"])
def test_platform_without_an_enforced_memory_limit_refuses_to_run(
    monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    def must_not_start(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a process was started without a memory limit")

    monkeypatch.setattr("sandbox.parser.sys.platform", platform)
    monkeypatch.setattr("sandbox.parser.subprocess.Popen", must_not_start)

    with pytest.raises(LuteUnavailableError, match="only enforced on Linux"):
        _run_bounded(
            [sys.executable, "-c", "pass"],
            cwd=Path.cwd(),
            env={},
            timeout_seconds=5,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            memory_limit_bytes=_MIB,
        )


@_linux_only
def test_spawn_failure_is_unavailable_and_leaves_no_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = Path(sys.executable).with_name("definitely-not-a-real-executable")

    with pytest.raises(LuteUnavailableError, match="could not complete"):
        _run_bounded(
            [str(missing)],
            cwd=Path.cwd(),
            env=os.environ.copy(),
            timeout_seconds=5,
            max_stdout_bytes=1024,
            max_stderr_bytes=1024,
            memory_limit_bytes=256 * _MIB,
        )


# --- real Lute (optional; skipped when it is not installed) -----------------------


@pytest.mark.integration
@pytest.mark.skipif(shutil.which("lute") is None, reason="Lute is not installed")
def test_real_lute_cannot_start_under_an_absurdly_small_memory_limit() -> None:
    with pytest.raises(LuteUnavailableError):
        LuteSyntaxParser(memory_limit_bytes=4 * _MIB)
