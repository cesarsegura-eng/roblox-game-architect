from __future__ import annotations

import base64
import hashlib
import http.client
import json
import struct
import sys
import threading
import time
import uuid
import zlib
from typing import Any

import pytest

from api.roblox_mcp import RobloxMCPClient
from apps.roblox_mcp_server.assets import (
    AssetUploadLedger,
    OpenCloudModelAssetUploader,
    RobloxAssetError,
    RobloxAssetTarget,
    _image_dimensions,
)
from apps.roblox_mcp_server.server import RobloxMCPServer
from core.asset_approval import sign_asset_approval, verify_asset_approval


def _glb(
    document: dict[str, Any] | None = None,
    *,
    vertex_count: int = 3,
    index_count: int | None = None,
    first_index: int = 0,
    position_view_length: int | None = None,
    position_byte_offset: int = 0,
    position_stride: int = 12,
    primitive_count: int = 1,
    skin_influences: int = 0,
    first_skin_joint: int = 0,
    inverse_bind_matrices: list[tuple[float, ...]] | None = None,
    animation: bool = False,
    animation_input_count: int = 2,
    animation_output_count: int = 2,
    texture_dimensions: tuple[int, int] | None = None,
    corrupt_texture_crc: bool = False,
    texture_mime: str = "image/png",
    malformed_jpeg: bool = False,
    texture_source_index: int = 0,
    material_texture_index: int = 0,
    sparse_position: tuple[float, float, float] | None = None,
    sparse_position_without_base: bool = False,
    sparse_position_index: int = 0,
    sparse_index_value: int | None = None,
    sparse_joint_value: int | None = None,
    sparse_weight_value: float | None = None,
    sparse_animation_value: tuple[float, float, float] | None = None,
    node_fields: dict[str, Any] | None = None,
) -> bytes:
    position_bytes = position_byte_offset + (vertex_count - 1) * position_stride + 12
    position_bytes = (position_bytes + 3) // 4 * 4
    binary = b"\0" * position_bytes
    position_accessor: dict[str, Any] = {
        "bufferView": 0,
        "componentType": 5126,
        "count": vertex_count,
        "type": "VEC3",
    }
    if position_byte_offset:
        position_accessor["byteOffset"] = position_byte_offset
    accessors = [position_accessor]
    position_view: dict[str, Any] = {
        "buffer": 0,
        "byteLength": position_bytes if position_view_length is None else position_view_length,
    }
    if position_stride != 12:
        position_view["byteStride"] = position_stride
    buffer_views = [position_view]
    primitive: dict[str, Any] = {"attributes": {"POSITION": 0}}
    if index_count is not None:
        primitive["indices"] = 1
        accessors.append(
            {"bufferView": 1, "componentType": 5123, "count": index_count, "type": "SCALAR"}
        )
        buffer_views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": index_count * 2})
        index_data = bytearray(index_count * 2)
        index_data[:2] = first_index.to_bytes(2, "little")
        binary += index_data
    binary += b"\0" * ((-len(binary)) % 4)
    nodes: list[dict[str, Any]] = []
    skins: list[dict[str, Any]] = []
    animations: list[dict[str, Any]] = []
    first_joint_accessor: int | None = None
    first_weight_accessor: int | None = None
    animation_output_accessor: int | None = None
    if skin_influences:
        joint_count = max(4, skin_influences)
        nodes = [
            {"mesh": 0, "skin": 0},
            *({"name": f"Joint {index}"} for index in range(joint_count)),
        ]
        skins = [{"joints": list(range(1, joint_count + 1))}]
        for set_index in range((skin_influences + 3) // 4):
            joint_values: list[int] = []
            weight_values: list[float] = []
            for _ in range(vertex_count):
                for slot in range(4):
                    influence = set_index * 4 + slot
                    active = influence < skin_influences
                    joint = influence if active else 0
                    if set_index == 0 and slot == 0 and first_skin_joint:
                        joint = first_skin_joint
                    joint_values.append(joint)
                    weight_values.append(1 / skin_influences if active else 0.0)
            joint_accessor = len(accessors)
            if first_joint_accessor is None:
                first_joint_accessor = joint_accessor
            joint_view = len(buffer_views)
            joint_bytes = bytes(joint_values)
            buffer_views.append(
                {"buffer": 0, "byteOffset": len(binary), "byteLength": len(joint_bytes)}
            )
            accessors.append(
                {
                    "bufferView": joint_view,
                    "componentType": 5121,
                    "count": vertex_count,
                    "type": "VEC4",
                }
            )
            binary += joint_bytes
            binary += b"\0" * ((-len(binary)) % 4)
            weight_accessor = len(accessors)
            if first_weight_accessor is None:
                first_weight_accessor = weight_accessor
            weight_view = len(buffer_views)
            weight_bytes = struct.pack("<" + "f" * len(weight_values), *weight_values)
            buffer_views.append(
                {"buffer": 0, "byteOffset": len(binary), "byteLength": len(weight_bytes)}
            )
            accessors.append(
                {
                    "bufferView": weight_view,
                    "componentType": 5126,
                    "count": vertex_count,
                    "type": "VEC4",
                }
            )
            binary += weight_bytes
            binary += b"\0" * ((-len(binary)) % 4)
            primitive["attributes"][f"JOINTS_{set_index}"] = joint_accessor
            primitive["attributes"][f"WEIGHTS_{set_index}"] = weight_accessor
    if inverse_bind_matrices is not None:
        if not skins:
            raise ValueError("inverse bind matrix fixture requires a skinned mesh")
        matrix_data = b"".join(struct.pack("<16f", *matrix) for matrix in inverse_bind_matrices)
        matrix_view = len(buffer_views)
        buffer_views.append(
            {"buffer": 0, "byteOffset": len(binary), "byteLength": len(matrix_data)}
        )
        binary += matrix_data
        binary += b"\0" * ((-len(binary)) % 4)
        accessors.append(
            {
                "bufferView": matrix_view,
                "componentType": 5126,
                "count": len(inverse_bind_matrices),
                "type": "MAT4",
            }
        )
        skins[0]["inverseBindMatrices"] = len(accessors) - 1
    if animation:
        input_index = len(accessors)
        input_view = len(buffer_views)
        input_data = struct.pack("<2f", 0.0, 1.0)
        buffer_views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(input_data)})
        accessors.append(
            {
                "bufferView": input_view,
                "componentType": 5126,
                "count": animation_input_count,
                "type": "SCALAR",
            }
        )
        binary += input_data
        output_index = len(accessors)
        animation_output_accessor = output_index
        output_view = len(buffer_views)
        output_data = struct.pack(
            "<" + "f" * (animation_output_count * 3), *([0.0] * (animation_output_count * 3))
        )
        buffer_views.append(
            {"buffer": 0, "byteOffset": len(binary), "byteLength": len(output_data)}
        )
        accessors.append(
            {
                "bufferView": output_view,
                "componentType": 5126,
                "count": animation_output_count,
                "type": "VEC3",
            }
        )
        binary += output_data
        animated_node = len(nodes)
        nodes.append({"name": "Animated Node"})
        animations.append(
            {
                "channels": [
                    {"sampler": 0, "target": {"node": animated_node, "path": "translation"}}
                ],
                "samplers": [{"input": input_index, "output": output_index}],
            }
        )
    images: list[dict[str, Any]] = []
    textures: list[dict[str, Any]] = []
    materials: list[dict[str, Any]] = []
    if texture_dimensions is not None:
        width, height = texture_dimensions

        def png_chunk(kind: bytes, payload: bytes) -> bytes:
            return (
                len(payload).to_bytes(4, "big")
                + kind
                + payload
                + (zlib.crc32(kind + payload) & 0xFFFFFFFF).to_bytes(4, "big")
            )

        if texture_mime == "image/png":
            scanline = b"\0" + b"\0" * (width * 4)
            image_data = (
                b"\x89PNG\r\n\x1a\n"
                + png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
                + png_chunk(b"IDAT", zlib.compress(scanline * height))
                + png_chunk(b"IEND", b"")
            )
        else:
            if malformed_jpeg:
                quantization_table = b"\x00" + b"\x01" * 64
                huffman_code_counts = b"\x01" + b"\x00" * 15
                dc_huffman_table = b"\x00" + huffman_code_counts + b"\x00"
                ac_huffman_table = b"\x10" + huffman_code_counts + b"\x00"
                image_data = (
                    b"\xff\xd8"
                    + b"\xff\xdb\x00\x43"
                    + quantization_table
                    + b"\xff\xc0\x00\x0b\x08"
                    + height.to_bytes(2, "big")
                    + width.to_bytes(2, "big")
                    + b"\x01\x01\x11\x00"
                    + b"\xff\xc4\x00\x14"
                    + dc_huffman_table
                    + b"\xff\xc4\x00\x14"
                    + ac_huffman_table
                    + b"\xff\xda\x00\x08\x01\x31\x00\x00\x3f\x00"
                    + b"\x3f\xff\xd9"
                )
            else:
                import io

                from PIL import Image

                image_buffer = io.BytesIO()
                with Image.new("RGB", (width, height), (65, 105, 145)) as jpeg_image:
                    jpeg_image.save(image_buffer, format="JPEG", quality=75)
                image_data = image_buffer.getvalue()
        if corrupt_texture_crc and texture_mime == "image/png":
            image_data = image_data[:-1] + bytes([image_data[-1] ^ 1])
        image_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(image_data)})
        binary += image_data
        binary += b"\0" * ((-len(binary)) % 4)
        images.append({"bufferView": image_view, "mimeType": texture_mime})
        textures.append({"source": texture_source_index})
        materials.append(
            {"pbrMetallicRoughness": {"baseColorTexture": {"index": material_texture_index}}}
        )
        primitive["material"] = 0

    def add_sparse(accessor: dict[str, Any], index: int, value: bytes) -> None:
        nonlocal binary
        sparse_index_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": 1})
        binary += bytes([index])
        binary += b"\0" * ((-len(binary)) % 4)
        sparse_value_view = len(buffer_views)
        buffer_views.append({"buffer": 0, "byteOffset": len(binary), "byteLength": len(value)})
        binary += value
        binary += b"\0" * ((-len(binary)) % 4)
        accessor["sparse"] = {
            "count": 1,
            "indices": {"bufferView": sparse_index_view, "componentType": 5121},
            "values": {"bufferView": sparse_value_view},
        }

    if sparse_position is not None:
        if sparse_position_without_base:
            position_accessor.pop("bufferView", None)
        add_sparse(position_accessor, sparse_position_index, struct.pack("<3f", *sparse_position))
    if sparse_index_value is not None:
        if index_count is None:
            raise ValueError("sparse index fixture needs an index accessor")
        add_sparse(accessors[1], 0, sparse_index_value.to_bytes(2, "little"))
    if sparse_joint_value is not None:
        if first_joint_accessor is None:
            raise ValueError("sparse joint fixture needs a skinned mesh")
        add_sparse(accessors[first_joint_accessor], 0, bytes([sparse_joint_value, 0, 0, 0]))
    if sparse_weight_value is not None:
        if first_weight_accessor is None:
            raise ValueError("sparse weight fixture needs a skinned mesh")
        add_sparse(
            accessors[first_weight_accessor], 0, struct.pack("<4f", sparse_weight_value, 0, 0, 0)
        )
    if sparse_animation_value is not None:
        if animation_output_accessor is None:
            raise ValueError("sparse animation fixture needs an animation")
        add_sparse(
            accessors[animation_output_accessor],
            0,
            struct.pack("<3f", *sparse_animation_value),
        )
    if node_fields is not None:
        nodes.append({"mesh": 0, **node_fields})
    value = document or {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
        "meshes": [{"primitives": [primitive] * primitive_count}],
        "nodes": nodes,
        "skins": skins,
        "animations": animations,
        "images": images,
        "textures": textures,
        "materials": materials,
    }
    chunk = json.dumps(value, separators=(",", ":")).encode("utf-8")
    chunk += b" " * ((-len(chunk)) % 4)
    binary = binary if document is None else b""
    chunks = len(chunk).to_bytes(4, "little") + (0x4E4F534A).to_bytes(4, "little") + chunk
    if binary:
        chunks += len(binary).to_bytes(4, "little") + (0x004E4942).to_bytes(4, "little") + binary
    return b"glTF" + (2).to_bytes(4, "little") + (12 + len(chunks)).to_bytes(4, "little") + chunks


