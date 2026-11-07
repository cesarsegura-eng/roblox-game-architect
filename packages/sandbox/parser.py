"""Fail-closed syntax parsing of Luau source with the pinned Lute runtime.

This is only the syntax layer. It does not implement the API allowlist or any
other Gate 1 policy, and it never executes generated Luau.

The Lute child process is bounded on every run: a wall-clock timeout, a cap on
the bytes it may write to stdout and stderr, and an operating-system memory limit
that is in force before the process executes anything. Linux uses an address-space
limit between `fork` and `exec`; Windows uses a suspended process assigned to a
memory-limited Job Object before its primary thread resumes. Other platforms fail
closed until an equivalent pre-execution limit is implemented.
"""

from __future__ import annotations

import json
import math
import os
import re
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
MAX_STDOUT_BYTES = 512 * 1024
MAX_STDERR_BYTES = 16_384
MAX_ANALYSIS_ITEMS = 512
MAX_ANALYSIS_STRING_LENGTH = 256
MAX_AST_NODES = 4096
MAX_AST_DEPTH = 128
_LOOP_KINDS = frozenset({"for", "forin", "while", "repeat"})
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
class CstSummary:
    """Bounded syntax facts for a future policy analyzer; not a verdict."""

    globals: tuple[str, ...]
    access_chains: tuple[str, ...]
    calls: tuple[str, ...]
    bracket_index_count: int
    unresolved_call_count: int
    loop_kinds: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SourceAnalysis:
    """Syntax, bounded CST facts, and a normalized CST program for policy checks."""

    syntax_valid: bool
    summary: CstSummary
    program: dict[str, Any]


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
    creationflags: int = 0,
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
        creationflags=creationflags,
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


