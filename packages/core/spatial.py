"""Shared axis-aligned spatial checks for generated scene recipes."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .worldbuilding import SceneObject

PATH_SEGMENT_MAX_GAP = 1.0


def object_bounds(item: SceneObject) -> tuple[tuple[float, float, float], ...]:
    """Compute a scene object's world-space AABB after recipe scale and rotation."""
    if item.mesh is not None:
        local_min = tuple(min(vertex[axis] for vertex in item.mesh.vertices) for axis in range(3))
        local_max = tuple(max(vertex[axis] for vertex in item.mesh.vertices) for axis in range(3))
    else:
        primitive_bounds = {
            "plane": (1.0, 1.0, 0.0),
            "torus": (1.25, 1.25, 0.25),
        }
        local_extent = primitive_bounds.get(item.primitive or "", (1.0, 1.0, 1.0))
        local_min = tuple(-extent for extent in local_extent)
        local_max = tuple(local_extent)

    local_center = tuple((low + high) * 0.5 for low, high in zip(local_min, local_max, strict=True))
    local_half = tuple((high - low) * 0.5 for low, high in zip(local_min, local_max, strict=True))
    scaled_center = tuple(
        center * scale for center, scale in zip(local_center, item.scale, strict=True)
    )
    scaled_half = tuple(half * scale for half, scale in zip(local_half, item.scale, strict=True))
    matrix = _rotation_matrix_xyz(item.rotation_deg)
    center = tuple(
        item.location[row] + sum(matrix[row][axis] * scaled_center[axis] for axis in range(3))
        for row in range(3)
    )
    half = tuple(
        sum(abs(matrix[row][axis]) * scaled_half[axis] for axis in range(3)) for row in range(3)
    )
    return (
        tuple(center[axis] - half[axis] for axis in range(3)),
        tuple(center[axis] + half[axis] for axis in range(3)),
    )


def bounds_distance(
    first: tuple[tuple[float, float, float], ...],
    second: tuple[tuple[float, float, float], ...],
) -> float:
    """Euclidean gap between two 3D axis-aligned bounds; zero means touching."""
    gaps = tuple(
        max(0.0, first[0][axis] - second[1][axis], second[0][axis] - first[1][axis])
        for axis in range(3)
    )
    return math.sqrt(sum(gap * gap for gap in gaps))


def largest_connected_component(
    bounds: list[tuple[tuple[float, float, float], ...]], max_gap: float
) -> int:
    """Return the largest connected component using pairwise AABB gap edges."""
    if not math.isfinite(max_gap) or max_gap < 0:
        raise ValueError("max_gap must be finite and non-negative")
    remaining = set(range(len(bounds)))
    largest = 0
    while remaining:
        component = {remaining.pop()}
        frontier = list(component)
        while frontier:
            current = frontier.pop()
            connected = {
                candidate
                for candidate in remaining
                if bounds_distance(bounds[current], bounds[candidate]) <= max_gap
            }
            remaining.difference_update(connected)
            component.update(connected)
            frontier.extend(connected)
        largest = max(largest, len(component))
    return largest


def _rotation_matrix_xyz(rotation_deg: tuple[float, float, float]) -> tuple[tuple[float, ...], ...]:
    x, y, z = (math.radians(angle) for angle in rotation_deg)
    cx, sx = math.cos(x), math.sin(x)
    cy, sy = math.cos(y), math.sin(y)
    cz, sz = math.cos(z), math.sin(z)
    return (
        (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
        (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
        (-sy, cy * sx, cy * cx),
    )