def _target() -> RobloxAssetTarget:
    return RobloxAssetTarget("groupId", "123456", "server-secret", poll_timeout_seconds=1)


def _rewrite_glb_json(glb: bytes, update) -> bytes:
    json_length = int.from_bytes(glb[12:16], "little")
    assert int.from_bytes(glb[16:20], "little") == 0x4E4F534A
    document = json.loads(glb[20 : 20 + json_length])
    update(document)
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    chunks = len(json_chunk).to_bytes(4, "little") + (0x4E4F534A).to_bytes(4, "little")
    chunks += json_chunk
    binary_offset = 20 + json_length
    if binary_offset < len(glb):
        chunks += glb[binary_offset:]
    return b"glTF" + (2).to_bytes(4, "little") + (12 + len(chunks)).to_bytes(4, "little") + chunks


class _FakeUploader(OpenCloudModelAssetUploader):
    def __init__(self, *, moderation: str = "MODERATION_STATE_APPROVED", fail: bool = False):
        super().__init__(_target(), poll_interval_seconds=0.1)
        self.calls: list[tuple[str, str, bytes | None, str | None]] = []
        self.moderation = moderation
        self.fail = fail

    def _request(
        self, method: str, path: str, body: bytes | None = None, content_type: str | None = None
    ) -> object:
        self.calls.append((method, path, body, content_type))
        if self.fail:
            raise RobloxAssetError("simulated uncertain outcome")
        if method == "POST":
            return {"path": "operations/operation-123"}
        if path == "/assets/v1/assets/987654321":
            return {
                "assetId": "987654321",
                "assetType": "Model",
                "revisionId": "1",
                "creationContext": {"creator": {"groupId": 123456}},
                "moderationResult": {"moderationState": self.moderation},
            }
        return {
            "path": "operations/operation-123",
            "done": True,
            "response": {
                "assetId": "987654321",
                "assetType": "ASSET_TYPE_MODEL",
                "moderationResult": {"moderationState": self.moderation},
            },
        }