def _launch_windows(
    command: list[str], cwd: Path, env: dict[str, str], memory_limit_bytes: int
) -> tuple[subprocess.Popen[bytes], Callable[[], None]]:
    """Assign a suspended child to a memory-capped Job Object, then resume it."""
    import ctypes
    from ctypes import wintypes

    class BasicLimitInformation(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IoCounters(ctypes.Structure):
        _fields_ = [
            (name, ctypes.c_ulonglong)
            for name in (
                "ReadOperationCount",
                "WriteOperationCount",
                "OtherOperationCount",
                "ReadTransferCount",
                "WriteTransferCount",
                "OtherTransferCount",
            )
        ]

    class ExtendedLimitInformation(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BasicLimitInformation),
            ("IoInfo", IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    class ThreadEntry32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ThreadID", wintypes.DWORD),
            ("th32OwnerProcessID", wintypes.DWORD),
            ("tpBasePri", wintypes.LONG),
            ("tpDeltaPri", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.ResumeThread.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Thread32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry32)]
    kernel32.Thread32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(ThreadEntry32)]
    kernel32.OpenThread.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenThread.restype = wintypes.HANDLE

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise ctypes.WinError(ctypes.get_last_error())
    closed = False

    def close_job() -> None:
        nonlocal closed
        if not closed:
            closed = True
            kernel32.CloseHandle(job)

    process: subprocess.Popen[bytes] | None = None
    try:
        limits = ExtendedLimitInformation()
        # JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2000
        limits.ProcessMemoryLimit = memory_limit_bytes
        if not kernel32.SetInformationJobObject(
            job, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            raise ctypes.WinError(ctypes.get_last_error())

        # CREATE_SUSPENDED prevents any child code from running before assignment.
        process = _popen(command, cwd=cwd, env=env, creationflags=0x00000004)
        if not kernel32.AssignProcessToJobObject(job, wintypes.HANDLE(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
        # subprocess closes CreateProcessW's primary-thread handle, so reopen
        # the (still suspended) thread by enumerating this newly created PID.
        snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
        if snapshot == wintypes.HANDLE(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        thread_handle = None
        try:
            entry = ThreadEntry32()
            entry.dwSize = ctypes.sizeof(entry)
            more = kernel32.Thread32First(snapshot, ctypes.byref(entry))
            while more:
                if entry.th32OwnerProcessID == process.pid:
                    thread_handle = kernel32.OpenThread(0x0002, False, entry.th32ThreadID)
                    break
                more = kernel32.Thread32Next(snapshot, ctypes.byref(entry))
            if not thread_handle:
                raise ctypes.WinError(ctypes.get_last_error())
            if kernel32.ResumeThread(thread_handle) == 0xFFFFFFFF:
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            if thread_handle:
                kernel32.CloseHandle(thread_handle)
            kernel32.CloseHandle(snapshot)
        return process, close_job
    except (OSError, ValueError, subprocess.SubprocessError):
        if process is not None:
            try:
                process.kill()
                process.wait(timeout=_REAP_TIMEOUT_SECONDS)
            except (OSError, subprocess.SubprocessError):
                pass
        close_job()
        raise


def _launch(
    command: list[str], cwd: Path, env: dict[str, str], memory_limit_bytes: int
) -> tuple[subprocess.Popen[bytes], Any]:
    """Start the child under a memory limit, or refuse: never run it unlimited."""
    if sys.platform == "win32":
        try:
            return _launch_windows(command, cwd, env, memory_limit_bytes)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            raise LuteUnavailableError("the Lute process could not complete") from exc
    if not sys.platform.startswith("linux"):
        raise LuteUnavailableError(
            "a memory limit for Lute is only enforced on Linux and Windows; "
            "refusing on this platform"
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
        """Return syntax validity or raise if the parser cannot run safely."""
        result = self.analyze(source)
        return SyntaxCheckResult(syntax_valid=result.syntax_valid)

    def analyze(self, source: str) -> SourceAnalysis:
        """Return bounded CST facts without making a policy decision.

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
        if not isinstance(payload, dict) or set(payload) != {
            "syntax_valid",
            "summary",
            "program",
        }:
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        syntax_valid = payload["syntax_valid"]
        raw_summary = payload["summary"]
        raw_program = payload["program"]
        if (
            not isinstance(syntax_valid, bool)
            or not isinstance(raw_summary, dict)
            or not isinstance(raw_program, dict)
        ):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        if set(raw_summary) != {
            "globals",
            "access_chains",
            "calls",
            "bracket_index_count",
            "unresolved_call_count",
            "loop_kinds",
        }:
            raise LuteUnavailableError("the Lute checker returned an invalid result")

        def read_names(key: str) -> tuple[str, ...]:
            values = raw_summary[key]
            if (
                not isinstance(values, list)
                or len(values) > MAX_ANALYSIS_ITEMS
                or any(
                    not isinstance(value, str)
                    or not value
                    or len(value) > MAX_ANALYSIS_STRING_LENGTH
                    for value in values
                )
                or values != sorted(set(values))
            ):
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return tuple(values)

        def read_count(key: str) -> int:
            value = raw_summary[key]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= MAX_SOURCE_CHARACTERS
            ):
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return value

        loop_kinds = read_names("loop_kinds")
        if not set(loop_kinds) <= _LOOP_KINDS:
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        summary = CstSummary(
            globals=read_names("globals"),
            access_chains=read_names("access_chains"),
            calls=read_names("calls"),
            bracket_index_count=read_count("bracket_index_count"),
            unresolved_call_count=read_count("unresolved_call_count"),
            loop_kinds=loop_kinds,
        )
        program = _validate_program(raw_program)
        if not syntax_valid and summary != CstSummary((), (), (), 0, 0, ()):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        if not syntax_valid and program != {"kind": "block", "statements": []}:
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        return SourceAnalysis(syntax_valid=syntax_valid, summary=summary, program=program)


def _validate_program(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate the bounded JSON AST emitted by the trusted Lute checker."""
    nodes = 0

    def text(value: object, maximum: int = MAX_ANALYSIS_STRING_LENGTH) -> str:
        if not isinstance(value, str) or not value or len(value) > maximum:
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        return value

    def binding(value: object) -> dict[str, str]:
        if not isinstance(value, dict) or set(value) != {"id", "name"}:
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        identity = text(value["id"], 64)
        if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*:[1-9][0-9]*:[1-9][0-9]*", identity):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        return {"id": identity, "name": text(value["name"])}

    def expressions(value: object, depth: int) -> list[dict[str, Any]]:
        if not isinstance(value, list) or len(value) > MAX_AST_NODES:
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        return [expression(item, depth + 1) for item in value]

    def expression(value: object, depth: int) -> dict[str, Any]:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_AST_NODES or depth > MAX_AST_DEPTH or not isinstance(value, dict):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        kind = value.get("kind")
        if not isinstance(kind, str):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        if kind == "unsupported":
            if set(value) != {"kind", "tag"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, "tag": text(value["tag"])}
        if kind == "global":
            if set(value) != {"kind", "name"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, "name": text(value["name"])}
        if kind == "local":
            if set(value) != {"kind", "binding", "name"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            identity = text(value["binding"], 64)
            if not re.fullmatch(r"[1-9][0-9]*:[1-9][0-9]*:[1-9][0-9]*:[1-9][0-9]*", identity):
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, "binding": identity, "name": text(value["name"])}
        if kind in {"string", "number"}:
            key = "raw"
            if set(value) != {"kind", key}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, key: text(value[key], MAX_SOURCE_CHARACTERS)}
        if kind == "boolean":
            if set(value) != {"kind", "value"} or type(value["value"]) is not bool:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, "value": value["value"]}
        if kind == "nil":
            if set(value) != {"kind"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind}
        if kind in {"indexname", "index"}:
            required = (
                {"kind", "base", "accessor", "name"}
                if kind == "indexname"
                else {
                    "kind",
                    "base",
                    "index",
                }
            )
            if set(value) != required:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            result = {"kind": kind, "base": expression(value["base"], depth + 1)}
            if kind == "indexname":
                accessor = value["accessor"]
                if accessor not in {".", ":"}:
                    raise LuteUnavailableError("the Lute checker returned an invalid result")
                result.update(accessor=accessor, name=text(value["name"]))
            else:
                result["index"] = expression(value["index"], depth + 1)
            return result
        if kind == "call":
            if set(value) != {"kind", "func", "arguments"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {
                "kind": kind,
                "func": expression(value["func"], depth + 1),
                "arguments": expressions(value["arguments"], depth + 1),
            }
        if kind == "binary":
            if set(value) != {"kind", "operator", "left", "right"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {
                "kind": kind,
                "operator": text(value["operator"]),
                "left": expression(value["left"], depth + 1),
                "right": expression(value["right"], depth + 1),
            }
        if kind == "unary":
            if set(value) != {"kind", "operator", "operand"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {
                "kind": kind,
                "operator": text(value["operator"]),
                "operand": expression(value["operand"], depth + 1),
            }
        if kind == "group":
            if set(value) != {"kind", "expression"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, "expression": expression(value["expression"], depth + 1)}
        raise LuteUnavailableError("the Lute checker returned an invalid result")

    def statement(value: object, depth: int) -> dict[str, Any]:
        nonlocal nodes
        nodes += 1
        if nodes > MAX_AST_NODES or depth > MAX_AST_DEPTH or not isinstance(value, dict):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        kind = value.get("kind")
        if not isinstance(kind, str):
            raise LuteUnavailableError("the Lute checker returned an invalid result")
        if kind == "unsupported":
            if set(value) != {"kind", "tag"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, "tag": text(value["tag"])}
        if kind == "block":
            if set(value) != {"kind", "statements"} or not isinstance(value["statements"], list):
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            if len(value["statements"]) > MAX_AST_NODES:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {
                "kind": kind,
                "statements": [statement(item, depth + 1) for item in value["statements"]],
            }
        if kind in {"local", "const"}:
            if set(value) != {"kind", "variables", "values"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            variables = value["variables"]
            if not isinstance(variables, list) or len(variables) > MAX_AST_NODES:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {
                "kind": kind,
                "variables": [binding(item) for item in variables],
                "values": expressions(value["values"], depth + 1),
            }
        if kind == "assign":
            if set(value) != {"kind", "targets", "values"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {
                "kind": kind,
                "targets": expressions(value["targets"], depth + 1),
                "values": expressions(value["values"], depth + 1),
            }
        if kind == "expression":
            if set(value) != {"kind", "expression"}:
                raise LuteUnavailableError("the Lute checker returned an invalid result")
            return {"kind": kind, "expression": expression(value["expression"], depth + 1)}
        raise LuteUnavailableError("the Lute checker returned an invalid result")

    result = statement(raw, 1)
    if result.get("kind") != "block":
        raise LuteUnavailableError("the Lute checker returned an invalid result")
    return result
