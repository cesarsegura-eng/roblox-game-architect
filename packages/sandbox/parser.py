"""Fail-closed syntax parsing of Luau source with the pinned Lute runtime.

This is only the syntax layer. It does not implement the API allowlist or any
other Gate 1 policy, and it never executes generated Luau.

The Lute child process is bounded on every run: a wall-clock timeout, a cap on
the bytes it may write to stdout and stderr, and an operating-system memory limit
that is in force before the process executes anything. That limit is implemented
only on Linux (an address-space rlimit applied between `fork` and `exec`). On
every other platform, Windows included, the parser refuses to run rather than
pretend to be limited: with the standard library alone there is no documented way
to place a Windows child in a memory-limited job object before it runs code.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

PINNED_LUTE_VERSION = "1.0.0"
MAX_SOURCE_CHARACTERS = 100_000
# UTF-8 needs at most four bytes per code point, so this is the byte form of the
# character limit above; it is checked on the encoded source as well.
MAX_SOURCE_BYTES = MAX_SOURCE_CHARACTERS * 4
DEFAULT_TIMEOUT_SECONDS = 5.0
DEFAULT_MEMORY_LIMIT_BYTES = 1024 * 1024 * 1024
# The checker prints one short JSON object and `--version` one short line, so
# these caps are far above anything legitimate. stderr is only counted, never kept.
MAX_STDOUT_BYTES = 4096
MAX_STDERR_BYTES = 16_384
_VERSION_TIMEOUT_SECONDS = 2.0
_CHECKER_PATH = Path(__file__).parent / "lute" / "check_syntax.luau"
_CHILD_ENVIRONMENT_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP")

_POLL_INTERVAL_SECONDS = 0.02
_JOIN_GRACE_SECONDS = 1.0
_REAP_TIMEOUT_SECONDS = 5.0
_READ_CHUNK_BYTES = 4096


class LuauParserError(Exception):
    """Base class for syntax-parser failures."""


class LuteUnavailableError(LuauParserError):
    """Lute or its trusted checker could not run; validation must fail closed."""


class LuteVersionError(LuauParserError):
    """The installed Lute version differs from the repository pin."""


class SourceRejectedError(LuauParserError, ValueError):
    """The source is not representable or exceeds the parser's input bound."""


@dataclass(frozen=True, slots=True)
class SyntaxCheckResult:
    """Result of parsing only; a successful parse is not policy approval."""

    syntax_valid: bool


@dataclass(frozen=True, slots=True)
class _ProcessResult:
    """Exit status and bounded stdout of a finished child. stderr is never kept."""

    returncode: int
    stdout: bytes


def _popen(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    preexec_fn: Callable[[], None] | None = None,
    start_new_session: bool = False,
) -> subprocess.Popen[bytes]:
    # The executable and checker are trusted and fixed; the source is only ever a
    # file path in `command`, and shell parsing is disabled.
    return subprocess.Popen(  # noqa: S603
        command,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
        shell=False,
        preexec_fn=preexec_fn,
        start_new_session=start_new_session,
    )