def _upload(uploader: OpenCloudModelAssetUploader, request_id: str, data: bytes):
    return uploader.upload_glb(
        data,
        display_name="Reviewed scene",
        description="Generated model",
        request_id=request_id,
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
    )


def test_target_pins_creator_and_requires_explicit_environment_confirmation(
    monkeypatch: pytest.MonkeyPatch,
):
    values = {
        "RGA_ROBLOX_ASSET_CREATOR_TYPE": "groupId",
        "RGA_ROBLOX_ASSET_CREATOR_ID": "123456",
        "ROBLOX_OPEN_CLOUD_ASSET_API_KEY": "server-key",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("RGA_ROBLOX_ASSET_CREATION_CONFIRMED", raising=False)
    with pytest.raises(ValueError, match="confirmation"):
        RobloxAssetTarget.from_env()
    monkeypatch.setenv("RGA_ROBLOX_ASSET_CREATION_CONFIRMED", "I_ACCEPT_ROBLOX_ASSET_CREATION")
    target = RobloxAssetTarget.from_env()
    assert target.creator_type == "groupId"
    assert target.creator_id == "123456"


def test_model_upload_pins_creator_binds_digest_and_reports_moderation():
    data = _glb()
    uploader = _FakeUploader(moderation="MODERATION_STATE_REVIEWING")
    request_id = str(uuid.uuid4())
    receipt = _upload(uploader, request_id, data)
    assert receipt.asset_id == "987654321"
    assert receipt.status == "moderation_pending"
    assert receipt.request_id == request_id
    post = uploader.calls[0]
    assert post[0:2] == ("POST", "/assets/v1/assets")
    assert post[3].startswith("multipart/form-data; boundary=rga")
    assert post[2] is not None and data in post[2]
    metadata = post[2].split(b"\r\n\r\n", 2)[1].split(b"\r\n--", 1)[0]
    request = json.loads(metadata)
    assert request["assetType"] == "Model"
    assert request["creationContext"]["creator"] == {"groupId": "123456"}


def test_upload_rejects_wrong_digest_invalid_glb_and_external_uri_before_network():
    uploader = _FakeUploader()
    data = _glb()
    with pytest.raises(ValueError, match="digest"):
        uploader.upload_glb(
            data,
            display_name="Scene",
            description="Scene model",
            request_id=str(uuid.uuid4()),
            approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            approved_sha256="0" * 64,
        )
    with pytest.raises(ValueError, match="binary GLB"):
        uploader.upload_glb(
            b"nope"
            + (2).to_bytes(4, "little")
            + (20).to_bytes(4, "little")
            + (0).to_bytes(8, "little"),
            display_name="Scene",
            description="Scene model",
            request_id=str(uuid.uuid4()),
            approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            approved_sha256=hashlib.sha256(
                b"nope"
                + (2).to_bytes(4, "little")
                + (20).to_bytes(4, "little")
                + (0).to_bytes(8, "little")
            ).hexdigest(),
        )
    external = _glb(
        {
            "asset": {"version": "2.0"},
            "meshes": [{"primitives": [{"attributes": {}}]}],
            "buffers": [{"uri": "https://example"}],
        }
    )
    with pytest.raises(ValueError, match="external resource"):
        _upload(uploader, str(uuid.uuid4()), external)
    empty_mesh = _glb({"asset": {"version": "2.0"}, "meshes": []})
    with pytest.raises(ValueError, match="mesh primitives"):
        _upload(uploader, str(uuid.uuid4()), empty_mesh)
    limited = OpenCloudModelAssetUploader(
        RobloxAssetTarget("groupId", "123456", "server-secret", max_glb_bytes=20)
    )
    with pytest.raises(ValueError, match="size limit"):
        _upload(limited, str(uuid.uuid4()), data)
    assert uploader.calls == []


def test_upload_rejects_uninspected_glb_extensions_before_network():
    uploader = _FakeUploader()
    cases = [
        (
            lambda document: document.update(
                extensionsUsed=["KHR_draco_mesh_compression"],
                extensionsRequired=["KHR_draco_mesh_compression"],
            ),
            "does not inspect",
        ),
        (
            lambda document: document.update(extensionsRequired=["KHR_draco_mesh_compression"]),
            "extension declarations are invalid",
        ),
        (
            lambda document: document["meshes"][0]["primitives"][0].update(
                extensions={
                    "KHR_draco_mesh_compression": {
                        "bufferView": 0,
                        "attributes": {"POSITION": 0},
                    }
                }
            ),
            "does not inspect",
        ),
    ]
    for update, message in cases:
        data = _rewrite_glb_json(_glb(), update)
        with pytest.raises(ValueError, match=message):
            _upload(uploader, str(uuid.uuid4()), data)
    assert uploader.calls == []


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"vertex_count": 60_003}, "per-mesh vertex limit"),
        ({"vertex_count": 3, "index_count": 60_003}, "20,000-triangle"),
    ],
)
def test_upload_rejects_mesh_over_roblox_geometry_limits_before_network(geometry, message):
    uploader = _FakeUploader()
    data = _glb(**geometry)
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), data)
    assert uploader.calls == []


