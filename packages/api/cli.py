"""The operator surface: run the service, queue and approve work, attest, read status.

Approval is a human act (ADR-0002), and so is the attestation that releases a lock
(ADR-0011 section 7). Neither has a web surface yet — `apps/web` does not exist — so
until it does, this is where a person performs them.

    python -m api.cli serve
    python -m api.cli queue examples/action.json
    python -m api.cli approve a-0001
    python -m api.cli status
    python -m api.cli attest --actor you --note "Studio closed"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from .http import DEFAULT_POLL_TIMEOUT_S, ApiServer
from .service import Service
from .store import FileStore

ATTESTATION_WARNING = (
    "You are declaring that no Studio instance is still applying the uncertain work. "
    "The API cannot check this. If it is wrong, two executors may change one place at "
    "once."
)


def _credential() -> str:
    token = os.environ.get("PLUGIN_AUTH_TOKEN", "").strip()
    if not token:
        sys.exit("PLUGIN_AUTH_TOKEN is not set. See .env.example.")
    return token


def _service() -> Service:
    root = Path(os.environ.get("DATA_DIR", "./data")).expanduser() / "api"
    return Service(FileStore(root))


def _serve(args: argparse.Namespace) -> None:
    service = _service()
    server = ApiServer(service, port=args.port, poll_timeout_s=args.poll_timeout)
    print(f"listening on {server.endpoint}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _queue(args: argparse.Namespace) -> None:
    item = json.loads(Path(args.file).read_text(encoding="utf-8"))
    work_id = _service().queue(_credential(), item)
    print(f"queued {work_id}; it is delivered only after `approve {work_id}`")


def _approve(args: argparse.Namespace) -> None:
    _service().approve(_credential(), args.work_id)
    print(f"approved {args.work_id}")


def _attest(args: argparse.Namespace) -> None:
    print(ATTESTATION_WARNING)
    _service().attest(_credential(), args.actor, ATTESTATION_WARNING, args.review)
    print("lock released; planning resumes once a fresh snapshot arrives")


def _status(args: argparse.Namespace) -> None:
    del args
    print(json.dumps(_service().status(_credential()), indent=2))


def build_parser() -> argparse.ArgumentParser:
    """The command line. One subcommand per operator action."""
    parser = argparse.ArgumentParser(prog="api", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the HTTP service")
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--poll-timeout", type=float, default=DEFAULT_POLL_TIMEOUT_S)
    serve.set_defaults(run=_serve)

    queue = commands.add_parser("queue", help="add a work item, queued and unapproved")
    queue.add_argument("file", help="a JSON file holding an edit.action or a playtest.request")
    queue.set_defaults(run=_queue)

    approve = commands.add_parser("approve", help="approve a queued work item")
    approve.add_argument("work_id")
    approve.set_defaults(run=_approve)

    attest = commands.add_parser("attest", help="declare that the executor has stopped")
    attest.add_argument("--actor", required=True, help="who is declaring it")
    attest.add_argument("--review", help="for a conflict: the disposition of both results")
    attest.set_defaults(run=_attest)

    status = commands.add_parser("status", help="print the lifecycle state")
    status.set_defaults(run=_status)
    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for `python -m api.cli`."""
    args = build_parser().parse_args(argv)
    try:
        args.run(args)
    except (ValueError, OSError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
