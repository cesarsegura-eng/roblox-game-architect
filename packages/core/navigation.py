"""Interpret bounded navigation evidence consistently across the MCP boundary."""

from .worldbuilding import SceneRecipe


def navigation_status(
    recipe: SceneRecipe, path_count: object, waypoint_count: object, connected: object
) -> str:
    """Reject contradictory evidence before deriving a public validation status."""
    expected_paths = sum(item.role == "path" for item in recipe.objects)
    if (
        type(path_count) is not int
        or path_count != expected_paths
        or type(waypoint_count) is not int
        or not 0 <= waypoint_count <= 512
        or type(connected) is not bool
    ):
        raise ValueError("Navigation counts or connectivity do not match the recipe")
    if path_count < 2:
        if connected or waypoint_count != 0:
            raise ValueError("Navigation evidence claims a query without a route")
        return "structure_only"
    if connected:
        if waypoint_count < min(path_count - 1, 512):
            raise ValueError("Navigation pass lacks evidence for every route leg")
        return "navigation_pass"
    if path_count == 2 and waypoint_count != 0:
        raise ValueError("Failed single-leg navigation cannot contain successful waypoints")
    return "navigation_failed"