def test_upload_accepts_bounded_finite_node_transform():
    uploader = _FakeUploader()
    receipt = _upload(uploader, str(uuid.uuid4()), _glb(node_fields={"translation": [1, 2, 3]}))
    assert receipt.asset_id == "987654321"


@pytest.mark.parametrize(
    ("node_fields", "message"),
    [
        ({"translation": [1_000_001, 0, 0]}, "node transform is invalid"),
        ({"scale": [float("nan"), 1, 1]}, "GLB JSON chunk is invalid"),
        ({"matrix": [0] * 16, "translation": [0, 0, 0]}, "cannot combine matrix and TRS"),
        ({"children": [0]}, "node hierarchy contains a cycle"),
        ({"mesh": 1}, "node references an invalid mesh"),
    ],
)
def test_upload_rejects_invalid_node_transforms_and_hierarchy_before_network(node_fields, message):
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), _glb(node_fields=node_fields))
    assert uploader.calls == []


def test_upload_applies_triangle_limit_to_each_imported_primitive():
    uploader = _FakeUploader()
    receipt = _upload(
        uploader,
        str(uuid.uuid4()),
        _glb(vertex_count=36_000, primitive_count=2),
    )
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


def test_upload_caps_total_accessor_validation_work_across_reused_primitives():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="total accessor validation work limit"):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(vertex_count=60_000, primitive_count=17),
        )
    assert uploader.calls == []


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"index_count": 3, "first_index": 3}, "index value exceeds"),
        ({"vertex_count": 3, "position_view_length": 12}, "exceeds or misaligns"),
        ({"position_byte_offset": 2}, "exceeds or misaligns"),
        ({"position_stride": 13}, "exceeds or misaligns"),
    ],
)
def test_upload_rejects_geometry_outside_embedded_buffer_before_network(geometry, message):
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), _glb(**geometry))
    assert uploader.calls == []


