"""A stand-in for the Studio plugin, so the loop can be exercised without Roblox.

It speaks the protocol the way `apps/studio-plugin` will have to (ADR-0007: every
exchange is started here, and work arrives inside a poll response), but it **applies
nothing**: there is no place, no pre-flight and no verification at apply time. It reports
whatever `--outcome` says. It is a way to drive the API by hand, not a plugin and not a
test of anything in Studio.

    PLUGIN_AUTH_TOKEN=dev python tools/fake_plugin.py
    PLUGIN_AUTH_TOKEN=dev python tools/fake_plugin.py --outcome indeterminate
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid

DEFAULT_ENDPOINT = "http://127.0.0.1:8787/v1/messages"


def _post(endpoint: str, token: str, message: dict) -> dict:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(endpoint, data=body, method="POST")  # noqa: S310
    request.add_header("Content-Type", "application/json")
    request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            return json.loads(response.read())
    except urllib.error.HTTPError as error:
        return json.loads(error.read())
    except urllib.error.URLError as error:
        sys.exit(f"cannot reach {endpoint}: {error.reason}. Is `python -m api.cli serve` running?")


def _envelope(message_type: str, session: str | None, payload: dict) -> dict:
    message = {
        "protocol_version": {"major": 1, "minor": 0},
        "kind": "request",
        "type": message_type,
        "message_id": f"m-{uuid.uuid4().hex[:12]}",
        "payload": payload,
    }
    if session is not None:
        message["session_id"] = session
    return message


def _snapshot(reason: str, after: str | None = None) -> dict:
    payload = {
        "snapshot_id": f"snap-{uuid.uuid4().hex[:8]}",
        "reason": reason,
        "roots": ["Workspace"],
        "complete_depth": 1,
        "truncated": False,
        "entries": [{"path": ["Workspace"], "class_name": "Workspace"}],
    }
    if after is not None:
        payload["after_action_id"] = after
    return payload


def _result(action: dict, outcome: str) -> dict:
    """What this stand-in claims happened. It applied nothing (ADR-0011 section 9)."""
    operations = action["operations"]
    if outcome == "applied":
        statuses = ["applied"] * len(operations)
    elif outcome == "indeterminate":
        statuses = ["unknown"] + ["skipped"] * (len(operations) - 1)
    else:
        statuses = ["failed"] + ["skipped"] * (len(operations) - 1)
    reported = []
    for operation, status in zip(operations, statuses, strict=True):
        node = {"op_id": operation["op_id"], "status": status}
        if status == "failed":
            node["error"] = {"code": "operation_failed", "message": "This plugin applies nothing."}
        reported.append(node)
    return {"action_id": action["action_id"], "outcome": outcome, "operations": reported}


def main(argv: list[str] | None = None) -> None:
    """Open a session, send a snapshot, then poll and report until interrupted."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default=os.environ.get("API_ENDPOINT", DEFAULT_ENDPOINT))
    parser.add_argument(
        "--outcome",
        default="applied",
        choices=["applied", "rejected", "indeterminate"],
        help="what to report for an edit.action",
    )
    parser.add_argument("--once", action="store_true", help="stop after one work item")
    args = parser.parse_args(argv)

    token = os.environ.get("PLUGIN_AUTH_TOKEN", "").strip()
    if not token:
        sys.exit("PLUGIN_AUTH_TOKEN is not set.")

    hello = _post(
        args.endpoint,
        token,
        _envelope(
            "session.hello",
            None,
            {
                "client": {"name": "fake-plugin", "version": "0"},
                "supported": [{"major": 1, "max_minor": 0}],
            },
        ),
    )
    if hello["status"] != "ok":
        sys.exit(f"hello refused: {hello['payload']}")
    session = hello["session_id"]
    print(f"session {session}")

    _post(args.endpoint, token, _envelope("project.state", session, _snapshot("session_start")))

    while True:
        poll = _post(args.endpoint, token, _envelope("work.poll", session, {}))
        if poll["status"] != "ok":
            print(f"poll refused: {poll['payload']}")
            return
        work = poll["payload"].get("work")
        if work is None:
            print("no work")
            if args.once:
                return
            continue

        if work["type"] == "edit.action":
            print(f"edit.action {work['action_id']}: reporting {args.outcome}")
            payload = _result(work, args.outcome)
            answer = _post(args.endpoint, token, _envelope("edit.result", session, payload))
            after = work["action_id"]
        else:
            print(f"playtest.request {work['playtest_id']}: reporting completed")
            payload = {
                "playtest_id": work["playtest_id"],
                "outcome": "completed",
                "duration_ms": 0,
                "output": [{"t_ms": 0, "level": "info", "text": "This plugin runs nothing."}],
                "output_truncated": False,
            }
            answer = _post(args.endpoint, token, _envelope("playtest.report", session, payload))
            after = work["playtest_id"]

        if answer["status"] != "ok":
            print(f"the API refused the result: {answer['payload']}")
            return
        after_action = _envelope("project.state", session, _snapshot("after_action", after))
        _post(args.endpoint, token, after_action)
        if args.once:
            return


if __name__ == "__main__":
    main()
