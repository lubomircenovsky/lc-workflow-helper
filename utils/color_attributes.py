from __future__ import annotations

import bpy


def ensure_color_attribute(
    mesh: bpy.types.Mesh,
    attribute_name: str,
    domain: str = "CORNER",
    data_type: str = "BYTE_COLOR",
    replace_existing: bool = False,
):
    existing = mesh.color_attributes.get(attribute_name)
    if existing and replace_existing:
        mesh.color_attributes.remove(existing)
        existing = None

    if existing is None:
        existing = mesh.color_attributes.new(attribute_name, data_type, domain)

    mesh.color_attributes.active_color = existing
    return existing


def blend_rgba(existing: tuple[float, float, float, float], new: tuple[float, float, float, float], mode: str) -> tuple[float, float, float, float]:
    if mode == "ADD":
        return tuple(min(existing[index] + new[index], 1.0) for index in range(4))
    if mode == "MULTIPLY":
        return tuple(existing[index] * new[index] for index in range(4))
    if mode == "OVERLAY":
        rgb = tuple(existing[index] if existing[index] > 0.5 else new[index] for index in range(3))
        return rgb + (existing[3],)
    return new