def _terminate(process: subprocess.Popen[bytes]) -> None:
    """Kill the child (and its process group on POSIX) and reap it."""
    if process.poll() is None:
        try:
            if sys.platform == "win32":
                process.kill()
            else:
                os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            try:
                process.kill()
            except OSError:
                pass
    try:
        process.wait(timeout=_REAP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        pass


def _launch_linux(
    command: list[str], cwd: Path, env: dict[str, str], memory_limit_bytes: int
) -> tuple[subprocess.Popen[bytes], Any]:
    """Start the child with an address-space limit applied before `exec`."""
    import resource

    def apply_limits() -> None:
        resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    process = _popen(
        command,
        cwd=cwd,
        env=env,
        preexec_fn=apply_limits,
        start_new_session=True,
    )
    return process, lambda: None


def _launch(
    command: list[str], cwd: Path, env: dict[str, str], memory_limit_bytes: int
) -> tuple[subprocess.Popen[bytes], Any]:
    """Start the child under a memory limit, or refuse: never run it unlimited."""
    if not sys.platform.startswith("linux"):
        raise LuteUnavailableError(
            "a memory limit for Lute is only enforced on Linux; refusing to run it on this platform"
        )
    try:
        return _launch_linux(command, cwd, env, memory_limit_bytes)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise LuteUnavailableError("the Lute process could not complete") from exc


def _drain(
    stream: IO[bytes],
    limit: int,
    keep: bool,
    overflow: threading.Event,
    sink: list[bytes],
) -> None:
    """Read a pipe, flagging overflow instead of buffering past `limit` bytes."""
    total = 0
    chunks: list[bytes] = []
    try:
        while True:
            chunk = stream.read(_READ_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                overflow.set()
                return
            if keep:
                chunks.append(chunk)
    except (OSError, ValueError):
        return
    sink.append(b"".join(chunks))


def _run_bounded(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout_seconds: float,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
    memory_limit_bytes: int,
) -> _ProcessResult:
    """Run `command` under a timeout, output caps and a memory limit.

    The child is always killed and reaped before this returns or raises. Nothing
    the child writes is placed in an exception message.
    """
    process, release = _launch(command, cwd, env, memory_limit_bytes)
    overflow = threading.Event()
    stdout_sink: list[bytes] = []
    stderr_sink: list[bytes] = []
    assert process.stdout is not None  # noqa: S101
    assert process.stderr is not None  # noqa: S101
    readers = [
        threading.Thread(
            target=_drain,
            args=(process.stdout, max_stdout_bytes, True, overflow, stdout_sink),
            daemon=True,
        ),
        threading.Thread(
            target=_drain,
            args=(process.stderr, max_stderr_bytes, False, overflow, stderr_sink),
            daemon=True,
        ),
    ]
    try:
        for reader in readers:
            reader.start()
        deadline = time.monotonic() + timeout_seconds
        while process.poll() is None:
            if overflow.is_set():
                raise LuteUnavailableError("the Lute process exceeded its output limit")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LuteUnavailableError("the Lute process could not complete")
            overflow.wait(min(_POLL_INTERVAL_SECONDS, remaining))
        for reader in readers:
            reader.join(_JOIN_GRACE_SECONDS)
        if overflow.is_set():
            raise LuteUnavailableError("the Lute process exceeded its output limit")
        if any(reader.is_alive() for reader in readers) or not stdout_sink or not stderr_sink:
            raise LuteUnavailableError("the Lute process did not close its output cleanly")
        return _ProcessResult(returncode=process.returncode, stdout=stdout_sink[0])
    finally:
        _terminate(process)
        release()
        for reader in readers:
            if reader.is_alive():
                reader.join(_JOIN_GRACE_SECONDS)
        for stream in (process.stdout, process.stderr):
            try:
                stream.close()
            except OSError:
                pass


class LuteSyntaxParser:
    """Parse Luau with the exact Lute version pinned in `aftman.toml`.

    The checker is a repository-controlled Luau script. Source code is written
    to a private temporary file and passed to the checker as input data.
    """

    def __init__(
        self,
        executable: str | Path = "lute",
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        memory_limit_bytes: int = DEFAULT_MEMORY_LIMIT_BYTES,
    ) -> None:
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ValueError("timeout_seconds must be a finite positive number")
        if (
            isinstance(memory_limit_bytes, bool)
            or not isinstance(memory_limit_bytes, int)
            or memory_limit_bytes <= 0
        ):
            raise ValueError("memory_limit_bytes must be a positive integer")
        if not _CHECKER_PATH.is_file():
            raise LuteUnavailableError("the trusted Lute checker is missing")

        self._executable = self._resolve_executable(executable)
        self._timeout_seconds = float(timeout_seconds)
        self._memory_limit_bytes = memory_limit_bytes
        self._verify_version()

    @staticmethod
    def _resolve_executable(executable: str | Path) -> str:
        raw = os.fspath(executable)
        if not raw:
            raise LuteUnavailableError("Lute executable was not configured")
        if Path(raw).is_absolute() or os.sep in raw or (os.altsep and os.altsep in raw):
            candidate = Path(raw)
            if not candidate.is_file():
                raise LuteUnavailableError("the configured Lute executable is missing")
            return str(candidate.resolve())
        resolved = shutil.which(raw)
        if resolved is None:
            raise LuteUnavailableError("Lute is not installed or is not on PATH")
        return resolved

    @staticmethod
    def _environment() -> dict[str, str]:
        """Pass only environment variables needed by the standalone runtime."""
        return {key: os.environ[key] for key in _CHILD_ENVIRONMENT_KEYS if os.environ.get(key)}

    def _run(self, arguments: list[str], timeout_seconds: float) -> _ProcessResult:
        return _run_bounded(
            [self._executable, *arguments],
            cwd=_CHECKER_PATH.parent,
            env=self._environment(),
            timeout_seconds=timeout_seconds,
            max_stdout_bytes=MAX_STDOUT_BYTES,
            max_stderr_bytes=MAX_STDERR_BYTES,
            memory_limit_bytes=self._memory_limit_bytes,
        )

    @staticmethod
    def _decode(output: bytes) -> str:
        try:
            return output.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise LuteUnavailableError("the Lute process returned malformed output") from exc

    def _verify_version(self) -> None:
        result = self._run(["--version"], _VERSION_TIMEOUT_SECONDS)
        if result.returncode != 0:
            raise LuteUnavailableError("Lute version check failed")
        actual = self._decode(result.stdout).strip()
        if actual != PINNED_LUTE_VERSION:
            raise LuteVersionError(
                f"expected Lute {PINNED_LUTE_VERSION}; found {actual or 'no version'}"
            )

    def parse(self, source: str) -> SyntaxCheckResult:
        """Return syntax validity or raise if the parser cannot run safely.

        Syntax diagnostics from Lute are intentionally not surfaced here: they
        can contain untrusted source fragments. Policy-level diagnostics belong
        to the future structured analyzer.
        """
        if not isinstance(source, str):
            raise SourceRejectedError("Luau source must be a string")
        if len(source) > MAX_SOURCE_CHARACTERS:
            raise SourceRejectedError(
                f"Luau source exceeds {MAX_SOURCE_CHARACTERS} Unicode code points"
            )
        if "\x00" in source:
            raise SourceRejectedError("Luau source contains a NUL character")
        try:
            source_bytes = source.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise SourceRejectedError("Luau source is not valid Unicode") from exc
        if len(source_bytes) > MAX_SOURCE_BYTES:
            raise SourceRejectedError(f"Luau source exceeds {MAX_SOURCE_BYTES} UTF-8 bytes")

        with tempfile.TemporaryDirectory(prefix="rga-luau-") as temp_dir:
            source_path = Path(temp_dir) / "source.luau"
            try:
                source_path.write_bytes(source_bytes)
            except OSError as exc:
                raise LuteUnavailableError("could not stage Luau source for parsing") from exc

            result = self._run(
                ["run", str(_CHECKER_PATH), str(source_path)],
                self._timeout_seconds,
            )
        if result.returncode != 0:
            raise LuteUnavailableError("the Lute checker failed")
        try:
            payload = json.loads(self._decode(result.stdout))
        except json.JSONDecodeError as exc:
            raise LuteUnavailableError("the Lute checker returned malformed output") from exc
        if (
            not isinstance(payload, dict)
            or set(payload) != {"syntax_valid"}
            or not isinstance(payload["syntax_valid"], bool)
        ):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        return SyntaxCheckResult(syntax_valid=payload["syntax_valid"])
