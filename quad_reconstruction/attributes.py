from __future__ import annotations


DIAGNOSTIC_ATTRIBUTES = (
    "AIQ_UnresolvedTriangle",
    "AIQ_LowConfidence",
    "AIQ_UVRelaxed",
    "AIQ_SeamRelaxed",
    "AIQ_SharpRelaxed",
    "AIQ_MaterialRelaxed",
    "AIQ_HighWarp",
    "AIQ_HighCost",
    "AIQ_AttributeRelaxed",
)


def problem_face_indices(mesh) -> tuple[int, ...]:
    indices = set()
    for name in DIAGNOSTIC_ATTRIBUTES:
        layer = mesh.attributes.get(name)
        if layer is None or layer.domain != "FACE" or layer.data_type != "BOOLEAN":
            continue
        indices.update(index for index, value in enumerate(layer.data) if value.value)
    return tuple(sorted(indices))
