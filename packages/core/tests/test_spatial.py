"""Axis-aligned bounds and connectivity checks used to grade generated scenes."""

import math

import pytest

from core.spatial import bounds_distance, largest_connected_component, object_bounds
from core.worldbuilding import SceneMesh, SceneObject


def _object(**overrides: object) -> SceneObject:
    values: dict[str, object] = {
        "name": "block",
        "primitive": "cube",
        "role": "landmark",
        "location": (0.0, 0.0, 0.0),
        "rotation_deg": (0.0, 0.0, 0.0),
        "scale": (1.0, 1.0, 1.0),
    }
    values.update(overrides)
    return SceneObject(**values)  # type: ignore[arg-type]


def _close(first: tuple[float, ...], second: tuple[float, ...]) -> bool:
    return all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(first, second, strict=True))


def test_a_unit_cube_spans_one_each_way_from_its_centre() -> None:
    low, high = object_bounds(_object(location=(10.0, 0.0, 5.0)))

    assert _close(low, (9.0, -1.0, 4.0))
    assert _close(high, (11.0, 1.0, 6.0))


def test_scale_stretches_the_bounds() -> None:
    low, high = object_bounds(_object(scale=(2.0, 3.0, 4.0)))

    assert _close(low, (-2.0, -3.0, -4.0))
    assert _close(high, (2.0, 3.0, 4.0))


def test_a_quarter_turn_swaps_the_horizontal_extents() -> None:
    low, high = object_bounds(_object(scale=(4.0, 1.0, 1.0), rotation_deg=(0.0, 0.0, 90.0)))

    assert _close(low, (-1.0, -4.0, -1.0))
    assert _close(high, (1.0, 4.0, 1.0))


def test_a_plane_is_flat_and_a_torus_is_thin() -> None:
    plane_low, plane_high = object_bounds(_object(primitive="plane"))
    torus_low, torus_high = object_bounds(_object(primitive="torus"))

    assert _close(plane_low, (-1.0, -1.0, 0.0))
    assert _close(plane_high, (1.0, 1.0, 0.0))
    assert _close(torus_low, (-1.25, -1.25, -0.25))
    assert _close(torus_high, (1.25, 1.25, 0.25))


def test_a_mesh_uses_its_own_vertices_not_a_primitive() -> None:
    mesh = SceneMesh(
        vertices=((0.0, 0.0, 0.0), (2.0, 4.0, 6.0), (1.0, 1.0, 1.0)), faces=((0, 1, 2),)
    )

    low, high = object_bounds(_object(primitive=None, mesh=mesh))

    assert _close(low, (0.0, 0.0, 0.0))
    assert _close(high, (2.0, 4.0, 6.0))


def test_touching_bounds_are_zero_apart_and_gaps_are_euclidean() -> None:
    a = ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    touching = ((1.0, 0.0, 0.0), (2.0, 1.0, 1.0))
    diagonal = ((4.0, 5.0, 1.0), (6.0, 7.0, 2.0))

    assert bounds_distance(a, touching) == 0.0
    assert bounds_distance(a, a) == 0.0
    assert bounds_distance(a, diagonal) == pytest.approx(5.0)
    assert bounds_distance(diagonal, a) == pytest.approx(5.0)


def _box(x: float) -> tuple[tuple[float, float, float], ...]:
    return ((x, 0.0, 0.0), (x + 1.0, 1.0, 1.0))


def test_connectivity_follows_chains_and_ignores_far_pieces() -> None:
    # 0-1-2 chain with 0.5 gaps, plus a lone box far away and a pair apart from it.
    pieces = [_box(0.0), _box(1.5), _box(3.0), _box(50.0), _box(100.0), _box(101.0)]

    assert largest_connected_component(pieces, 0.5) == 3
    assert largest_connected_component(pieces, 0.1) == 2
    assert largest_connected_component(pieces, 1000.0) == 6


def test_an_empty_scene_has_no_component() -> None:
    assert largest_connected_component([], 1.0) == 0


@pytest.mark.parametrize("gap", [-1.0, math.inf, math.nan])
def test_an_unusable_gap_is_refused(gap: float) -> None:
    with pytest.raises(ValueError, match="max_gap"):
        largest_connected_component([_box(0.0)], gap)
