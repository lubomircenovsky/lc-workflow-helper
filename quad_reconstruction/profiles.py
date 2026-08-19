from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReconstructionProfile:
    identifier: str
    label: str
    protect_materials: bool
    protect_uv: bool
    protect_seams: bool
    protect_sharp_edges: bool
    description: str


PROFILES = {
    profile.identifier: profile
    for profile in (
        ReconstructionProfile(
            "STRICT",
            "Strict",
            True,
            True,
            True,
            True,
            "Preserve protected data and leave ambiguous triangles unresolved.",
        ),
        ReconstructionProfile(
            "BALANCED",
            "Balanced",
            True,
            False,
            False,
            False,
            "Keep materials hard while allowing reported UV, seam and sharp relaxations.",
        ),
        ReconstructionProfile(
            "AGGRESSIVE",
            "Aggressive",
            False,
            False,
            False,
            False,
            "Maximize hard-valid quad coverage and report every attribute relaxation.",
        ),
        ReconstructionProfile(
            "ANALYZE_ONLY",
            "Analyze Only",
            True,
            True,
            True,
            True,
            "Audit hypotheses without creating output mesh data.",
        ),
    )
}


def profile_defaults(identifier: str) -> ReconstructionProfile:
    return PROFILES.get(identifier, PROFILES["STRICT"])