def test_upload_bounds_unreferenced_mesh_vertices_before_network():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="per-mesh vertex limit"):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(vertex_count=60_001, index_count=3),
        )
    assert uploader.calls == []


def test_upload_accepts_standard_normal_attribute_with_matching_position_count():
    uploader = _FakeUploader()
    glb = _rewrite_glb_json(
        _glb(),
        lambda document: document["meshes"][0]["primitives"][0]["attributes"].update({"NORMAL": 0}),
    )
    receipt = _upload(uploader, str(uuid.uuid4()), glb)
    assert receipt.asset_id == "987654321"


def test_upload_rejects_normalized_float_position_accessor():
    uploader = _FakeUploader()
    glb = _rewrite_glb_json(
        _glb(), lambda document: document["accessors"][0].update(normalized=True)
    )
    with pytest.raises(ValueError, match="POSITION accessor must use 32-bit floats"):
        _upload(uploader, str(uuid.uuid4()), glb)
    assert uploader.calls == []


@pytest.mark.parametrize(
    ("semantic", "accessor", "message"),
    [
        ("NORMAL", 9, "invalid accessor"),
        ("JOINTS_00", 0, "set index is invalid"),
    ],
)
def test_upload_rejects_unvalidated_vertex_attribute_references(semantic, accessor, message):
    uploader = _FakeUploader()
    glb = _rewrite_glb_json(
        _glb(),
        lambda document: document["meshes"][0]["primitives"][0]["attributes"].update(
            {semantic: accessor}
        ),
    )
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), glb)
    assert uploader.calls == []


@pytest.mark.parametrize(
    ("accessor", "message"),
    [
        (
            {"bufferView": 0, "componentType": 5126, "count": 2, "type": "VEC3"},
            "counts do not match",
        ),
        (
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "SCALAR"},
            "unsupported type",
        ),
    ],
)
def test_upload_rejects_vertex_attributes_with_incompatible_accessors(accessor, message):
    uploader = _FakeUploader()

    def add_bad_normal(document):
        document["accessors"].append(accessor)
        document["meshes"][0]["primitives"][0]["attributes"]["NORMAL"] = (
            len(document["accessors"]) - 1
        )

    glb = _rewrite_glb_json(_glb(), add_bad_normal)
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), glb)
    assert uploader.calls == []


@pytest.mark.parametrize("without_base", [False, True])
def test_upload_accepts_valid_sparse_position_accessor(without_base):
    uploader = _FakeUploader()
    receipt = _upload(
        uploader,
        str(uuid.uuid4()),
        _glb(sparse_position=(0.25, 0.0, 0.0), sparse_position_without_base=without_base),
    )
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


def test_upload_checks_sparse_position_replacements_for_nonfinite_values():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="POSITION contains a non-finite value"):
        _upload(uploader, str(uuid.uuid4()), _glb(sparse_position=(float("nan"), 0.0, 0.0)))
    assert uploader.calls == []


def test_upload_rejects_sparse_accessor_indices_outside_the_accessor():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="sparse indices must be increasing and within"):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(sparse_position=(0.0, 0.0, 0.0), sparse_position_index=3),
        )
    assert uploader.calls == []


def test_upload_checks_sparse_index_replacements_against_position_count():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="index value exceeds the POSITION accessor"):
        _upload(uploader, str(uuid.uuid4()), _glb(index_count=3, sparse_index_value=3))
    assert uploader.calls == []


@pytest.mark.parametrize("influences", [1, 4])
def test_upload_accepts_rigged_meshes_with_supported_influence_counts(influences):
    uploader = _FakeUploader()
    receipt = _upload(uploader, str(uuid.uuid4()), _glb(skin_influences=influences))
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


def test_upload_accepts_finite_inverse_bind_matrices_for_skin_joints():
    identity = (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    uploader = _FakeUploader()
    receipt = _upload(
        uploader,
        str(uuid.uuid4()),
        _glb(skin_influences=1, inverse_bind_matrices=[identity] * 4),
    )
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


@pytest.mark.parametrize(
    ("matrices", "message"),
    [
        (
            [(1.0, 0.0, 0.0, 0.5, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)] * 4,
            "invalid fourth row",
        ),
        (
            [
                (
                    float("nan"),
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    1.0,
                )
            ]
            * 4,
            "non-finite value",
        ),
        (
            [(1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)],
            "inverse bind matrix accessor is invalid",
        ),
    ],
)
def test_upload_rejects_invalid_inverse_bind_matrices_before_network(matrices, message):
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match=message):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(skin_influences=1, inverse_bind_matrices=matrices),
        )
    assert uploader.calls == []


def test_upload_rejects_malformed_inverse_bind_accessor_before_network():
    data = _rewrite_glb_json(
        _glb(skin_influences=1, inverse_bind_matrices=[]),
        lambda document: document["accessors"][-1].update(type="VEC4"),
    )
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="inverse bind matrix accessor is invalid"):
        _upload(uploader, str(uuid.uuid4()), data)
    assert uploader.calls == []


def test_upload_applies_sparse_skin_accessor_replacements():
    uploader = _FakeUploader()
    receipt = _upload(
        uploader,
        str(uuid.uuid4()),
        _glb(skin_influences=1, sparse_joint_value=1, sparse_weight_value=1.0),
    )
    assert receipt.asset_id == "987654321"


