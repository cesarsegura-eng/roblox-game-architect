"""The operator surface: run the service, queue and approve work, attest, read status.

Approval is a human act (ADR-0002), and so is the attestation that releases a lock
(ADR-0011 section 7). Both remain available here; the local web panel also supports
review and approval of script-free edit actions.

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
from .store import SQLiteStore

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
    return Service(SQLiteStore(root))


def _serve(args: argparse.Namespace) -> None:
    plugin_token = _credential()
    service = _service()
    world_token = os.environ.get("BLENDER_AUTH_TOKEN", "").strip()
    operator_token = os.environ.get("OPERATOR_AUTH_TOKEN", "").strip()
    blender_mcp_url = os.environ.get("BLENDER_MCP_URL", "").strip()
    blender_mcp_token = os.environ.get("BLENDER_MCP_BEARER_TOKEN", "").strip()
    roblox_mcp_url = os.environ.get("ROBLOX_MCP_URL", "").strip()
    roblox_mcp_token = os.environ.get("ROBLOX_MCP_BEARER_TOKEN", "").strip()
    roblox_asset_approval_secret = os.environ.get("RGA_ROBLOX_ASSET_APPROVAL_SECRET", "").strip()
    roblox_publish_approval_secret = os.environ.get(
        "RGA_ROBLOX_PUBLISH_APPROVAL_SECRET", ""
    ).strip()
    roblox_publish_universe_id = os.environ.get("RGA_ROBLOX_TEST_UNIVERSE_ID", "").strip()
    roblox_publish_place_id = os.environ.get("RGA_ROBLOX_TEST_PLACE_ID", "").strip()
    world_generator = None
    world_quoter = None
    game_plan_generator = None
    game_plan_quoter = None
    studio_action_generator = None
    studio_action_quoter = None
    code_preview_generator = None
    code_preview_quoter = None
    spend_status_provider = None
    blender_mcp = None
    roblox_mcp = None
    if blender_mcp_url:
        from .blender_mcp import BlenderMCPClient

        blender_mcp = BlenderMCPClient(blender_mcp_url, blender_mcp_token)
    elif blender_mcp_token:
        raise ValueError("BLENDER_MCP_BEARER_TOKEN requires BLENDER_MCP_URL")
    if roblox_mcp_url:
        from .roblox_mcp import RobloxMCPClient

        roblox_mcp = RobloxMCPClient(roblox_mcp_url, roblox_mcp_token)
    elif roblox_mcp_token:
        raise ValueError("ROBLOX_MCP_BEARER_TOKEN requires ROBLOX_MCP_URL")
    provider_configured = os.environ.get("LLM_PROVIDER", "fake").strip().lower() != "fake"
    if world_token or (operator_token and provider_configured):
        from core.budget import SpendBudget
        from core.game_planning import GamePlanningAgent
        from core.llm import create_provider
        from core.llm.types import LLMError
        from core.worldbuilding import WorldDesignAgent

        try:
            provider = create_provider()
        except LLMError as exc:
            raise ValueError(str(exc)) from exc
        if provider.name == "fake":
            if world_token:
                raise ValueError("Blender generation requires a real provider; set LLM_PROVIDER")
        else:
            spend = SpendBudget.from_env()

            def spend_status_provider() -> dict[str, str]:
                return {
                    "limit_usd": str(spend.limit),
                    "spent_usd": str(spend.spent),
                    "reserved_usd": str(spend.reserved),
                    "remaining_usd": str(spend.remaining),
                }

            def world_generator(brief: str) -> object:
                return WorldDesignAgent(provider, spend=spend).generate(brief)

            if operator_token:
                from core.studio_building import StudioBlockoutAgent
                from sandbox.action_policy import validate_action

                def game_plan_generator(brief: str) -> object:
                    return GamePlanningAgent(provider, spend=spend).generate(brief)

                def game_plan_quoter(brief: str) -> dict[str, str]:
                    agent = GamePlanningAgent(provider, spend=spend)
                    quote = agent.quote_next_call(brief)
                    if quote is None:
                        raise ValueError("provider did not return a maximum-cost quote")
                    return {
                        "provider": provider.name,
                        "model": getattr(provider, "model", "unknown"),
                        "first_call_max_usd": str(quote.max_usd),
                        "session_limit_usd": str(spend.limit),
                        "session_remaining_usd": str(spend.remaining),
                    }

                def world_quoter(brief: str) -> dict[str, str]:
                    agent = WorldDesignAgent(provider, spend=spend)
                    quote = agent.quote_next_call(brief)
                    if quote is None:
                        raise ValueError("provider did not return a maximum-cost quote")
                    return {
                        "provider": provider.name,
                        "model": getattr(provider, "model", "unknown"),
                        "first_call_max_usd": str(quote.max_usd),
                        "session_limit_usd": str(spend.limit),
                        "session_remaining_usd": str(spend.remaining),
                    }

                def studio_action_generator(brief: str) -> object:
                    return StudioBlockoutAgent(
                        provider, spend=spend, validator=validate_action
                    ).generate_with_trace(brief)

                def studio_action_quoter(brief: str) -> dict[str, str]:
                    agent = StudioBlockoutAgent(provider, spend=spend, validator=validate_action)
                    quote = agent.quote_next_call(brief)
                    if quote is None:
                        raise ValueError("provider did not return a maximum-cost quote")
                    return {
                        "provider": provider.name,
                        "model": getattr(provider, "model", "unknown"),
                        "first_call_max_usd": str(quote.max_usd),
                        "session_limit_usd": str(spend.limit),
                        "session_remaining_usd": str(spend.remaining),
                    }

                try:
                    from core.agent_loop import AgentLoop, BuildTask
                    from sandbox.parser import LuauParserError, LuteSyntaxParser
                    from sandbox.source_policy import LuauSourcePolicyValidator

                    validator = LuauSourcePolicyValidator(LuteSyntaxParser())

                    def code_preview_generator(description: str, scope: tuple[str, ...]) -> object:
                        task = BuildTask(description, scope)
                        return AgentLoop(provider, validator, spend=spend).run(task)

                    def code_preview_quoter(
                        description: str, scope: tuple[str, ...]
                    ) -> dict[str, str]:
                        task = BuildTask(description, scope)
                        quote = AgentLoop(provider, validator, spend=spend).quote_next_call(task)
                        if quote is None:
                            raise ValueError("provider did not return a maximum-cost quote")
                        return {
                            "provider": provider.name,
                            "model": getattr(provider, "model", "unknown"),
                            "first_call_max_usd": str(quote.max_usd),
                            "session_limit_usd": str(spend.limit),
                            "session_remaining_usd": str(spend.remaining),
                        }

                    print("operator Luau source preview and static policy gate enabled")
                except LuauParserError as exc:
                    print(f"operator Luau source preview disabled: {exc}")

    server = ApiServer(
        service,
        port=args.port,
        poll_timeout_s=args.poll_timeout,
        plugin_token=plugin_token,
        operator_token=operator_token or None,
        world_token=world_token or None,
        world_generator=world_generator,
        world_quoter=world_quoter,
        game_plan_generator=game_plan_generator,
        game_plan_quoter=game_plan_quoter,
        studio_action_generator=studio_action_generator,
        studio_action_quoter=studio_action_quoter,
        code_preview_generator=code_preview_generator,
        code_preview_quoter=code_preview_quoter,
        spend_status_provider=spend_status_provider,
        blender_mcp=blender_mcp,
        roblox_mcp=roblox_mcp,
        roblox_asset_approval_secret=roblox_asset_approval_secret,
        roblox_publish_approval_secret=roblox_publish_approval_secret,
        roblox_publish_universe_id=roblox_publish_universe_id,
        roblox_publish_place_id=roblox_publish_place_id,
    )
    print(f"listening on {server.endpoint}")
    if server.operator_token:
        print(f"local operator UI at http://127.0.0.1:{server.server_address[1]}/")
    if world_token and world_generator:
        print(f"Blender recipe endpoint enabled at {server.world_recipe_endpoint}")
    if world_generator and operator_token:
        print("operator world recipe generation and preflight quotes enabled")
    if game_plan_generator and game_plan_quoter:
        print("operator game planning and preflight quotes enabled")
    if studio_action_generator:
        print("operator Studio blockout generation and preflight quotes enabled")
    if blender_mcp:
        print(f"remote Blender MCP integration enabled for host {blender_mcp.audit_host}")
    if roblox_mcp:
        print(f"remote Roblox validation MCP enabled for host {roblox_mcp.audit_host}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _queue(args: argparse.Namespace) -> None:
    credential = _credential()
    item = json.loads(Path(args.file).read_text(encoding="utf-8"))
    work_id = _service().queue(credential, item)
    print(f"queued {work_id}; it is delivered only after `approve {work_id}`")


def _approve(args: argparse.Namespace) -> None:
    credential = _credential()
    _service().approve(credential, args.work_id)
    print(f"approved {args.work_id}")


def _attest(args: argparse.Namespace) -> None:
    credential = _credential()
    print(ATTESTATION_WARNING)
    _service().attest(credential, args.actor, ATTESTATION_WARNING, args.review)
    print("lock released; planning resumes once a fresh snapshot arrives")


def _status(args: argparse.Namespace) -> None:
    del args
    credential = _credential()
    print(json.dumps(_service().status(credential), indent=2))


def build_parser() -> argparse.ArgumentParser:
    """The command line. One subcommand per operator action."""
    parser = argparse.ArgumentParser(prog="api", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    serve = commands.add_parser("serve", help="run the HTTP service")
    serve.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", "8787")))
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
