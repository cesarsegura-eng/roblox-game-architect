"""Exercise bounded PNG/JPEG decoding in the remote asset service image."""

from __future__ import annotations

import io
import json
import struct

from PIL import Image

from .assets import MAX_GLB_BYTES, _validate_glb


def _glb_with_texture(mime_type: str, image_data: bytes) -> bytes:
    positions = b"\0" * 36
    image_offset = len(positions)
    binary = positions + image_data
    document = {
        "asset": {"version": "2.0"},
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(positions)},
            {
                "buffer": 0,
                "byteOffset": image_offset,
                "byteLength": len(image_data),
            },
        ],
        "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3"}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "images": [{"bufferView": 1, "mimeType": mime_type}],
        "textures": [{"source": 0}],
        "materials": [{"pbrMetallicRoughness": {"baseColorTexture": {"index": 0}}}],
    }
    json_chunk = json.dumps(document, separators=(",", ":")).encode("utf-8")
    json_chunk += b" " * ((-len(json_chunk)) % 4)
    binary_chunk = binary + b"\0" * ((-len(binary)) % 4)
    chunks = (
        struct.pack("<I4s", len(json_chunk), b"JSON")
        + json_chunk
        + struct.pack("<I4s", len(binary_chunk), b"BIN\0")
        + binary_chunk
    )
    return struct.pack("<4sII", b"glTF", 2, 12 + len(chunks)) + chunks


def _jpeg(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    with Image.new("RGB", (width, height), (64, 112, 168)) as image:
        image.save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


def _structurally_valid_but_undecodable_jpeg(width: int, height: int) -> bytes:
    quantization_table = b"\x00" + b"\x01" * 64
    huffman_counts = b"\x01" + b"\x00" * 15
    dc_table = b"\x00" + huffman_counts + b"\x00"
    ac_table = b"\x10" + huffman_counts + b"\x00"
    return (
        b"\xff\xd8\xff\xdb\x00\x43"
        + quantization_table
        + b"\xff\xc0\x00\x0b\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00\xff\xc4\x00\x14"
        + dc_table
        + b"\xff\xc4\x00\x14"
        + ac_table
        + b"\xff\xda\x00\x08\x01\x31\x00\x00\x3f\x00\x3f\xff\xd9"
    )


def main() -> None:
    png = io.BytesIO()
    with Image.new("RGBA", (16, 8), (42, 118, 76, 255)) as image:
        image.save(png, format="PNG")
    _validate_glb(_glb_with_texture("image/png", png.getvalue()), MAX_GLB_BYTES)

    jpeg = _jpeg(16, 8)
    _validate_glb(_glb_with_texture("image/jpeg", jpeg), MAX_GLB_BYTES)

    malformed = _glb_with_texture("image/jpeg", _structurally_valid_but_undecodable_jpeg(16, 8))
    try:
        _validate_glb(malformed, MAX_GLB_BYTES)
    except ValueError as exc:
        if "full pixel decoding" not in str(exc):
            raise
    else:
        raise RuntimeError("asset preflight accepted undecodable JPEG pixels")
    print("RGA_ASSET_IMAGE_SMOKE_OK png=decoded jpeg=decoded malformed_jpeg=rejected")


if __name__ == "__main__":
    main()