def test_upload_accepts_bounded_morph_target_accessors():
    data = _rewrite_glb_json(
        _glb(),
        lambda document: document["meshes"][0]["primitives"][0].update(targets=[{"POSITION": 0}]),
    )
    uploader = _FakeUploader()
    receipt = _upload(uploader, str(uuid.uuid4()), data)
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


@pytest.mark.parametrize(
    ("target", "message"),
    [
        ({"POSITION": 4}, "morph target references an invalid accessor"),
        ({"POSITION": "0"}, "morph target references an invalid accessor"),
        ({"_CUSTOM": 0}, "unsupported attribute"),
        ({"NORMAL": 0}, "missing from its base primitive"),
        ({}, "morph target is invalid"),
    ],
)
def test_upload_rejects_invalid_morph_target_contracts_before_network(target, message):
    data = _rewrite_glb_json(
        _glb(),
        lambda document: document["meshes"][0]["primitives"][0].update(targets=[target]),
    )
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), data)
    assert uploader.calls == []


def test_upload_rejects_morph_target_count_mismatch_and_inconsistent_primitives():
    wrong_accessor_count = _rewrite_glb_json(
        _glb(),
        lambda document: (
            document["accessors"].append({**document["accessors"][0], "count": 2}),
            document["meshes"][0]["primitives"][0].update(targets=[{"POSITION": 1}]),
        ),
    )
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="morph target accessor does not match POSITION"):
        _upload(uploader, str(uuid.uuid4()), wrong_accessor_count)
    assert uploader.calls == []

    inconsistent = _rewrite_glb_json(
        _glb(primitive_count=2),
        lambda document: document["meshes"][0]["primitives"][0].update(targets=[{"POSITION": 0}]),
    )
    with pytest.raises(ValueError, match="inconsistent morph target counts"):
        _upload(_FakeUploader(), str(uuid.uuid4()), inconsistent)


def test_upload_checks_mesh_node_and_animation_weights_against_morph_targets():
    valid_weights = _rewrite_glb_json(
        _glb(),
        lambda document: (
            document["meshes"][0]["primitives"][0].update(targets=[{"POSITION": 0}]),
            document["meshes"][0].update(weights=[0.0]),
            document.update(nodes=[{"mesh": 0, "weights": [0.0]}]),
        ),
    )
    uploader = _FakeUploader()
    assert _upload(uploader, str(uuid.uuid4()), valid_weights).asset_id == "987654321"

    bad_mesh_weights = _rewrite_glb_json(
        _glb(), lambda document: document["meshes"][0].update(weights=[1.0])
    )
    with pytest.raises(ValueError, match="mesh weights do not match"):
        _upload(_FakeUploader(), str(uuid.uuid4()), bad_mesh_weights)

    bad_node_weights = _rewrite_glb_json(
        _glb(), lambda document: document.update(nodes=[{"weights": [1.0]}])
    )
    with pytest.raises(ValueError, match="node weights do not match"):
        _upload(_FakeUploader(), str(uuid.uuid4()), bad_node_weights)

    bad_animation_weights = _rewrite_glb_json(
        _glb(animation=True),
        lambda document: document["animations"][0]["channels"][0]["target"].update(path="weights"),
    )
    with pytest.raises(ValueError, match="morph-weight animation output has invalid dimensions"):
        _upload(_FakeUploader(), str(uuid.uuid4()), bad_animation_weights)


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"skin_influences": 5}, "four-bone influence limit"),
        ({"skin_influences": 4, "first_skin_joint": 4}, "joint index exceeds"),
    ],
)
def test_upload_rejects_unsupported_or_invalid_skinning_before_network(geometry, message):
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), _glb(**geometry))
    assert uploader.calls == []


def test_upload_rejects_invalid_sparse_skin_values_before_network():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="joint index exceeds"):
        _upload(uploader, str(uuid.uuid4()), _glb(skin_influences=1, sparse_joint_value=4))
    assert uploader.calls == []
    with pytest.raises(ValueError, match="negative or non-finite weight"):
        _upload(uploader, str(uuid.uuid4()), _glb(skin_influences=1, sparse_weight_value=-1.0))
    assert uploader.calls == []


def test_upload_accepts_a_structurally_valid_animation_clip():
    uploader = _FakeUploader()
    receipt = _upload(uploader, str(uuid.uuid4()), _glb(animation=True))
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


def test_upload_applies_sparse_animation_values_and_checks_finiteness():
    uploader = _FakeUploader()
    receipt = _upload(
        uploader,
        str(uuid.uuid4()),
        _glb(animation=True, sparse_animation_value=(0.25, 0.0, 0.0)),
    )
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"

    rejected_uploader = _FakeUploader()
    with pytest.raises(ValueError, match="animation output contains a non-finite value"):
        _upload(
            rejected_uploader,
            str(uuid.uuid4()),
            _glb(animation=True, sparse_animation_value=(float("nan"), 0.0, 0.0)),
        )
    assert rejected_uploader.calls == []


def test_upload_rejects_animation_outputs_with_wrong_keyframe_count_before_network():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="output does not match its target path"):
        _upload(uploader, str(uuid.uuid4()), _glb(animation=True, animation_output_count=1))
    assert uploader.calls == []


def test_upload_bounds_animation_accessor_counts_before_network():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="animation element limit"):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(animation=True, animation_input_count=100_001),
        )
    assert uploader.calls == []


