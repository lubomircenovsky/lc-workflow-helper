"""Stable, serializable operation choices for the CAD worker."""

DEFAULTS = {
    "circular_holes": True,
    "perimeter_loops": True,
    "arcs": True,
    "outer_cylinders": True,
    "background_cleanup": True,
    "straight_walls": True,
}


def normalize(options=None):
    result = dict(DEFAULTS)
    if options is not None:
        unknown = set(options) - set(result)
        if unknown:
            raise ValueError(f"Unknown CAD operations: {sorted(unknown)}")
        for name, value in options.items():
            if not isinstance(value, bool):
                raise ValueError(f"CAD operation {name} must be a boolean")
            result[name] = value
    if not any(result.values()):
        raise ValueError("Enable at least one CAD operation")
    return result


def decision(category, operations, preserve_curve_segmentation=False):
    if category == "circular_hole":
        if preserve_curve_segmentation:
            return "PERIMETER_ONLY" if operations["perimeter_loops"] else "DISABLED"
        if operations["circular_holes"]:
            return "REBUILD"
        return "PERIMETER_ONLY" if operations["perimeter_loops"] else "DISABLED"
    if category in {"concave_arc", "convex_arc"}:
        return "REBUILD" if operations["arcs"] and not preserve_curve_segmentation else "DISABLED"
    if category == "outer_cylinder":
        return "REBUILD" if operations["outer_cylinders"] and not preserve_curve_segmentation else "DISABLED"
    return "DISABLED"
