"""Fixed-harness client for a separately provisioned Roblox test place."""

from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import re
import ssl
import struct
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from core.navigation import navigation_status, validate_failed_leg
from core.roblox_place import scene_recipe_collision_payload
from core.worldbuilding import SceneRecipe

API_HOST = "apis.roblox.com"
MAX_RECIPE_BYTES = 1_200_000
MAX_RESPONSE_BYTES = 1_200_000
MAX_IMPORTED_MODEL_BYTES = 512_000
_ID = re.compile(r"[1-9][0-9]{0,19}\Z", re.ASCII)
_TASK_PATH = re.compile(
    r"universes/(\d+)/places/(\d+)/versions/(\d+)/"
    r"luau-execution-sessions/([0-9a-f-]{36})/tasks/([0-9a-f-]{36})\Z",
    re.ASCII,
)


class RobloxCloudError(RuntimeError):
    """A bounded Open Cloud map-validation request failed or became uncertain."""


@dataclass(frozen=True, slots=True)
class RobloxTarget:
    """The only Roblox target a service process may execute against."""

    universe_id: str
    place_id: str
    place_version: str
    api_key: str
    task_timeout_seconds: int = 60
    poll_timeout_seconds: int = 150

    def __post_init__(self) -> None:
        for name in ("universe_id", "place_id", "place_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not _ID.fullmatch(value):
                raise ValueError(f"{name} must be a positive decimal ID")
        if (
            not 1 <= len(self.api_key) <= 512
            or not self.api_key.isascii()
            or any(ord(char) < 33 or ord(char) > 126 for char in self.api_key)
        ):
            raise ValueError("a Roblox Open Cloud API key is required")
        if not 1 <= self.task_timeout_seconds <= 300:
            raise ValueError("Open Cloud task timeout must be between 1 and 300 seconds")
        if not self.task_timeout_seconds + 10 <= self.poll_timeout_seconds <= 240:
            raise ValueError("poll timeout must safely exceed the task timeout and be at most 240")

    @classmethod
    def from_env(cls) -> RobloxTarget:
        required = {
            "RGA_ROBLOX_TEST_UNIVERSE_ID": os.environ.get("RGA_ROBLOX_TEST_UNIVERSE_ID", ""),
            "RGA_ROBLOX_TEST_PLACE_ID": os.environ.get("RGA_ROBLOX_TEST_PLACE_ID", ""),
            "RGA_ROBLOX_TEST_PLACE_VERSION": os.environ.get("RGA_ROBLOX_TEST_PLACE_VERSION", ""),
            "ROBLOX_OPEN_CLOUD_API_KEY": os.environ.get("ROBLOX_OPEN_CLOUD_API_KEY", ""),
        }
        missing = [key for key, value in required.items() if not value]
        if missing:
            raise ValueError(
                "missing required Roblox validation configuration: " + ", ".join(missing)
            )
        if os.environ.get("RGA_ROBLOX_DISPOSABLE_CONFIRMED") != "I_ACCEPT_DISPOSABLE_TEST_ONLY":
            raise ValueError("explicit disposable Roblox test-place confirmation is required")
        if (
            os.environ.get("RGA_ROBLOX_PERSISTENCE_VERIFIED")
            != "I_VERIFIED_PINNED_PLACE_NONPERSISTENCE"
        ):
            raise ValueError(
                "runtime persistence verification is required before enabling Roblox validation"
            )
        if not os.environ.get("RGA_ROBLOX_PERSISTENCE_EVIDENCE", "").strip():
            raise ValueError("record the disposable-place persistence evidence reference")
        production_universes = _id_set("RGA_ROBLOX_PRODUCTION_UNIVERSE_IDS")
        production_places = _id_set("RGA_ROBLOX_PRODUCTION_PLACE_IDS")
        target_universe = required["RGA_ROBLOX_TEST_UNIVERSE_ID"]
        target_place = required["RGA_ROBLOX_TEST_PLACE_ID"]
        if target_universe in production_universes or target_place in production_places:
            raise ValueError("Roblox validation target matches a configured production ID")
        try:
            task_timeout = int(os.environ.get("RGA_ROBLOX_TASK_TIMEOUT_SECONDS", "60"))
            poll_timeout = int(os.environ.get("RGA_ROBLOX_POLL_TIMEOUT_SECONDS", "150"))
        except ValueError as exc:
            raise ValueError("Roblox validation timeouts must be decimal integers") from exc
        return cls(
            universe_id=target_universe,
            place_id=target_place,
            place_version=required["RGA_ROBLOX_TEST_PLACE_VERSION"],
            api_key=required["ROBLOX_OPEN_CLOUD_API_KEY"],
            task_timeout_seconds=task_timeout,
            poll_timeout_seconds=poll_timeout,
        )


def _id_set(name: str) -> frozenset[str]:
    raw = os.environ.get(name, "")
    values = [item.strip() for item in raw.split(",") if item.strip()]
    if not values or any(not _ID.fullmatch(item) for item in values):
        raise ValueError(f"{name} must list one or more positive decimal IDs")
    return frozenset(values)


class OpenCloudMapValidator:
    """Submit only the repository-owned Luau harness and recipe binary input."""

    def __init__(
        self,
        target: RobloxTarget,
        *,
        harness_path: Path | None = None,
        poll_interval_seconds: float = 2.0,
    ) -> None:
        self.target = target
        self.harness_path = harness_path or Path(__file__).with_name("harness.luau")
        self.poll_interval_seconds = max(0.2, min(float(poll_interval_seconds), 10.0))

    def validate_recipe(self, recipe_payload: object) -> dict[str, Any]:
        """Validate a recipe in the pinned test place and return bounded evidence."""
        recipe = SceneRecipe.from_mapping(recipe_payload)
        recipe_bytes = json.dumps(
            scene_recipe_collision_payload(recipe), ensure_ascii=True, separators=(",", ":")
        ).encode("utf-8")
        if len(recipe_bytes) > MAX_RECIPE_BYTES:
            raise ValueError("recipe exceeds Open Cloud binary-input size limit")
        try:
            harness = self.harness_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RobloxCloudError("fixed Roblox validation harness is unavailable") from exc
        if not harness or len(harness.encode("utf-8")) > 32_000:
            raise RobloxCloudError("fixed Roblox validation harness is invalid")

        # The task ledger is written by the caller before this method. This code never
        # retries POST after an ambiguous connection error: Roblox may have accepted it.
        binary_input = self._create_binary_input(len(recipe_bytes))
        self._upload_binary_input(binary_input, recipe_bytes)
        version_prefix = (
            f"universes/{self.target.universe_id}/places/{self.target.place_id}/"
            f"versions/{self.target.place_version}/"
        )
        create_path = f"/cloud/v2/{version_prefix}luau-execution-session-tasks"
        body = json.dumps(
            {
                "script": harness,
                "binaryInput": binary_input["path"],
                "timeout": f"{self.target.task_timeout_seconds}s",
            },
            separators=(",", ":"),
        ).encode("utf-8")
        task = self._request("POST", create_path, body=body)
        task_path = task.get("path") if isinstance(task, dict) else None
        if not isinstance(task_path, str) or not self._valid_task_path(task_path):
            raise RobloxCloudError("Open Cloud returned an invalid pinned task path")
        final = self._poll_task(task_path)
        if final.get("state") != "COMPLETE":
            error = final.get("error")
            message = error.get("message") if isinstance(error, dict) else "task did not complete"
            raise RobloxCloudError(f"Open Cloud fixed-harness validation failed: {message[:240]}")
        output = final.get("output")
        results = output.get("results") if isinstance(output, dict) else None
        result = results[0] if isinstance(results, list) and results else None
        validated = self._check_result(result, recipe)
        validated["task_id"] = task_path.rsplit("/", 1)[-1]
        return validated

    def serialize_approved_model(self, asset_id: str) -> tuple[bytes, dict[str, int]]:
        """Load a creator-owned Model in Roblox Cloud, filter its tree, and serialize it."""
        if not isinstance(asset_id, str) or not _ID.fullmatch(asset_id):
            raise ValueError("model asset ID must be a positive decimal ID")
        harness_path = self.harness_path.with_name("model_import_harness.luau")
        try:
            harness = harness_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RobloxCloudError("fixed model import harness is unavailable") from exc
        if not harness or len(harness.encode("utf-8")) > 16_000:
            raise RobloxCloudError("fixed model import harness is invalid")
        payload = json.dumps({"asset_id": asset_id}, separators=(",", ":")).encode()
        binary_input = self._create_binary_input(len(payload))
        self._upload_binary_input(binary_input, payload)
        prefix = (
            f"universes/{self.target.universe_id}/places/{self.target.place_id}/"
            f"versions/{self.target.place_version}/luau-execution-session-tasks"
        )
        task = self._request(
            "POST",
            "/cloud/v2/" + prefix,
            body=json.dumps(
                {
                    "script": harness,
                    "binaryInput": binary_input["path"],
                    "timeout": f"{self.target.task_timeout_seconds}s",
                },
                separators=(",", ":"),
            ).encode(),
        )
        task_path = task.get("path") if isinstance(task, dict) else None
        if not isinstance(task_path, str) or not self._valid_task_path(task_path):
            raise RobloxCloudError("Open Cloud returned an invalid pinned model task path")
        final = self._poll_task(task_path)
        if final.get("state") != "COMPLETE":
            raise RobloxCloudError("fixed Roblox model inspection failed or is uncertain")
        output = final.get("output")
        results = output.get("results") if isinstance(output, dict) else None
        result = results[0] if isinstance(results, list) and results else None
        if not isinstance(result, dict) or set(result) != {
            "schema_version",
            "asset_id",
            "instance_count",
            "meshpart_count",
            "model_base64",
        }:
            raise RobloxCloudError("fixed model harness returned a malformed result")
        if (
            result.get("schema_version") != 1
            or result.get("asset_id") != asset_id
            or type(result.get("instance_count")) is not int
            or not 1 <= result["instance_count"] <= 512
            or type(result.get("meshpart_count")) is not int
            or not 1 <= result["meshpart_count"] <= 128
            or not isinstance(result.get("model_base64"), str)
            or len(result["model_base64"]) > ((MAX_IMPORTED_MODEL_BYTES + 2) // 3) * 4
        ):
            raise RobloxCloudError("fixed model harness returned invalid model limits")
        try:
            serialized = base64.b64decode(result["model_base64"], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise RobloxCloudError("fixed model harness returned invalid model encoding") from exc
        if not 32 <= len(serialized) <= MAX_IMPORTED_MODEL_BYTES:
            raise RobloxCloudError("serialized Roblox model is empty or oversized")
        if serialized[:14] != b"<roblox!\x89\xff\r\n\x1a\n" or serialized[14:16] != b"\x00\x00":
            raise RobloxCloudError("serialized model is not a Roblox binary model")
        class_count, instance_count = struct.unpack_from("<ii", serialized, 16)
        if not 1 <= class_count <= 16 or instance_count != result["instance_count"]:
            raise RobloxCloudError("serialized model header disagrees with inspected content")
        return serialized, {
            "instance_count": instance_count,
            "meshpart_count": result["meshpart_count"],
        }

    def _valid_task_path(self, path: str) -> bool:
        match = _TASK_PATH.fullmatch(path)
        if match is None:
            return False
        try:
            canonical_ids = all(
                str(uuid.UUID(match.group(index))) == match.group(index) for index in (4, 5)
            )
        except ValueError:
            return False
        return bool(
            canonical_ids
            and match.group(1) == self.target.universe_id
            and match.group(2) == self.target.place_id
            and match.group(3) == self.target.place_version
        )

    def _create_binary_input(self, size: int) -> dict[str, str]:
        path = (
            f"/cloud/v2/universes/{self.target.universe_id}/"
            "luau-execution-session-task-binary-inputs"
        )
        result = self._request("POST", path, body=json.dumps({"size": size}).encode())
        if not isinstance(result, dict):
            raise RobloxCloudError("Open Cloud returned an invalid binary-input receipt")
        upload_uri, input_path = result.get("uploadUri"), result.get("path")
        parsed = urlsplit(upload_uri) if isinstance(upload_uri, str) else None
        expected_prefix = (
            f"universes/{self.target.universe_id}/luau-execution-session-task-binary-inputs/"
        )
        if (
            not parsed
            or parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname.lower() != API_HOST
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
            or not isinstance(input_path, str)
            or not input_path.startswith(expected_prefix)
            or ".." in input_path
        ):
            raise RobloxCloudError("Open Cloud returned an invalid binary-input upload target")
        input_id = input_path.removeprefix(expected_prefix)
        try:
            if str(uuid.UUID(input_id)) != input_id:
                raise ValueError("binary input ID is not canonical")
        except ValueError as exc:
            raise RobloxCloudError("Open Cloud returned an invalid binary-input path") from exc
        return {"upload_uri": upload_uri, "path": input_path}

    def _upload_binary_input(self, receipt: dict[str, str], payload: bytes) -> None:
        parsed = urlsplit(receipt["upload_uri"])
        connection = http.client.HTTPSConnection(
            parsed.hostname, port=parsed.port, timeout=20, context=ssl.create_default_context()
        )
        try:
            path = parsed.path + ("?" + parsed.query if parsed.query else "")
            connection.request(
                "PUT", path, body=payload, headers={"Content-Type": "application/octet-stream"}
            )
            response = connection.getresponse()
            body = response.read(1024)
            if response.status not in {200, 201, 204}:
                raise RobloxCloudError("Open Cloud binary-input upload failed")
            del body
        except (OSError, http.client.HTTPException) as exc:
            raise RobloxCloudError("Open Cloud binary-input upload failed") from exc
        finally:
            connection.close()

    def _poll_task(self, path: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.target.poll_timeout_seconds
        while time.monotonic() < deadline:
            task = self._request("GET", "/cloud/v2/" + path)
            if not isinstance(task, dict):
                raise RobloxCloudError("Open Cloud returned an invalid task status")
            state = task.get("state")
            if state in {"COMPLETE", "FAILED"}:
                return task
            if state not in {"QUEUED", "PROCESSING"}:
                raise RobloxCloudError("Open Cloud returned an unknown task state")
            time.sleep(self.poll_interval_seconds)
        raise RobloxCloudError("Open Cloud task outcome is still unknown; do not resubmit")

    def _request(self, method: str, path: str, *, body: bytes | None = None) -> object:
        if not path.startswith("/cloud/v2/") or ".." in path:
            raise RobloxCloudError("Open Cloud request path is invalid")
        connection = http.client.HTTPSConnection(
            API_HOST,
            timeout=min(20.0, float(self.target.poll_timeout_seconds)),
            context=ssl.create_default_context(),
        )
        try:
            headers = {"x-api-key": self.target.api_key, "Accept": "application/json"}
            if body is not None:
                headers["Content-Type"] = "application/json"
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(MAX_RESPONSE_BYTES + 1)
            if response.status not in {200, 201} or len(raw) > MAX_RESPONSE_BYTES:
                raise RobloxCloudError("Roblox Open Cloud request failed")
            try:
                return json.loads(raw, object_pairs_hook=_unique_pairs)
            except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
                raise RobloxCloudError("Roblox Open Cloud returned invalid JSON") from exc
        except RobloxCloudError:
            raise
        except (OSError, http.client.HTTPException) as exc:
            raise RobloxCloudError("Roblox Open Cloud request failed") from exc
        finally:
            connection.close()

    @staticmethod
    def _check_result(result: object, recipe: SceneRecipe) -> dict[str, Any]:
        if not isinstance(result, dict):
            raise RobloxCloudError("fixed harness returned no structured result")
        required = {
            "schema_version",
            "name",
            "object_count",
            "path_feature_count",
            "navigation_waypoint_count",
            "navigation_connected",
            "navigation_failed_leg",
        }
        if (
            set(result) != required
            or result.get("schema_version") != recipe.schema_version
            or result.get("name") != recipe.name
            or type(result.get("object_count")) is not int
            or result["object_count"] != len(recipe.objects)
            or type(result.get("path_feature_count")) is not int
            or result["path_feature_count"] != sum(item.role == "path" for item in recipe.objects)
            or type(result.get("navigation_waypoint_count")) is not int
            or not 0 <= result["navigation_waypoint_count"] <= 512
            or type(result.get("navigation_connected")) is not bool
        ):
            raise RobloxCloudError("fixed harness returned a malformed validation result")
        try:
            result["validation_status"] = navigation_status(
                recipe,
                result["path_feature_count"],
                result["navigation_waypoint_count"],
                result["navigation_connected"],
            )
            validate_failed_leg(
                recipe,
                result["validation_status"],
                result["navigation_failed_leg"],
                result["navigation_waypoint_count"],
            )
        except ValueError as exc:
            raise RobloxCloudError(
                "fixed harness returned contradictory navigation evidence"
            ) from exc
        return {
            key: result[key]
            for key in (
                "object_count",
                "path_feature_count",
                "navigation_waypoint_count",
                "navigation_connected",
                "validation_status",
                "navigation_failed_leg",
            )
        }


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def recipe_digest(recipe_payload: object, target: RobloxTarget) -> str:
    """Bind idempotency to recipe, contract and non-secret pinned execution target."""
    recipe = SceneRecipe.from_mapping(recipe_payload)
    # Older endpoint-only checks must never be replayed as full route checks.
    context = json.dumps(
        ["rga-navigation-v2", target.universe_id, target.place_id, target.place_version],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(context + b"\0" + recipe.to_json().encode("utf-8")).hexdigest()
