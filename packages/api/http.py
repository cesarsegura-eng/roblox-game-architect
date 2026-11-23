"""HTTP transports for plugin polling and operator-reviewed scene workflows.

Plugin messages remain delegated to `messages.py` and `service.py`. Scene recipe
generation is an injected callback. Blender recipes can be sent to a separately
hosted MCP service after operator review. The standard library is enough for the
API transports, so this adds no runtime dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
import uuid
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files as package_files
from pathlib import Path
from typing import Any, Protocol

from core.agent_loop import BuildTask
from core.navigation import navigation_status, validate_failed_leg

from .json_profile import MAX_MESSAGE_BYTES, ProfileError, parse_strict, serialise
from .roblox_mcp import (
    MAX_GLB_UPLOAD_BYTES,
    RobloxAssetUploadReceipt,
    RobloxPlaceArtifact,
    RobloxPublishReceipt,
    RobloxValidationReceipt,
)
from .service import Service, handle_message

ENDPOINT = "/v1/messages"
DEFAULT_POLL_TIMEOUT_S = 25.0
_WAKE_S = 0.1
WORLD_RECIPE_ENDPOINT = "/v1/world/recipe"
MAX_WORLD_BRIEF_BYTES = 16_384
MAX_WORLD_RECIPE_BYTES = 1_048_576
MAX_GAME_PLAN_BYTES = 65_536
OPERATOR_STATUS_ENDPOINT = "/v1/operator/status"
OPERATOR_QUEUE_ENDPOINT = "/v1/operator/work"
OPERATOR_EVENTS_ENDPOINT = "/v1/operator/events"
OPERATOR_APPROVE_ENDPOINT = "/v1/operator/approve"
OPERATOR_WORLD_RECIPE_ENDPOINT = "/v1/operator/world-recipe"
OPERATOR_WORLD_QUOTE_ENDPOINT = "/v1/operator/world-quote"
OPERATOR_GAME_PLAN_ENDPOINT = "/v1/operator/game-plan"
OPERATOR_GAME_PLAN_QUOTE_ENDPOINT = "/v1/operator/game-plan-quote"
OPERATOR_RELEASE_READINESS_ENDPOINT = "/v1/operator/release-readiness"
OPERATOR_CODE_PREVIEW_ENDPOINT = "/v1/operator/code-preview"
OPERATOR_CODE_PREVIEW_QUOTE_ENDPOINT = "/v1/operator/code-preview-quote"
OPERATOR_STUDIO_ACTION_ENDPOINT = "/v1/operator/studio-action"
OPERATOR_STUDIO_RECIPE_ACTION_ENDPOINT = "/v1/operator/studio-recipe-action"
OPERATOR_STUDIO_QUOTE_ENDPOINT = "/v1/operator/studio-quote"
OPERATOR_BLENDER_APPLY_ENDPOINT = "/v1/operator/blender-apply"
OPERATOR_BLENDER_ARTIFACT_PREFIX = "/v1/operator/blender-artifact/"
OPERATOR_ROBLOX_VALIDATE_ENDPOINT = "/v1/operator/roblox-validate"
OPERATOR_ROBLOX_BUILD_ENDPOINT = "/v1/operator/roblox-build"
OPERATOR_ROBLOX_ASSET_UPLOAD_ENDPOINT = "/v1/operator/roblox-model-upload"
OPERATOR_ROBLOX_PUBLISH_ENDPOINT = "/v1/operator/roblox-publish"
OPERATOR_MCP_HEALTH_ENDPOINT = "/v1/operator/mcp-health"
MAX_OPERATOR_BODY_BYTES = MAX_WORLD_RECIPE_BYTES
try:
    _WEB_ROOT = package_files("apps").joinpath("web")
except ModuleNotFoundError:
    # Source checkouts may import ``api`` through packages/api without installing
    # the separately mapped apps package; wheels use the packaged resource path.
    _WEB_ROOT = Path(__file__).resolve().parents[2] / "apps" / "web"
_WEB_ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _provider_call_trace(responses: object) -> dict[str, Any]:
    """Return bounded per-call usage metadata, never model input or output text."""
    if not isinstance(responses, tuple) or not 1 <= len(responses) <= 128:
        raise ValueError("model call trace is malformed")
    providers: set[str] = set()
    models: set[str] = set()
    input_tokens = 0
    output_tokens = 0
    cost_usd = Decimal(0)
    attempts = []
    for number, response in enumerate(responses, start=1):
        provider = getattr(response, "provider", None)
        model = getattr(response, "model", None)
        usage = getattr(response, "usage", None)
        if (
            not isinstance(provider, str)
            or not provider
            or len(provider) > 80
            or any(ord(char) < 32 or ord(char) == 127 for char in provider)
            or not isinstance(model, str)
            or not model
            or len(model) > 80
            or any(ord(char) < 32 or ord(char) == 127 for char in model)
        ):
            raise ValueError("model call trace labels are malformed")
        response_input = getattr(usage, "input_tokens", None)
        response_output = getattr(usage, "output_tokens", None)
        response_cost = getattr(usage, "cost_usd", None)
        if (
            type(response_input) is not int
            or type(response_output) is not int
            or not 0 <= response_input <= 10_000_000
            or not 0 <= response_output <= 10_000_000
            or not isinstance(response_cost, Decimal)
            or not response_cost.is_finite()
            or response_cost < 0
            or response_cost > 1_000_000
            or len(str(response_cost)) > 64
        ):
            raise ValueError("model call trace usage is malformed")
        providers.add(provider)
        models.add(model)
        input_tokens += response_input
        output_tokens += response_output
        cost_usd += response_cost
        attempts.append(
            {
                "attempt": number,
                "provider": provider,
                "model": model,
                "input_tokens": response_input,
                "output_tokens": response_output,
                "cost_usd": str(response_cost),
            }
        )
    provider_label = ", ".join(sorted(providers))
    model_label = ", ".join(sorted(models))
    if len(provider_label) > 120 or len(model_label) > 120:
        raise ValueError("model call trace labels exceed their bounds")
    return {
        "provider": provider_label,
        "model": model_label,
        "iterations": len(responses),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": str(cost_usd),
        "attempts": attempts,
    }


def _generation_model_trace(result: object, response_field: str = "responses") -> dict[str, Any]:
    iterations = getattr(result, "iterations", None)
    responses = getattr(result, response_field, None)
    if type(iterations) is not int or not 1 <= iterations <= 128:
        raise ValueError("model generation iteration count is malformed")
    trace = _provider_call_trace(responses)
    if trace["iterations"] != iterations:
        raise ValueError("model generation trace iteration count differs")
    return trace


def _game_plan_model_trace(result: object) -> dict[str, Any]:
    """Return bounded run and per-call usage metadata without input or output text."""
    trace = _generation_model_trace(result)
    return {
        **{
            key: trace[key]
            for key in (
                "provider",
                "model",
                "iterations",
                "input_tokens",
                "output_tokens",
                "cost_usd",
            )
        },
        "model_trace": trace,
    }


def _parse_build_task(payload: dict[str, Any]) -> BuildTask:
    """Parse the bounded description and explicit Workspace scope for code preview."""
    if (
        set(payload) != {"description", "scope"}
        or not isinstance(payload["description"], str)
        or not isinstance(payload["scope"], list)
        or not all(isinstance(path, str) for path in payload["scope"])
    ):
        raise ValueError("Request must contain a string description and a list of scope paths.")
    return BuildTask(payload["description"].strip(), tuple(payload["scope"]))


class MCPHealthGateway(Protocol):
    """Read-only connection check for a restricted remote MCP contract."""

    def check_connection(self, *, timeout: float = 5.0) -> None: ...


class BlenderMCPGateway(MCPHealthGateway, Protocol):
    """Narrow remote recipe-import capability injected into the HTTP service."""

    audit_host: str

    def apply_recipe(self, recipe: dict[str, Any], request_id: str) -> BlenderArtifactReceipt: ...

    def download_artifact(
        self, artifact_id: str, *, expected_sha256: str | None = None
    ) -> bytes: ...


class BlenderArtifactReceipt(Protocol):
    request_id: str
    artifact_id: str
    recipe_name: str
    object_count: int
    artifact_sha256: str


class RobloxMCPGateway(MCPHealthGateway, Protocol):
    """Fixed-harness map validation hosted separately from the operator machine."""

    audit_host: str

    def validate_recipe(
        self, recipe: dict[str, Any], request_id: str
    ) -> RobloxValidationReceipt: ...

    def build_place(
        self,
        recipe: dict[str, Any],
        request_id: str,
        *,
        gameplay_mode: str = "blockout",
        gameplay_rules: list[dict[str, Any]] | None = None,
        model_asset_id: str | None = None,
    ) -> RobloxPlaceArtifact: ...

    def upload_reviewed_model(
        self,
        glb: bytes,
        *,
        request_id: str,
        approval_id: str,
        display_name: str,
        description: str,
        approval_secret: str,
    ) -> RobloxAssetUploadReceipt: ...

    def publish_reviewed_place(
        self,
        place_file: bytes,
        *,
        request_id: str,
        approval_id: str,
        approval_secret: str,
        universe_id: str,
        place_id: str,
    ) -> RobloxPublishReceipt: ...


class _Handler(BaseHTTPRequestHandler):
    """One request. The server instance carries the service and the settings."""

    server_version = "roblox-game-architect"
    sys_version = ""
    # A client that declares a body and then stalls must not hold a thread forever.
    # Long polls wait on the server side, so this does not cut them short.
    timeout = 30

    def do_GET(self) -> None:
        if self.path.startswith(OPERATOR_BLENDER_ARTIFACT_PREFIX):
            credential = self._operator_credential()
            if credential is None:
                self._operator_error(401, "unauthorized", "An operator token is required.")
                return
            artifact_id = self.path.removeprefix(OPERATOR_BLENDER_ARTIFACT_PREFIX)
            try:
                canonical_id = str(uuid.UUID(artifact_id))
            except ValueError:
                self._operator_error(404, "not_found", "No such Blender artifact.")
                return
            blender_mcp = self.server.blender_mcp  # type: ignore[attr-defined]
            if blender_mcp is None:
                self._operator_error(404, "disabled", "Remote Blender MCP is not configured.")
                return
            expected_sha256 = self.server.get_blender_artifact_sha256(  # type: ignore[attr-defined]
                canonical_id
            )
            if expected_sha256 is None:
                self._operator_error(
                    404, "not_found", "No verified Blender artifact receipt is available."
                )
                return
            try:
                artifact = blender_mcp.download_artifact(
                    canonical_id, expected_sha256=expected_sha256
                )
            except Exception:
                self._operator_error(
                    502, "artifact_unavailable", "The Blender artifact is unavailable."
                )
                return
            if not hmac.compare_digest(hashlib.sha256(artifact).hexdigest(), expected_sha256):
                self._operator_error(
                    502,
                    "artifact_digest_mismatch",
                    "The Blender artifact does not match its verified receipt.",
                )
                return
            self.send_response(200)
            self.send_header("Content-Type", "model/gltf-binary")
            self.send_header("Content-Length", str(len(artifact)))
            self.send_header(
                "Content-Disposition", f'attachment; filename="rga-{canonical_id}.glb"'
            )
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(artifact)
            return
        if self.path in _WEB_ASSETS:
            expected_host = f"127.0.0.1:{self.server.server_address[1]}".lower()
            if self.headers.get("Host", "").lower() != expected_host:
                self._plain(421, "Open the exact loopback URL printed by the API.")
                return
            filename, content_type = _WEB_ASSETS[self.path]
            try:
                body = _WEB_ROOT.joinpath(filename).read_bytes()
            except OSError:
                self._plain(404, "Web operator assets are unavailable in this checkout.")
                return
            self._send_raw(200, body, content_type)
            return
        if self.path == OPERATOR_STATUS_ENDPOINT:
            credential = self._operator_credential()
            if credential is None:
                self._operator_error(401, "unauthorized", "An operator token is required.")
                return
            state = self.server.service.status(self.server.plugin_token)  # type: ignore[attr-defined]
            self._json(
                200,
                {
                    "status": "ok",
                    "data": state,
                    "world_generation_enabled": self.server.world_generator is not None,
                    "world_quote_enabled": self.server.world_quoter is not None,
                    "game_plan_enabled": self.server.game_plan_generator is not None,
                    "game_plan_quote_enabled": self.server.game_plan_quoter is not None,
                    "code_preview_enabled": self.server.code_preview_generator is not None,
                    "code_preview_quote_enabled": self.server.code_preview_quoter is not None,
                    "studio_action_generation_enabled": self.server.studio_action_generator
                    is not None,
                    "studio_action_quote_enabled": self.server.studio_action_quoter is not None,
                    "blender_mcp_enabled": self.server.blender_mcp is not None,
                    "roblox_mcp_enabled": self.server.roblox_mcp is not None,
                    "roblox_asset_upload_enabled": self.server.roblox_asset_upload_enabled,
                    "roblox_place_publish_enabled": self.server.roblox_place_publish_enabled,
                    "spend_budget": (
                        self.server.spend_status_provider()
                        if self.server.spend_status_provider is not None
                        else None
                    ),
                },
            )
            return
        if self.path == OPERATOR_QUEUE_ENDPOINT:
            credential = self._operator_credential()
            if credential is None:
                self._operator_error(401, "unauthorized", "An operator token is required.")
                return
            items = self.server.service.operator_work_items(  # type: ignore[attr-defined]
                self.server.plugin_token  # type: ignore[attr-defined]
            )
            self._json(200, {"status": "ok", "items": items})
            return
        if self.path == OPERATOR_EVENTS_ENDPOINT:
            credential = self._operator_credential()
            if credential is None:
                self._operator_error(401, "unauthorized", "An operator token is required.")
                return
            events, total = self.server.service.operator_events(  # type: ignore[attr-defined]
                self.server.plugin_token  # type: ignore[attr-defined]
            )
            self._json(
                200,
                {
                    "status": "ok",
                    "events": events,
                    "total": total,
                    "truncated": total > len(events),
                },
            )
            return
        self._plain(404, "No such endpoint.")

    def do_POST(self) -> None:
        if self.path.startswith("/v1/operator/"):
            self._post_operator()
            return
        if self.path == WORLD_RECIPE_ENDPOINT:
            self._post_world_recipe()
            return
        if self.path != ENDPOINT:
            self._plain(404, "No such endpoint.")
            return
        credential = self._credential()
        plugin_token: str = self.server.plugin_token  # type: ignore[attr-defined]
        if (
            credential is None
            or not credential.isascii()
            or not hmac.compare_digest(credential, plugin_token)
        ):
            self._send(
                401,
                {
                    "protocol_version": {"major": 1, "minor": 0},
                    "kind": "response",
                    "message_id": "m-unauthorized",
                    "status": "error",
                    "payload": {
                        "code": "unauthorized",
                        "message": "A plugin token is required.",
                        "retryable": False,
                    },
                },
            )
            return
        raw_length = self.headers.get("Content-Length") or "0"
        # A negative or non-numeric length must never reach `read`: `read(-1)` would
        # block until the client closes the connection.
        if not (raw_length.isascii() and raw_length.isdecimal()):
            self.close_connection = True
            self._plain(400, "Content-Length is invalid.")
            return
        length = int(raw_length)
        if length > MAX_MESSAGE_BYTES:
            self.close_connection = True
            self._plain(413, "The message is larger than the protocol allows.")
            return
        try:
            body = self.rfile.read(length)
        except OSError:
            self.close_connection = True
            return

        service: Service = self.server.service  # type: ignore[attr-defined]
        timeout: float = self.server.poll_timeout_s  # type: ignore[attr-defined]
        response, hold = handle_message(service, credential, body)
        if hold:
            response = self._wait(service, credential, body, response, timeout)
        self._send(200, response)

    def _post_operator(self) -> None:
        credential = self._operator_credential()
        if credential is None:
            self._operator_error(401, "unauthorized", "An operator token is required.")
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._operator_error(400, "invalid_request", "Content-Length is invalid.")
            return
        if length < 1 or length > MAX_OPERATOR_BODY_BYTES:
            self.close_connection = length > MAX_OPERATOR_BODY_BYTES
            self._operator_error(
                413 if length > MAX_OPERATOR_BODY_BYTES else 400,
                "invalid_request",
                "Request body size is invalid.",
            )
            return
        try:
            payload = parse_strict(self.rfile.read(length))
        except ProfileError:
            self._operator_error(400, "invalid_request", "Request must be strict JSON.")
            return
        if not isinstance(payload, dict):
            self._operator_error(400, "invalid_request", "Request must be a JSON object.")
            return
        service: Service = self.server.service  # type: ignore[attr-defined]
        plugin_token: str = self.server.plugin_token  # type: ignore[attr-defined]
        try:
            if self.path == OPERATOR_MCP_HEALTH_ENDPOINT:
                if payload:
                    raise ValueError("Request body must be an empty JSON object.")

                def check_mcp(client: MCPHealthGateway | None) -> str:
                    if client is None:
                        return "not_configured"
                    try:
                        client.check_connection(timeout=5)
                    except Exception:
                        return "unavailable"
                    return "available"

                blender_health = check_mcp(self.server.blender_mcp)  # type: ignore[attr-defined]
                roblox = self.server.roblox_mcp  # type: ignore[attr-defined]
                roblox_health = check_mcp(roblox)
                self._json(
                    200,
                    {
                        "status": "ok",
                        "blender_mcp": blender_health,
                        "roblox_mcp": roblox_health,
                        "roblox_map_validation_available": (
                            roblox_health == "available"
                            and bool(getattr(roblox, "map_validation_available", False))
                        ),
                        "roblox_place_publish": (
                            "not_configured"
                            if not self.server.roblox_place_publish_enabled  # type: ignore[attr-defined]
                            else "available"
                            if roblox_health == "available"
                            and getattr(roblox, "place_publish_available", False)
                            else "unavailable"
                        ),
                    },
                )
            elif self.path == OPERATOR_QUEUE_ENDPOINT:
                if set(payload) != {"item"} or not isinstance(payload["item"], dict):
                    raise ValueError("Request must contain one object field named item.")
                work_id = service.queue(plugin_token, payload["item"])
                self._json(200, {"status": "ok", "work_id": work_id})
            elif self.path == OPERATOR_APPROVE_ENDPOINT:
                if set(payload) != {"work_id"} or not isinstance(payload["work_id"], str):
                    raise ValueError("Request must contain one string field named work_id.")
                service.approve(plugin_token, payload["work_id"])
                self._json(200, {"status": "ok", "work_id": payload["work_id"]})
            elif self.path == OPERATOR_WORLD_RECIPE_ENDPOINT:
                generator = self.server.world_generator  # type: ignore[attr-defined]
                if generator is None:
                    self._operator_error(404, "disabled", "World generation is not enabled.")
                    return
                if set(payload) != {"brief"} or not isinstance(payload["brief"], str):
                    raise ValueError("Request must contain one string field named brief.")
                brief = payload["brief"].strip()
                if not brief or len(brief.encode("utf-8")) > MAX_WORLD_BRIEF_BYTES:
                    raise ValueError("Brief must contain between 1 and 16384 UTF-8 bytes.")
                run_id = str(uuid.uuid4())
                started = time.monotonic()
                try:
                    generated = generator(brief)
                except Exception:
                    if self._record_failed_generation(run_id, "blender_scene_recipe", started):
                        self._operator_error(502, "generation_failed", "World generation failed.")
                    return
                try:
                    from core.worldbuilding import SceneRecipe, WorldBuildResult

                    model_trace = {}
                    if isinstance(generated, WorldBuildResult):
                        scene = SceneRecipe.from_mapping(generated.recipe.to_mapping())
                        model_trace = {"model_trace": _generation_model_trace(generated)}
                    elif isinstance(generated, str):
                        scene = SceneRecipe.from_json(generated)
                    else:
                        raise ValueError("world generator returned an unsupported result")
                    recipe = scene.to_json().encode("utf-8")
                    if len(recipe) > MAX_WORLD_RECIPE_BYTES:
                        raise ValueError("generated recipe exceeds the response size limit")
                except Exception:
                    if self._record_failed_generation(
                        run_id, "blender_scene_recipe", started, failure_stage="validation"
                    ):
                        self._operator_error(
                            502,
                            "generation_failed",
                            "World generation returned an invalid recipe.",
                        )
                    return
                try:
                    self._record_generation(
                        run_id=run_id,
                        operation="blender_scene_recipe",
                        succeeded=True,
                        duration_ms=_elapsed_ms(started),
                        summary={
                            "object_count": len(scene.objects),
                            "light_count": len(scene.lights),
                            "character_count": len(scene.characters),
                            "output_bytes": len(recipe),
                            **model_trace,
                        },
                    )
                except OSError:
                    self._operator_error(
                        500,
                        "audit_storage_error",
                        "World generation completed, but its audit record could not be saved.",
                    )
                    return
                self._send_raw(
                    200,
                    recipe,
                    "application/json; charset=utf-8",
                    extra_headers={"X-RGA-Run-ID": run_id},
                )
            elif self.path == OPERATOR_GAME_PLAN_ENDPOINT:
                generator = self.server.game_plan_generator  # type: ignore[attr-defined]
                if generator is None:
                    self._operator_error(404, "disabled", "Game planning is not enabled.")
                    return
                if set(payload) != {"brief"} or not isinstance(payload["brief"], str):
                    raise ValueError("Request must contain one string field named brief.")
                brief = payload["brief"].strip()
                if not brief or len(brief.encode("utf-8")) > MAX_WORLD_BRIEF_BYTES:
                    raise ValueError("Brief must contain between 1 and 16384 UTF-8 bytes.")
                run_id = str(uuid.uuid4())
                started = time.monotonic()
                try:
                    generated = generator(brief)
                except Exception:
                    if self._record_failed_generation(run_id, "game_plan", started):
                        self._operator_error(502, "generation_failed", "Game planning failed.")
                    return
                try:
                    from core.game_planning import GamePlan, GamePlanBuildResult

                    model_trace: dict[str, int | str] = {}
                    if isinstance(generated, GamePlanBuildResult):
                        plan = GamePlan.from_mapping(generated.plan.to_mapping())
                        model_trace = _game_plan_model_trace(generated)
                    elif isinstance(generated, str):
                        plan = GamePlan.from_json(generated)
                    else:
                        raise ValueError("game planner returned an unsupported result")
                    body = plan.to_json().encode("utf-8")
                    if len(body) > MAX_GAME_PLAN_BYTES:
                        raise ValueError("game plan exceeds the response size limit")
                except Exception:
                    if self._record_failed_generation(
                        run_id, "game_plan", started, failure_stage="validation"
                    ):
                        self._operator_error(
                            502,
                            "generation_failed",
                            "Game planning returned an invalid plan.",
                        )
                    return
                try:
                    self._record_generation(
                        run_id=run_id,
                        operation="game_plan",
                        succeeded=True,
                        duration_ms=_elapsed_ms(started),
                        summary={
                            "system_count": len(plan.systems),
                            "milestone_count": len(plan.milestones),
                            "output_bytes": len(body),
                            **model_trace,
                        },
                    )
                except OSError:
                    self._operator_error(
                        500,
                        "audit_storage_error",
                        "Game plan completed, but its audit record could not be saved.",
                    )
                    return
                self._send_raw(
                    200,
                    body,
                    "application/json; charset=utf-8",
                    extra_headers={"X-RGA-Run-ID": run_id},
                )
            elif self.path == OPERATOR_RELEASE_READINESS_ENDPOINT:
                if set(payload) != {"plan"}:
                    raise ValueError("Request must contain one Game Plan object named plan.")
                from core.release_readiness import review_release_readiness

                review = review_release_readiness(payload["plan"])
                self._json(200, {"status": "ok", "report": review})
            elif self.path == OPERATOR_CODE_PREVIEW_ENDPOINT:
                generator = self.server.code_preview_generator  # type: ignore[attr-defined]
                if generator is None:
                    self._operator_error(404, "disabled", "Luau source preview is not enabled.")
                    return
                if not isinstance(payload.get("quote_id"), str):
                    self._operator_error(
                        409,
                        "quote_required",
                        "Request a fresh quote for this exact task and scope before generating.",
                    )
                    return
                if set(payload) != {"description", "scope", "quote_id"}:
                    raise ValueError("Request must contain the quoted task and quote_id.")
                task = _parse_build_task(
                    {"description": payload["description"], "scope": payload["scope"]}
                )
                if not self.server.consume_code_preview_quote(payload["quote_id"], task):  # type: ignore[attr-defined]
                    self._operator_error(
                        409,
                        "quote_required",
                        "Request a fresh quote for this exact task and scope before generating.",
                    )
                    return
                run_id = str(uuid.uuid4())
                started = time.monotonic()
                try:
                    result = generator(task.description, task.scope)
                except Exception:
                    if self._record_failed_generation(run_id, "luau_source_preview", started):
                        self._operator_error(502, "generation_failed", "Code preview failed.")
                    return
                model_trace = {}
                if getattr(result, "usage", None) is not None:
                    try:
                        model_trace = {"model_trace": _generation_model_trace(result, "usage")}
                    except ValueError:
                        if self._record_failed_generation(
                            run_id, "luau_source_preview", started, failure_stage="validation"
                        ):
                            self._operator_error(
                                422,
                                "policy_rejected",
                                "Code preview returned invalid model usage metadata.",
                            )
                        return
                validation = getattr(result, "validation", None)
                source = getattr(result, "source", None)
                iterations = getattr(result, "iterations", None)
                if (
                    source is None
                    or getattr(result, "succeeded", False) is not True
                    or getattr(validation, "passed", False) is not True
                    or not isinstance(source, str)
                    or len(source.encode("utf-8")) > 100_000
                    or type(iterations) is not int
                    or not 1 <= iterations <= 128
                ):
                    if self._record_failed_generation(
                        run_id, "luau_source_preview", started, failure_stage="validation"
                    ):
                        self._operator_error(
                            422,
                            "policy_rejected",
                            "No source passed the restricted static scene-blockout policy.",
                        )
                    return
                try:
                    self._record_generation(
                        run_id=run_id,
                        operation="luau_source_preview",
                        succeeded=True,
                        duration_ms=_elapsed_ms(started),
                        summary={
                            "iterations": iterations,
                            "source_bytes": len(source.encode("utf-8")),
                            **model_trace,
                        },
                    )
                except OSError:
                    self._operator_error(
                        500,
                        "audit_storage_error",
                        "Code preview completed, but its audit record could not be saved.",
                    )
                    return
                self._json(
                    200,
                    {
                        "status": "ok",
                        "run_id": run_id,
                        "source": source,
                        "validation": "passed",
                        "iterations": iterations,
                        "execution_enabled": False,
                        "studio_delivery_enabled": False,
                    },
                )
            elif self.path in {
                OPERATOR_WORLD_QUOTE_ENDPOINT,
                OPERATOR_GAME_PLAN_QUOTE_ENDPOINT,
                OPERATOR_STUDIO_QUOTE_ENDPOINT,
                OPERATOR_CODE_PREVIEW_QUOTE_ENDPOINT,
            }:
                is_studio_quote = self.path == OPERATOR_STUDIO_QUOTE_ENDPOINT
                is_game_plan_quote = self.path == OPERATOR_GAME_PLAN_QUOTE_ENDPOINT
                is_code_quote = self.path == OPERATOR_CODE_PREVIEW_QUOTE_ENDPOINT
                quoter = (
                    self.server.code_preview_quoter
                    if is_code_quote
                    else (
                        self.server.studio_action_quoter
                        if is_studio_quote
                        else (
                            self.server.game_plan_quoter
                            if is_game_plan_quote
                            else self.server.world_quoter
                        )
                    )
                )  # type: ignore[attr-defined]
                if quoter is None:
                    self._operator_error(404, "disabled", "Cost quotes are not enabled.")
                    return
                if is_code_quote:
                    task = _parse_build_task(payload)
                    try:
                        quote = quoter(task.description, task.scope)
                    except Exception:
                        self._operator_error(
                            503,
                            "quote_unavailable",
                            "A maximum-cost estimate is unavailable; generation remains blocked.",
                        )
                        return
                else:
                    if set(payload) != {"brief"} or not isinstance(payload["brief"], str):
                        raise ValueError("Request must contain one string field named brief.")
                    brief = payload["brief"].strip()
                    if not brief or len(brief.encode("utf-8")) > MAX_WORLD_BRIEF_BYTES:
                        raise ValueError("Brief must contain between 1 and 16384 UTF-8 bytes.")
                    try:
                        quote = quoter(brief)
                    except Exception:
                        self._operator_error(
                            503,
                            "quote_unavailable",
                            "A maximum-cost estimate is unavailable; generation remains blocked.",
                        )
                        return
                if not isinstance(quote, dict) or set(quote) != {
                    "provider",
                    "model",
                    "first_call_max_usd",
                    "session_limit_usd",
                    "session_remaining_usd",
                }:
                    self._operator_error(503, "quote_unavailable", "Cost estimate is invalid.")
                    return
                if any(
                    not isinstance(quote[field], str)
                    or not quote[field]
                    or len(quote[field]) > 120
                    or any(ord(char) < 32 for char in quote[field])
                    for field in ("provider", "model")
                ):
                    self._operator_error(503, "quote_unavailable", "Cost estimate is invalid.")
                    return
                try:
                    money_fields = (
                        "first_call_max_usd",
                        "session_limit_usd",
                        "session_remaining_usd",
                    )
                    if any(not isinstance(quote[field], str) for field in money_fields):
                        raise InvalidOperation
                    money = [Decimal(quote[field]) for field in money_fields]
                    if any(not value.is_finite() or value < 0 for value in money):
                        raise InvalidOperation
                except (InvalidOperation, TypeError, ValueError):
                    self._operator_error(503, "quote_unavailable", "Cost estimate is invalid.")
                    return
                if money[0] > money[2]:
                    self._operator_error(
                        409,
                        "insufficient_budget",
                        "The first-call maximum cost exceeds the remaining session budget.",
                    )
                    return
                response = {"status": "ok", **quote}
                if is_code_quote:
                    response["quote_id"] = self.server.issue_code_preview_quote(task)  # type: ignore[attr-defined]
                self._json(200, response)
            elif self.path == OPERATOR_STUDIO_ACTION_ENDPOINT:
                generator = self.server.studio_action_generator  # type: ignore[attr-defined]
                if generator is None:
                    self._operator_error(
                        404, "disabled", "Studio action generation is not enabled."
                    )
                    return
                if set(payload) != {"brief"} or not isinstance(payload["brief"], str):
                    raise ValueError("Request must contain one string field named brief.")
                brief = payload["brief"].strip()
                if not brief or len(brief.encode("utf-8")) > MAX_WORLD_BRIEF_BYTES:
                    raise ValueError("Brief must contain between 1 and 16384 UTF-8 bytes.")
                run_id = str(uuid.uuid4())
                started = time.monotonic()
                try:
                    from core.studio_building import StudioBlockoutBuildResult

                    generated = generator(brief)
                    if isinstance(generated, StudioBlockoutBuildResult):
                        item = generated.action
                        model_trace = _generation_model_trace(generated)
                    elif isinstance(generated, dict):
                        item = generated
                        model_trace = None
                    else:
                        raise ValueError("Studio blockout generator returned an unsupported result")
                except Exception:
                    if self._record_failed_generation(run_id, "studio_blockout", started):
                        self._operator_error(
                            502, "generation_failed", "Studio blockout generation failed."
                        )
                    return
                try:
                    work_id = service.queue(
                        plugin_token,
                        item,
                        generation_run_id=run_id,
                        generation_duration_ms=_elapsed_ms(started),
                        generation_model_trace=model_trace,
                        workflow_id=run_id,
                    )
                except Exception:
                    if self._record_failed_generation(
                        run_id, "studio_blockout", started, failure_stage="queue"
                    ):
                        self._operator_error(
                            502, "queue_failed", "Generated Studio action could not be queued."
                        )
                    return
                self._json(
                    200,
                    {"status": "ok", "run_id": run_id, "work_id": work_id, "item": item},
                )
            elif self.path == OPERATOR_STUDIO_RECIPE_ACTION_ENDPOINT:
                if (
                    set(payload) != {"recipe", "request_id"}
                    or not isinstance(payload["recipe"], dict)
                    or not isinstance(payload["request_id"], str)
                ):
                    raise ValueError("Request must contain recipe and request_id fields.")
                try:
                    request_id = str(uuid.UUID(payload["request_id"]))
                except ValueError as exc:
                    raise ValueError("request_id must be a UUID.") from exc
                if request_id != payload["request_id"].lower():
                    raise ValueError("request_id must use canonical UUID syntax.")
                from core.scene_to_studio import scene_recipe_to_studio_action
                from core.worldbuilding import SceneRecipe

                recipe = SceneRecipe.from_mapping(payload["recipe"])
                item = scene_recipe_to_studio_action(recipe, request_id)
                existing = next(
                    (
                        entry
                        for entry in service.operator_work_items(plugin_token)
                        if entry.get("work_id") == item["action_id"]
                    ),
                    None,
                )
                if existing is not None:
                    if existing.get("item") != item:
                        raise ValueError(
                            "request_id was already used for a different scene recipe."
                        )
                    work_id = item["action_id"]
                    work_state = existing.get("state")
                    replayed = True
                else:
                    work_id = service.queue(plugin_token, item, workflow_id=request_id)
                    work_state = "queued"
                    replayed = False
                proxy_count = sum(
                    operation.get("op") == "create_instance"
                    and operation.get("class_name") == "Part"
                    for operation in item["operations"]
                )
                self._json(
                    200,
                    {
                        "status": "ok",
                        "work_id": work_id,
                        "work_state": work_state,
                        "replayed": replayed,
                        "proxy_part_count": proxy_count,
                        "source_object_count": len(recipe.objects),
                        "omitted_object_count": len(recipe.objects) - proxy_count,
                        "omitted_light_count": len(recipe.lights),
                        "omitted_character_count": len(recipe.characters),
                        "item": item,
                    },
                )
            elif self.path == OPERATOR_BLENDER_APPLY_ENDPOINT:
                blender_mcp = self.server.blender_mcp  # type: ignore[attr-defined]
                if blender_mcp is None:
                    self._operator_error(404, "disabled", "Remote Blender MCP is not configured.")
                    return
                if (
                    set(payload) != {"recipe", "request_id"}
                    or not isinstance(payload["recipe"], dict)
                    or not isinstance(payload["request_id"], str)
                ):
                    raise ValueError("Request must contain recipe and request_id fields.")
                try:
                    uuid.UUID(payload["request_id"])
                except ValueError as exc:
                    raise ValueError("request_id must be a UUID.") from exc
                from core.worldbuilding import SceneRecipe

                recipe = SceneRecipe.from_mapping(payload["recipe"])
                try:
                    receipt = blender_mcp.apply_recipe(recipe.to_mapping(), payload["request_id"])
                except Exception:
                    self._operator_error(
                        502,
                        "remote_outcome_uncertain",
                        "The remote server did not confirm the build. "
                        "Retry with the same request ID to recover its artifact.",
                    )
                    return
                if (
                    getattr(receipt, "request_id", None) != payload["request_id"]
                    or not isinstance(getattr(receipt, "artifact_id", None), str)
                    or getattr(receipt, "recipe_name", None) != recipe.name
                    or getattr(receipt, "object_count", None) != recipe.rendered_object_count
                    or not isinstance(getattr(receipt, "artifact_sha256", None), str)
                    or not re.fullmatch(r"[0-9a-f]{64}", receipt.artifact_sha256)
                ):
                    self._operator_error(
                        502,
                        "remote_receipt_invalid",
                        "The remote server did not return a verified scene artifact receipt.",
                    )
                    return
                try:
                    service.record_blender_artifact_built(
                        plugin_token,
                        recipe_name=recipe.name,
                        object_count=recipe.rendered_object_count,
                        request_id=payload["request_id"],
                        artifact_id=receipt.artifact_id,
                        artifact_sha256=receipt.artifact_sha256,
                        remote_host=blender_mcp.audit_host,
                    )
                except OSError:
                    self._operator_error(
                        500,
                        "audit_storage_error",
                        "Blender confirmed the build, but the API could not "
                        "persist the audit event.",
                    )
                    return
                self.server.remember_blender_artifact(  # type: ignore[attr-defined]
                    receipt.artifact_id, receipt.artifact_sha256
                )
                self._json(
                    200,
                    {
                        "status": "ok",
                        "recipe_name": recipe.name,
                        "object_count": recipe.rendered_object_count,
                        "artifact_id": receipt.artifact_id,
                        "artifact_sha256": receipt.artifact_sha256,
                    },
                )
            elif self.path == OPERATOR_ROBLOX_VALIDATE_ENDPOINT:
                roblox_mcp = self.server.roblox_mcp  # type: ignore[attr-defined]
                if roblox_mcp is None:
                    self._operator_error(
                        404, "disabled", "Remote Roblox validation MCP is not configured."
                    )
                    return
                if (
                    set(payload) != {"recipe", "request_id"}
                    or not isinstance(payload["recipe"], dict)
                    or not isinstance(payload["request_id"], str)
                ):
                    raise ValueError("Request must contain recipe and request_id fields.")
                try:
                    uuid.UUID(payload["request_id"])
                except ValueError as exc:
                    raise ValueError("request_id must be a UUID.") from exc
                from core.worldbuilding import SceneRecipe

                recipe = SceneRecipe.from_mapping(payload["recipe"])
                try:
                    receipt = roblox_mcp.validate_recipe(recipe.to_mapping(), payload["request_id"])
                except Exception:
                    self._operator_error(
                        502,
                        "remote_outcome_uncertain",
                        "The remote validation result is unavailable. Retry with the same request "
                        "ID; "
                        "an uncertain task will not be resubmitted.",
                    )
                    return
                try:
                    task_id = str(uuid.UUID(receipt.task_id))
                except (AttributeError, TypeError, ValueError):
                    task_id = ""
                try:
                    expected_navigation_status = navigation_status(
                        recipe,
                        getattr(receipt, "path_feature_count", None),
                        getattr(receipt, "navigation_waypoint_count", None),
                        getattr(receipt, "navigation_connected", None),
                    )
                    validate_failed_leg(
                        recipe,
                        expected_navigation_status,
                        getattr(receipt, "navigation_failed_leg", None),
                        getattr(receipt, "navigation_waypoint_count", None),
                    )
                except (TypeError, ValueError):
                    expected_navigation_status = None
                if (
                    getattr(receipt, "request_id", None) != payload["request_id"]
                    or task_id != getattr(receipt, "task_id", None)
                    or not isinstance(getattr(receipt, "place_version", None), str)
                    or not receipt.place_version.isdecimal()
                    or type(getattr(receipt, "object_count", None)) is not int
                    or receipt.object_count != len(recipe.objects)
                    or type(getattr(receipt, "path_feature_count", None)) is not int
                    or type(getattr(receipt, "navigation_waypoint_count", None)) is not int
                    or type(getattr(receipt, "navigation_connected", None)) is not bool
                    or getattr(receipt, "validation_status", None)
                    not in {"structure_only", "navigation_pass", "navigation_failed"}
                    or (receipt.validation_status == "navigation_failed")
                    != (getattr(receipt, "navigation_failed_leg", None) is not None)
                    or receipt.validation_status != expected_navigation_status
                ):
                    self._operator_error(
                        502,
                        "remote_receipt_invalid",
                        "Remote Roblox validation returned an invalid receipt.",
                    )
                    return
                try:
                    service.record_roblox_map_validation(
                        plugin_token,
                        request_id=receipt.request_id,
                        place_version=receipt.place_version,
                        task_id=receipt.task_id,
                        recipe_name=recipe.name,
                        object_count=receipt.object_count,
                        path_feature_count=receipt.path_feature_count,
                        navigation_waypoint_count=receipt.navigation_waypoint_count,
                        navigation_connected=receipt.navigation_connected,
                        validation_status=receipt.validation_status,
                        navigation_failed_leg=receipt.navigation_failed_leg,
                        remote_host=roblox_mcp.audit_host,
                    )
                except (OSError, ValueError):
                    self._operator_error(
                        500,
                        "audit_storage_error",
                        "Roblox validation completed, but its audit could not be saved.",
                    )
                    return
                self._json(
                    200,
                    {
                        "status": "ok",
                        "validation": {
                            "request_id": receipt.request_id,
                            "place_version": receipt.place_version,
                            "task_id": receipt.task_id,
                            "validation_status": receipt.validation_status,
                            "object_count": receipt.object_count,
                            "path_feature_count": receipt.path_feature_count,
                            "navigation_waypoint_count": receipt.navigation_waypoint_count,
                            "navigation_connected": receipt.navigation_connected,
                            "navigation_failed_leg": receipt.navigation_failed_leg,
                        },
                    },
                )
            elif self.path == OPERATOR_ROBLOX_BUILD_ENDPOINT:
                roblox_mcp = self.server.roblox_mcp  # type: ignore[attr-defined]
                if roblox_mcp is None:
                    self._operator_error(404, "disabled", "Remote Roblox MCP is not configured.")
                    return
                if (
                    set(payload)
                    - {"recipe", "request_id", "gameplay_mode", "gameplay_rules", "model_asset_id"}
                    or not {"recipe", "request_id"} <= set(payload)
                    or not isinstance(payload["recipe"], dict)
                    or not isinstance(payload["request_id"], str)
                ):
                    raise ValueError("Request must contain recipe and request_id fields.")
                gameplay_mode = payload.get("gameplay_mode", "blockout")
                from core.gameplay_templates import GAMEPLAY_MODES

                if not isinstance(gameplay_mode, str) or gameplay_mode not in GAMEPLAY_MODES:
                    raise ValueError("gameplay_mode is not supported.")
                model_asset_id = payload.get("model_asset_id")
                if model_asset_id is not None and (
                    not isinstance(model_asset_id, str)
                    or not re.fullmatch(r"[1-9][0-9]{0,19}", model_asset_id, re.ASCII)
                ):
                    raise ValueError("model_asset_id must be a positive decimal Roblox asset ID.")
                try:
                    request_id = str(uuid.UUID(payload["request_id"]))
                except ValueError as exc:
                    raise ValueError("request_id must be a UUID.") from exc
                if request_id != payload["request_id"].lower():
                    raise ValueError("request_id must use canonical UUID syntax.")
                from core.gameplay_templates import validate_gameplay_mode
                from core.worldbuilding import SceneRecipe

                recipe = SceneRecipe.from_mapping(payload["recipe"])
                gameplay_rules = payload.get("gameplay_rules")
                validate_gameplay_mode(gameplay_mode, recipe, gameplay_rules)
                try:
                    if model_asset_id is None:
                        if gameplay_rules is None:
                            artifact = roblox_mcp.build_place(
                                recipe.to_mapping(), request_id, gameplay_mode=gameplay_mode
                            )
                        else:
                            artifact = roblox_mcp.build_place(
                                recipe.to_mapping(),
                                request_id,
                                gameplay_mode=gameplay_mode,
                                gameplay_rules=gameplay_rules,
                            )
                    else:
                        artifact = roblox_mcp.build_place(
                            recipe.to_mapping(),
                            request_id,
                            gameplay_mode=gameplay_mode,
                            model_asset_id=model_asset_id,
                        )
                except Exception:
                    self._operator_error(
                        502,
                        "remote_build_failed",
                        "Remote Roblox place build failed; the place was not published.",
                    )
                    return
                if artifact.request_id != request_id or len(artifact.place_file) > 8_000_000:
                    self._operator_error(
                        502,
                        "remote_receipt_invalid",
                        "Remote Roblox place build returned an invalid artifact.",
                    )
                    return
                if self.server.roblox_place_publish_enabled:  # type: ignore[attr-defined]
                    self.server.remember_place_artifact(artifact)  # type: ignore[attr-defined]
                import base64

                self._json(
                    200,
                    {
                        "status": "ok",
                        "filename": f"{recipe.name[:40]}-{gameplay_mode}.rbxlx",
                        "sha256": artifact.sha256,
                        "place_file_base64": base64.b64encode(artifact.place_file).decode("ascii"),
                        "object_count": artifact.object_count,
                        "part_count": artifact.part_count,
                        "light_count": artifact.light_count,
                        "approximated_object_count": artifact.approximated_object_count,
                        "omitted_character_count": artifact.omitted_character_count,
                        "omitted_sun_light_count": artifact.omitted_sun_light_count,
                        "gameplay_mode": artifact.gameplay_mode,
                        "imported_meshpart_count": getattr(artifact, "imported_meshpart_count", 0),
                    },
                )
            elif self.path == OPERATOR_ROBLOX_PUBLISH_ENDPOINT:
                required = {"request_id", "approval_id", "sha256", "reviewed_in_studio"}
                if set(payload) != required or payload.get("reviewed_in_studio") is not True:
                    raise ValueError("Review the exact build in Studio and confirm publication.")
                for key in ("request_id", "approval_id", "sha256"):
                    if not isinstance(payload[key], str):
                        raise ValueError(f"{key} must be a string.")
                try:
                    request_id = str(uuid.UUID(payload["request_id"]))
                    approval_id = str(uuid.UUID(payload["approval_id"]))
                except ValueError as exc:
                    raise ValueError("Publish request and approval IDs must be UUIDs.") from exc
                if (
                    request_id != payload["request_id"].lower()
                    or approval_id != payload["approval_id"].lower()
                ):
                    raise ValueError("Publish request and approval IDs must be canonical UUIDs.")
                digest = payload["sha256"]
                if not re.fullmatch(r"[0-9a-f]{64}", digest, re.ASCII):
                    raise ValueError("sha256 must be lowercase hexadecimal.")
                roblox_mcp = self.server.roblox_mcp  # type: ignore[attr-defined]
                if roblox_mcp is None or not self.server.roblox_place_publish_enabled:  # type: ignore[attr-defined]
                    self._operator_error(
                        404, "disabled", "Reviewed test-place publishing is not configured."
                    )
                    return
                place_file = self.server.get_place_artifact(request_id, digest)  # type: ignore[attr-defined]
                if place_file is None:
                    self._operator_error(
                        409,
                        "artifact_unavailable",
                        "Build the place again; this API session no longer holds that artifact.",
                    )
                    return
                try:
                    receipt = roblox_mcp.publish_reviewed_place(
                        place_file,
                        request_id=request_id,
                        approval_id=approval_id,
                        approval_secret=self.server.roblox_publish_approval_secret,  # type: ignore[attr-defined]
                        universe_id=self.server.roblox_publish_universe_id,  # type: ignore[attr-defined]
                        place_id=self.server.roblox_publish_place_id,  # type: ignore[attr-defined]
                    )
                except Exception:
                    self._operator_error(
                        502,
                        "publish_uncertain",
                        "Roblox did not confirm the publication. Retry only with the same "
                        "request and approval IDs.",
                    )
                    return
                try:
                    service.record_roblox_place_published(
                        plugin_token,
                        request_id=receipt.request_id,
                        approval_id=receipt.approval_id,
                        artifact_sha256=receipt.artifact_sha256,
                        universe_id=receipt.universe_id,
                        place_id=receipt.place_id,
                        version_number=receipt.version_number,
                        remote_host=roblox_mcp.audit_host,
                    )
                except (OSError, ValueError):
                    self._operator_error(
                        500,
                        "audit_storage_error",
                        "Roblox published the test place, but the API could not save its receipt.",
                    )
                    return
                self._json(
                    200,
                    {
                        "status": "ok",
                        "publication": {
                            "request_id": receipt.request_id,
                            "approval_id": receipt.approval_id,
                            "artifact_sha256": receipt.artifact_sha256,
                            "universe_id": receipt.universe_id,
                            "place_id": receipt.place_id,
                            "version_number": receipt.version_number,
                        },
                    },
                )
            elif self.path == "/v1/operator/roblox-model-status":
                roblox_mcp = self.server.roblox_mcp
                if roblox_mcp is None:
                    self._operator_error(404, "disabled", "Remote Roblox is not configured.")
                    return
                if set(payload) != {"request_id"} or not isinstance(payload["request_id"], str):
                    raise ValueError("Request must contain a request_id UUID.")
                request_id = str(uuid.UUID(payload["request_id"]))
                if request_id != payload["request_id"].lower():
                    raise ValueError("request_id must use canonical UUID syntax.")
                try:
                    receipt = roblox_mcp.check_model_upload(request_id)
                    if receipt.request_id != request_id:
                        raise ValueError("Mismatched receipt")
                except Exception:
                    self._operator_error(
                        502, "remote_status_failed", "Could not verify the model upload status."
                    )
                    return
                self._json(
                    200,
                    {
                        "status": "ok",
                        "asset": {
                            "request_id": receipt.request_id,
                            "approval_id": receipt.approval_id,
                            "artifact_sha256": receipt.artifact_sha256,
                            "asset_id": receipt.asset_id,
                            "operation_id": receipt.operation_id,
                            "moderation_state": receipt.moderation_state,
                            "status": receipt.status,
                        },
                    },
                )
            elif self.path == OPERATOR_ROBLOX_ASSET_UPLOAD_ENDPOINT:
                blender_mcp = self.server.blender_mcp  # type: ignore[attr-defined]
                roblox_mcp = self.server.roblox_mcp  # type: ignore[attr-defined]
                approval_secret = self.server.roblox_asset_approval_secret  # type: ignore[attr-defined]
                if blender_mcp is None or roblox_mcp is None or not approval_secret:
                    self._operator_error(
                        404, "disabled", "Reviewed remote Roblox Model upload is not configured."
                    )
                    return
                fields = {"artifact_id", "request_id", "approval_id", "display_name", "description"}
                if set(payload) != fields or any(
                    not isinstance(payload[key], str) for key in fields
                ):
                    raise ValueError("Request must contain the five reviewed asset fields.")
                ids: dict[str, str] = {}
                for key in ("artifact_id", "request_id", "approval_id"):
                    try:
                        canonical = str(uuid.UUID(payload[key]))
                    except ValueError as exc:
                        raise ValueError(f"{key} must be a UUID.") from exc
                    if canonical != payload[key].lower():
                        raise ValueError(f"{key} must use canonical UUID syntax.")
                    ids[key] = canonical
                display_name = payload["display_name"].strip()
                description = payload["description"].strip()
                if not display_name or len(display_name) > 80:
                    raise ValueError("Model display name must contain 1-80 characters.")
                if not description or len(description) > 1000:
                    raise ValueError("Model description must contain 1-1000 characters.")
                try:
                    expected_sha256 = self.server.get_blender_artifact_sha256(  # type: ignore[attr-defined]
                        ids["artifact_id"]
                    )
                    glb = blender_mcp.download_artifact(
                        ids["artifact_id"], expected_sha256=expected_sha256
                    )
                    if not 20 <= len(glb) <= MAX_GLB_UPLOAD_BYTES:
                        raise ValueError("Blender artifact exceeds the Roblox Model upload limit.")
                    from .blender_mcp import BlenderMCPClient

                    BlenderMCPClient._validate_glb_bytes(glb)
                    receipt = roblox_mcp.upload_reviewed_model(
                        glb,
                        request_id=ids["request_id"],
                        approval_id=ids["approval_id"],
                        display_name=display_name,
                        description=description,
                        approval_secret=approval_secret,
                    )
                except ValueError:
                    raise
                except Exception:
                    self._operator_error(
                        502,
                        "remote_upload_uncertain",
                        "The remote asset operation failed or is uncertain; retry only with "
                        "the same request ID.",
                    )
                    return
                digest = hashlib.sha256(glb).hexdigest()
                if (
                    receipt.request_id != ids["request_id"]
                    or receipt.approval_id != ids["approval_id"]
                    or receipt.artifact_sha256 != digest
                    or not re.fullmatch(r"[1-9][0-9]{0,19}", receipt.asset_id)
                    or receipt.status not in {"approved", "moderation_pending", "rejected"}
                ):
                    self._operator_error(
                        502,
                        "remote_receipt_invalid",
                        "Remote Roblox returned an invalid Model asset receipt.",
                    )
                    return
                try:
                    service.record_roblox_model_asset_uploaded(
                        plugin_token,
                        request_id=ids["request_id"],
                        approval_id=ids["approval_id"],
                        artifact_sha256=digest,
                        asset_id=receipt.asset_id,
                        moderation_state=receipt.moderation_state,
                        status=receipt.status,
                        remote_host=roblox_mcp.audit_host,
                    )
                except (OSError, ValueError):
                    self._operator_error(
                        500,
                        "audit_storage_error",
                        "Roblox created or recovered the asset, but its audit receipt could "
                        "not be saved.",
                    )
                    return
                self._json(
                    200,
                    {
                        "status": "ok",
                        "asset": {
                            "request_id": receipt.request_id,
                            "approval_id": receipt.approval_id,
                            "artifact_sha256": receipt.artifact_sha256,
                            "asset_id": receipt.asset_id,
                            "operation_id": receipt.operation_id,
                            "moderation_state": receipt.moderation_state,
                            "status": receipt.status,
                        },
                    },
                )
            else:
                self._operator_error(404, "not_found", "No such endpoint.")
        except ValueError as exc:
            self._operator_error(400, "invalid_request", str(exc)[:500])
        except OSError:
            self._operator_error(
                500, "storage_error", "The operator request could not be persisted."
            )

    def _operator_credential(self) -> str | None:
        expected: str | None = self.server.operator_token  # type: ignore[attr-defined]
        if expected is None or not self._operator_origin_allowed():
            return None
        credential = self._credential()
        if credential is None or not credential.isascii():
            return None
        return credential if hmac.compare_digest(credential, expected) else None

    def _record_generation(
        self,
        *,
        run_id: str,
        operation: str,
        succeeded: bool,
        duration_ms: int,
        summary: dict[str, Any] | None = None,
        failure_stage: str = "generation",
    ) -> None:
        self.server.service.record_generation_attempt(  # type: ignore[attr-defined]
            self.server.plugin_token,  # type: ignore[attr-defined]
            run_id=run_id,
            operation=operation,
            succeeded=succeeded,
            duration_ms=duration_ms,
            summary=summary,
            failure_stage=failure_stage,
        )

    def _record_failed_generation(
        self,
        run_id: str,
        operation: str,
        started: float,
        *,
        failure_stage: str = "generation",
    ) -> bool:
        try:
            self._record_generation(
                run_id=run_id,
                operation=operation,
                succeeded=False,
                duration_ms=_elapsed_ms(started),
                failure_stage=failure_stage,
            )
        except OSError:
            self._operator_error(
                500,
                "audit_storage_error",
                "Generation failed, and its audit record could not be saved.",
            )
            return False
        return True

    def _operator_origin_allowed(self) -> bool:
        host = self.headers.get("Host", "").lower()
        expected_host = f"127.0.0.1:{self.server.server_address[1]}".lower()
        if host != expected_host:
            return False
        origin = self.headers.get("Origin")
        return origin is None or origin.lower() == f"http://{expected_host}"

    def _operator_error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"status": "error", "error": {"code": code, "message": message}})

    def _json(self, status: int, value: dict[str, Any]) -> None:
        self._send_raw(
            status,
            json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _post_world_recipe(self) -> None:
        expected: str | None = self.server.world_token  # type: ignore[attr-defined]
        generator: Callable[[str], str] | None = self.server.world_generator  # type: ignore[attr-defined]
        if expected is None or generator is None:
            self._plain(404, "World generation is not enabled.")
            return
        credential = self._credential()
        if (
            credential is None
            or not credential.isascii()
            or not hmac.compare_digest(credential, expected)
        ):
            self._plain(401, "A Blender service token is required.")
            return
        try:
            length = int(self.headers.get("Content-Length") or "0")
        except ValueError:
            self._plain(400, "Content-Length is invalid.")
            return
        if length < 1 or length > MAX_WORLD_BRIEF_BYTES:
            self.close_connection = True
            self._plain(413 if length > MAX_WORLD_BRIEF_BYTES else 400, "Brief size is invalid.")
            return
        body = self.rfile.read(length)
        try:
            payload = parse_strict(body)
        except ProfileError:
            self._plain(400, "Request must be a strict JSON object.")
            return
        if set(payload) != {"brief"} or not isinstance(payload["brief"], str):
            self._plain(400, "Request must contain one string field named brief.")
            return
        brief = payload["brief"].strip()
        if not brief or len(brief) > 12_000:
            self._plain(400, "Brief must contain between 1 and 12000 characters.")
            return
        run_id = str(uuid.uuid4())
        started = time.monotonic()
        try:
            generated = generator(brief)
        except Exception:
            if self._record_failed_generation(run_id, "blender_scene_recipe", started):
                self._plain(502, "World generation failed.")
            return
        try:
            from core.worldbuilding import SceneRecipe

            scene = SceneRecipe.from_json(generated)
            body = scene.to_json().encode("utf-8")
            if len(body) > MAX_WORLD_RECIPE_BYTES:
                raise ValueError("generated recipe exceeds the response size limit")
        except Exception:
            if self._record_failed_generation(
                run_id, "blender_scene_recipe", started, failure_stage="validation"
            ):
                self._plain(502, "World generation returned an invalid recipe.")
            return
        try:
            self._record_generation(
                run_id=run_id,
                operation="blender_scene_recipe",
                succeeded=True,
                duration_ms=_elapsed_ms(started),
                summary={
                    "object_count": len(scene.objects),
                    "light_count": len(scene.lights),
                    "character_count": len(scene.characters),
                    "output_bytes": len(body),
                },
            )
        except OSError:
            self._plain(500, "World generation completed, but the audit record could not be saved.")
            return
        self._send_raw(
            200,
            body,
            "application/json; charset=utf-8",
            extra_headers={"X-RGA-Run-ID": run_id},
        )

    def _wait(
        self,
        service: Service,
        credential: str,
        body: bytes,
        waiting: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        """Hold the poll open until there is work or the timeout elapses (ADR-0007)."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(_WAKE_S)
            if service.has_deliverable(credential):
                answered, _ = handle_message(service, credential, body)
                return answered
        return waiting

    def _credential(self) -> str | None:
        header = self.headers.get("Authorization") or ""
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        return token.strip()

    def _send(self, status: int, message: dict[str, Any]) -> None:
        body = serialise(message)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _plain(self, status: int, text: str) -> None:
        body = text.encode("utf-8")
        self._send_raw(status, body, "text/plain; charset=utf-8")

    def _send_raw(
        self,
        status: int,
        body: bytes,
        content_type: str,
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        if content_type.startswith("text/html"):
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                "img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        """Quiet by default: a request line can carry a token in a header, never logged."""


class ApiServer(ThreadingHTTPServer):
    """A local HTTP server bound to the loopback interface and nothing else."""

    daemon_threads = True

    def __init__(
        self,
        service: Service,
        *,
        host: str = "127.0.0.1",
        port: int = 8787,
        poll_timeout_s: float = DEFAULT_POLL_TIMEOUT_S,
        plugin_token: str,
        operator_token: str | None = None,
        world_token: str | None = None,
        world_generator: Callable[[str], str] | None = None,
        world_quoter: Callable[[str], dict[str, str]] | None = None,
        game_plan_generator: Callable[[str], object] | None = None,
        game_plan_quoter: Callable[[str], dict[str, str]] | None = None,
        studio_action_generator: Callable[[str], dict[str, Any]] | None = None,
        studio_action_quoter: Callable[[str], dict[str, str]] | None = None,
        code_preview_generator: Callable[[str, tuple[str, ...]], object] | None = None,
        code_preview_quoter: Callable[[str, tuple[str, ...]], dict[str, str]] | None = None,
        spend_status_provider: Callable[[], dict[str, str]] | None = None,
        blender_mcp: BlenderMCPGateway | None = None,
        roblox_mcp: RobloxMCPGateway | None = None,
        roblox_asset_approval_secret: str = "",
        roblox_publish_approval_secret: str = "",
        roblox_publish_universe_id: str = "",
        roblox_publish_place_id: str = "",
    ) -> None:
        if host != "127.0.0.1":
            raise ValueError("API server must bind to IPv4 loopback 127.0.0.1")
        normalized_plugin_token = plugin_token.strip()
        if not 32 <= len(normalized_plugin_token) <= 512 or any(
            ord(char) < 33 or ord(char) > 126 for char in normalized_plugin_token
        ):
            raise ValueError("PLUGIN_AUTH_TOKEN must be 32-512 printable ASCII characters")
        normalized_token = world_token.strip() if world_token and world_token.strip() else None
        if normalized_token is not None and world_generator is None:
            raise ValueError("world_token requires a configured world_generator")
        if normalized_token is not None and (
            not 32 <= len(normalized_token) <= 512
            or any(ord(char) < 33 or ord(char) > 126 for char in normalized_token)
        ):
            raise ValueError("BLENDER_AUTH_TOKEN must be 32-512 printable ASCII characters")
        normalized_operator = (
            operator_token.strip() if operator_token and operator_token.strip() else None
        )
        if normalized_operator is not None and (
            not 32 <= len(normalized_operator) <= 512
            or any(ord(char) < 33 or ord(char) > 126 for char in normalized_operator)
        ):
            raise ValueError("OPERATOR_AUTH_TOKEN must be 32-512 printable ASCII characters")
        if world_generator is not None and normalized_token is None and normalized_operator is None:
            raise ValueError("world generation requires a Blender or operator token")
        if world_quoter is not None and normalized_operator is None:
            raise ValueError("world cost quotes require an operator token")
        if world_quoter is not None and world_generator is None:
            raise ValueError("world cost quotes require a configured world generator")
        if game_plan_generator is not None and normalized_operator is None:
            raise ValueError("game planning requires an operator token")
        if game_plan_quoter is not None and normalized_operator is None:
            raise ValueError("game plan cost quotes require an operator token")
        if game_plan_quoter is not None and game_plan_generator is None:
            raise ValueError("game plan cost quotes require a configured planner")
        if studio_action_generator is not None and normalized_operator is None:
            raise ValueError("Studio action generation requires an operator token")
        if studio_action_quoter is not None and normalized_operator is None:
            raise ValueError("Studio action cost quotes require an operator token")
        if studio_action_quoter is not None and studio_action_generator is None:
            raise ValueError("Studio action cost quotes require a configured action generator")
        if code_preview_generator is not None and normalized_operator is None:
            raise ValueError("Luau source preview requires an operator token")
        if code_preview_quoter is not None and normalized_operator is None:
            raise ValueError("Luau source preview quotes require an operator token")
        if code_preview_quoter is not None and code_preview_generator is None:
            raise ValueError("Luau source preview quotes require a configured preview generator")
        if blender_mcp is not None and normalized_operator is None:
            raise ValueError("remote Blender MCP requires an operator token")
        if roblox_mcp is not None and normalized_operator is None:
            raise ValueError("remote Roblox MCP requires an operator token")
        if roblox_asset_approval_secret and (
            not 32 <= len(roblox_asset_approval_secret) <= 512
            or not roblox_asset_approval_secret.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in roblox_asset_approval_secret)
        ):
            raise ValueError(
                "Roblox asset approval secret must be 32-512 printable ASCII characters"
            )
        if roblox_asset_approval_secret and (blender_mcp is None or roblox_mcp is None):
            raise ValueError("Roblox asset uploads require both remote Blender and Roblox MCP")
        if roblox_publish_approval_secret:
            if (
                not 32 <= len(roblox_publish_approval_secret) <= 512
                or not roblox_publish_approval_secret.isascii()
                or any(ord(char) < 33 or ord(char) > 126 for char in roblox_publish_approval_secret)
            ):
                raise ValueError(
                    "Roblox place publish secret must be 32-512 printable ASCII characters"
                )
            if roblox_mcp is None:
                raise ValueError("Roblox place publishing requires remote Roblox MCP")
            numeric_id = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
            if not numeric_id.fullmatch(roblox_publish_universe_id) or not numeric_id.fullmatch(
                roblox_publish_place_id
            ):
                raise ValueError(
                    "Roblox place publishing requires pinned test universe and place IDs"
                )
        super().__init__((host, port), _Handler)
        self.service = service
        self.poll_timeout_s = poll_timeout_s
        self.plugin_token = normalized_plugin_token
        self.operator_token = normalized_operator
        self.world_token = normalized_token
        self.world_generator = world_generator
        self.world_quoter = world_quoter
        self.game_plan_generator = game_plan_generator
        self.game_plan_quoter = game_plan_quoter
        self.studio_action_generator = studio_action_generator
        self.studio_action_quoter = studio_action_quoter
        self.code_preview_generator = code_preview_generator
        self.code_preview_quoter = code_preview_quoter
        self._code_preview_quotes: dict[str, tuple[BuildTask, float]] = {}
        self._code_preview_quotes_lock = threading.Lock()
        self.spend_status_provider = spend_status_provider
        self.blender_mcp = blender_mcp
        self.roblox_mcp = roblox_mcp
        self.roblox_asset_approval_secret = roblox_asset_approval_secret
        self.roblox_asset_upload_enabled = bool(
            roblox_asset_approval_secret and blender_mcp is not None and roblox_mcp is not None
        )
        self.roblox_publish_approval_secret = roblox_publish_approval_secret
        self.roblox_publish_universe_id = roblox_publish_universe_id
        self.roblox_publish_place_id = roblox_publish_place_id
        self.roblox_place_publish_enabled = bool(roblox_publish_approval_secret and roblox_mcp)
        self._place_artifacts: dict[str, tuple[str, bytes, float]] = {}
        self._place_artifacts_lock = threading.Lock()
        self._blender_artifacts: dict[str, tuple[str, float]] = {}
        self._blender_artifacts_lock = threading.Lock()

    def remember_blender_artifact(self, artifact_id: str, digest: str) -> None:
        """Bind a verified Blender receipt digest to a short-lived operator download."""
        now = time.monotonic()
        with self._blender_artifacts_lock:
            self._blender_artifacts = {
                key: value for key, value in self._blender_artifacts.items() if value[1] > now
            }
            while len(self._blender_artifacts) >= 64:
                del self._blender_artifacts[next(iter(self._blender_artifacts))]
            self._blender_artifacts[artifact_id] = (digest, now + 900)

    def get_blender_artifact_sha256(self, artifact_id: str) -> str | None:
        with self._blender_artifacts_lock:
            item = self._blender_artifacts.get(artifact_id)
            if item is None or item[1] <= time.monotonic():
                self._blender_artifacts.pop(artifact_id, None)
                return None
            return item[0]

    def remember_place_artifact(self, artifact: RobloxPlaceArtifact) -> None:
        now = time.monotonic()
        with self._place_artifacts_lock:
            self._place_artifacts = {
                key: value for key, value in self._place_artifacts.items() if value[2] > now
            }
            while len(self._place_artifacts) >= 8:
                del self._place_artifacts[next(iter(self._place_artifacts))]
            self._place_artifacts[artifact.request_id] = (
                artifact.sha256,
                artifact.place_file,
                now + 900,
            )

    def get_place_artifact(self, request_id: str, digest: str) -> bytes | None:
        with self._place_artifacts_lock:
            item = self._place_artifacts.get(request_id)
            if item is None or item[2] <= time.monotonic() or item[0] != digest:
                return None
            return item[1]

    def issue_code_preview_quote(self, task: BuildTask) -> str:
        """Issue a bounded, single-use quote handle for one exact Luau task."""
        now = time.monotonic()
        with self._code_preview_quotes_lock:
            expired = [
                quote_id
                for quote_id, (_, expires_at) in self._code_preview_quotes.items()
                if expires_at <= now
            ]
            for quote_id in expired:
                del self._code_preview_quotes[quote_id]
            while len(self._code_preview_quotes) >= 128:
                del self._code_preview_quotes[next(iter(self._code_preview_quotes))]
            quote_id = str(uuid.uuid4())
            self._code_preview_quotes[quote_id] = (task, now + 900)
            return quote_id

    def consume_code_preview_quote(self, quote_id: str, task: BuildTask) -> bool:
        """Consume a matching code-preview quote once, with a 15-minute lifetime."""
        try:
            if str(uuid.UUID(quote_id)) != quote_id:
                return False
        except (AttributeError, TypeError, ValueError):
            return False
        now = time.monotonic()
        with self._code_preview_quotes_lock:
            saved = self._code_preview_quotes.pop(quote_id, None)
        return saved is not None and saved[1] > now and saved[0] == task

    @property
    def endpoint(self) -> str:
        """The URL a plugin posts to."""
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}{ENDPOINT}"

    @property
    def world_recipe_endpoint(self) -> str:
        """Loopback endpoint consumed by the Blender extension."""
        host, port = self.server_address[0], self.server_address[1]
        return f"http://{host}:{port}{WORLD_RECIPE_ENDPOINT}"
