"""Shared size ceilings for generated Roblox model artifacts."""

# Roblox documents a 20 MB maximum file size for Open Cloud asset uploads.
# Keep RGA's shared model ceiling at 19 MiB across its client and server paths.
ROBLOX_MODEL_UPLOAD_MAX_BYTES = 19 * 1024 * 1024