def test_upload_accepts_supported_embedded_png_texture_dimensions():
    pytest.importorskip("PIL")
    uploader = _FakeUploader()
    receipt = _upload(uploader, str(uuid.uuid4()), _glb(texture_dimensions=(1024, 1024)))
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


def test_upload_rejects_texture_above_roblox_dimension_limit_before_network():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="4096x4096"):
        _upload(uploader, str(uuid.uuid4()), _glb(texture_dimensions=(4097, 1)))
    assert uploader.calls == []


def test_upload_rejects_excessive_gltf_image_count_before_network():
    data = _rewrite_glb_json(
        _glb(texture_dimensions=(1, 1)),
        lambda document: document.update(images=document["images"] * 257),
    )
    uploader = _FakeUploader()

    with pytest.raises(ValueError, match="image count exceeds structural limits"):
        _upload(uploader, str(uuid.uuid4()), data)
    assert uploader.calls == []


def test_upload_rejects_excessive_total_texture_pixels_before_network():
    data = _rewrite_glb_json(
        _glb(
            texture_dimensions=(4096, 4096),
            texture_mime="image/jpeg",
            malformed_jpeg=True,
        ),
        lambda document: document.update(images=document["images"] * 4),
    )
    uploader = _FakeUploader()

    with pytest.raises(ValueError, match="total pixel budget"):
        _upload(uploader, str(uuid.uuid4()), data)
    assert uploader.calls == []


def test_upload_rejects_png_with_invalid_chunk_checksum_before_network():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="checksum"):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(texture_dimensions=(1, 1), corrupt_texture_crc=True),
        )
    assert uploader.calls == []


def test_upload_fails_closed_when_remote_image_decoder_is_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "PIL", None)
    uploader = _FakeUploader()

    with pytest.raises(ValueError, match="failed full pixel decoding"):
        _upload(uploader, str(uuid.uuid4()), _glb(texture_dimensions=(1, 1)))
    assert uploader.calls == []


def test_upload_accepts_jpeg_with_dimensions_inside_roblox_limit():
    pytest.importorskip("PIL")
    uploader = _FakeUploader()
    receipt = _upload(
        uploader,
        str(uuid.uuid4()),
        _glb(texture_dimensions=(4096, 256), texture_mime="image/jpeg"),
    )
    assert receipt.asset_id == "987654321"
    assert uploader.calls[0][0] == "POST"


def test_upload_rejects_jpeg_with_valid_structure_but_invalid_compressed_pixels():
    pytest.importorskip("PIL")
    uploader = _FakeUploader()

    with pytest.raises(ValueError, match="failed full pixel decoding"):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(texture_dimensions=(8, 4), texture_mime="image/jpeg", malformed_jpeg=True),
        )
    assert uploader.calls == []


def test_jpeg_dimension_check_rejects_header_only_and_truncated_scans():
    valid_image = (
        b"\xff\xd8\xff\xc0\x00\x0b\x08\x00\x04\x00\x08\x01\x01\x11\x00"
        b"\xff\xda\x00\x08\x01\x01\x00\x00\x3f\x00\x3f\xff\xd9"
    )
    with pytest.raises(ValueError, match="complete image scan"):
        _image_dimensions(valid_image[:15], "image/jpeg")
    with pytest.raises(ValueError, match="complete image scan"):
        _image_dimensions(valid_image[:-2], "image/jpeg")
    assert _image_dimensions(valid_image, "image/jpeg") == (8, 4)
    with pytest.raises(ValueError, match="empty image scan"):
        _image_dimensions(valid_image[:-3] + b"\xff\xd9", "image/jpeg")
    with pytest.raises(ValueError, match="incomplete"):
        _image_dimensions(valid_image + b"\x00", "image/jpeg")


def test_upload_rejects_oversized_jpeg_before_network():
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match="4096x4096"):
        _upload(
            uploader,
            str(uuid.uuid4()),
            _glb(
                texture_dimensions=(4097, 1),
                texture_mime="image/jpeg",
                malformed_jpeg=True,
            ),
        )
    assert uploader.calls == []


@pytest.mark.parametrize(
    ("geometry", "message"),
    [
        ({"texture_source_index": 1}, "missing embedded image"),
        ({"material_texture_index": 1}, "missing texture"),
    ],
)
def test_upload_rejects_broken_material_texture_references_before_network(geometry, message):
    pytest.importorskip("PIL")
    uploader = _FakeUploader()
    with pytest.raises(ValueError, match=message):
        _upload(uploader, str(uuid.uuid4()), _glb(texture_dimensions=(16, 16), **geometry))
    assert uploader.calls == []


def test_upload_ledger_caches_success_and_rejects_request_reuse(tmp_path):
    ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    request_id = str(uuid.uuid4())
    data = _glb()
    first_uploader = _FakeUploader()
    first = ledger.run(
        first_uploader,
        data,
        request_id=request_id,
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
        display_name="Reviewed scene",
        description="Generated model",
    )
    second_uploader = _FakeUploader()
    second = ledger.run(
        second_uploader,
        data,
        request_id=request_id,
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
        display_name="Reviewed scene",
        description="Generated model",
    )
    assert second == first
    assert ledger.is_approved_model("987654321")
    assert not ledger.is_approved_model("987654322")
    assert second_uploader.calls == []
    with pytest.raises(ValueError, match="different asset content"):
        ledger.run(
            _FakeUploader(),
            data,
            request_id=request_id,
            approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
            approved_sha256=hashlib.sha256(data).hexdigest(),
            display_name="Different name",
            description="Generated model",
        )


def test_moderation_pending_model_cannot_be_imported_from_upload_ledger(tmp_path):
    ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    data = _glb()
    ledger.run(
        _FakeUploader(moderation="MODERATION_STATE_REVIEWING"),
        data,
        request_id=str(uuid.uuid4()),
        approval_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        approved_sha256=hashlib.sha256(data).hexdigest(),
        display_name="Reviewed scene",
        description="Generated model",
    )
    assert not ledger.is_approved_model("987654321")


def test_uncertain_upload_is_never_submitted_twice(tmp_path):
    ledger = AssetUploadLedger(tmp_path / "assets.sqlite3")
    request_id = str(uuid.uuid4())
    data = _glb()
    args = {
        "request_id": request_id,
        "approval_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "approved_sha256": hashlib.sha256(data).hexdigest(),
        "display_name": "Reviewed scene",
        "description": "Generated model",
    }
    with pytest.raises(RobloxAssetError, match="uncertain outcome"):
        ledger.run(_FakeUploader(fail=True), data, **args)
    retry = _FakeUploader()
    with pytest.raises(RobloxAssetError, match="will not be resubmitted"):
        ledger.run(retry, data, **args)
    assert retry.calls == []


def test_approval_signature_expires_and_binds_exact_artifact():
    data = _glb()
    digest = hashlib.sha256(data).hexdigest()
    fields = {
        "request_id": "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
        "approval_id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
        "artifact_sha256": digest,
        "display_name": "Reviewed scene",
        "description": "Generated model",
        "expires_at": 1000,
    }
    signature = sign_asset_approval("a" * 40, **fields)
    assert verify_asset_approval("a" * 40, signature, **fields, now=999)
    assert not verify_asset_approval(
        "a" * 40,
        signature,
        **{**fields, "artifact_sha256": "0" * 64},
        now=999,
    )
    assert not verify_asset_approval("a" * 40, signature, **fields, now=1000)


def test_mcp_asset_upload_requires_signed_approval_and_is_idempotent(tmp_path):
    data = _glb()
    token = "t" * 40
    approval_secret = "s" * 40
    uploader = _FakeUploader(moderation="MODERATION_STATE_REVIEWING")
    server = RobloxMCPServer(
        "127.0.0.1",
        0,
        None,
        None,
        token,
        asset_uploader=uploader,
        asset_ledger=AssetUploadLedger(tmp_path / "assets.sqlite3"),
        asset_approval_secret=approval_secret,
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    request_id = str(uuid.uuid4())
    approval_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    digest = hashlib.sha256(data).hexdigest()
    expires_at = int(time.time()) + 300
    signature = sign_asset_approval(
        approval_secret,
        request_id=request_id,
        approval_id=approval_id,
        artifact_sha256=digest,
        display_name="Reviewed scene",
        description="Generated model",
        expires_at=expires_at,
    )

    def post(request: dict[str, Any]) -> dict[str, Any]:
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request(
                "POST",
                "/mcp",
                body=json.dumps(request).encode(),
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-11-25",
                },
            )
            return json.loads(connection.getresponse().read())
        finally:
            connection.close()

    try:
        listing = post({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in listing["result"]["tools"]]
        assert "rga_upload_reviewed_model" in names
        client = RobloxMCPClient(f"http://127.0.0.1:{server.server_address[1]}/mcp", token)
        result = client.upload_reviewed_model(
            data,
            request_id=request_id,
            approval_id=approval_id,
            display_name="Reviewed scene",
            description="Generated model",
            approval_secret=approval_secret,
        )
        assert result.request_id == request_id
        assert result.status == "moderation_pending"
        assert len(uploader.calls) == 2
        replay = client.upload_reviewed_model(
            data,
            request_id=request_id,
            approval_id=approval_id,
            display_name="Reviewed scene",
            description="Generated model",
            approval_secret=approval_secret,
        )
        assert replay == result
        assert len(uploader.calls) == 2
        arguments = {
            "request_id": request_id,
            "approval_id": approval_id,
            "artifact_sha256": "0" * 64,
            "approval_signature": signature,
            "approval_expires_at": expires_at,
            "display_name": "Reviewed scene",
            "description": "Generated model",
            "glb_base64": base64.b64encode(data).decode("ascii"),
        }
        forged = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "rga_upload_reviewed_model", "arguments": arguments},
        }
        rejected = post(forged)["result"]
        assert rejected["isError"] is True
        assert len(uploader.calls) == 2
        uploader.moderation = "Approved"
        status_call = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "rga_check_model_upload", "arguments": {"request_id": request_id}},
        }
        refreshed = post(status_call)["result"]["structuredContent"]
        assert refreshed["status"] == "approved"
        assert refreshed["artifact_sha256"] == digest
        assert refreshed["operation_id"] == result.operation_id
        assert AssetUploadLedger(tmp_path / "assets.sqlite3").is_approved_model(
            refreshed["asset_id"]
        )
        assert post(status_call)["result"]["structuredContent"] == refreshed
        status_call["params"]["arguments"]["request_id"] = str(uuid.uuid4())
        assert post(status_call)["result"]["isError"]
        assert [call[:2] for call in uploader.calls] == [
            ("POST", "/assets/v1/assets"),
            ("GET", "/assets/v1/operations/operation-123"),
            ("GET", "/assets/v1/assets/987654321"),
        ]
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
