"""Short English CAD status text; full technical evidence stays in run files."""

from __future__ import annotations

import re
import textwrap


def lines(message, width=43):
    return textwrap.wrap(message, width=width, break_long_words=True) or [""]


def _count_label(count, singular, plural):
    return f"{count} {singular if count == 1 else plural}"


def analysis_issue(message):
    source = message.split(": ", 1)[0] if ": " in message else ""
    source = source if source not in {"Preflight", "CAD"} else ""
    if "CAD source must be a closed manifold mesh" in message:
        counts = {kind: int(count) for kind, count in re.findall(
            r"(boundary|nonmanifold|winding|duplicates)=(\d+)", message)}
        names = {"boundary": ("open edge", "open edges"),
                 "nonmanifold": ("non-manifold edge", "non-manifold edges"),
                 "winding": ("flipped edge", "flipped edges"),
                 "duplicates": ("duplicate face", "duplicate faces")}
        detail = ", ".join(_count_label(counts[kind], *names[kind])
                           for kind in ("boundary", "nonmanifold", "winding", "duplicates")
                           if counts.get(kind, 0))
        advice = ("Guarded mode or repair." if counts.get("nonmanifold") and not any(
            counts.get(kind) for kind in ("boundary", "winding", "duplicates"))
            else "Repair mesh first.")
        return f"{source or 'Mesh'}: {detail}. {advice}"
    tests = (
        ("unapplied modifiers", "Apply modifiers first."),
        ("empty mesh", "Mesh has no faces."),
        ("linked source is read-only", "Linked mesh cannot be edited."),
        ("singular transform", "Object transform has zero scale."),
        ("Switch to Object Mode", "Switch to Object Mode."),
        ("Enable at least one", "Enable at least one operation."),
        ("Choose input and output", "Choose both collections."),
        ("No eligible source", "Select mesh objects first."),
        ("Save the .blend", "Save .blend or use an absolute Run Folder."),
    )
    for needle, short in tests:
        if needle in message:
            return f"{source}: {short}" if source else short
    return message.split(": ", 1)[-1]


def analysis_note(message):
    source = message.split(": ", 1)[0] if ": " in message else ""
    if "negative scale" in message:
        return f"{source}: Negative scale. Check direction."
    counts = re.findall(r"(\d+) (boundary|non-manifold|degenerate)", message)
    names = {"boundary": ("open edge", "open edges"),
             "non-manifold": ("non-manifold edge", "non-manifold edges"),
             "degenerate": ("flat face", "flat faces")}
    found = [_count_label(int(count), *names[kind]) for count, kind in counts if int(count)]
    return f"{source}: " + ", ".join(found) if found else f"{source}: Check mesh topology."


def result_brief(row):
    if row.status in {"PENDING", "RUNNING"}:
        return "Waiting." if row.status == "PENDING" else "Working."
    if row.status == "PASS":
        return "Mesh ready. Check shape."
    if row.status == "REVIEW":
        if row.preserve_nonmanifold:
            return "Partial mesh. Bad edges kept. Review."
        if "sharp edge(s) changed" in row.reason.lower():
            return "Sharp edges changed. Review shading."
        if "face directions conflict" in row.reason.lower():
            return "Face directions conflict. Check local geometry."
        return "Partial mesh. Check skipped areas."
    reason = row.technical_reason or row.reason
    if "CAD source must be a closed manifold mesh" in reason:
        counts = {kind: int(count) for kind, count in re.findall(
            r"(boundary|nonmanifold|winding|duplicates)=(\d+)", reason)}
        if counts.get("boundary"):
            return "Open mesh edges. Repair source."
        if counts.get("winding") or counts.get("duplicates"):
            return "Mesh topology invalid. Repair source."
        if counts.get("nonmanifold"):
            return "Non-manifold edges. Use guarded mode."
    tests = (
        ("No selected operation produced", "No safe change. No output."),
        ("No safe feature could be reconstructed", "No safe area found. No output."),
        ("UNRESOLVED_PERIMETER", "No room for support loop."),
        ("Region boundary branches", "Planar edge path unclear."),
        ("non-manifold", "Bad mesh edges. Use guarded mode or repair."),
        ("boundary", "Open mesh edges. Repair source."),
        ("unapplied modifiers", "Apply modifiers first."),
        ("Source fingerprint changed", "Source changed during run. No output."),
        ("Import/integrity failure", "Import failed. See Run Files."),
    )
    for needle, short in tests:
        if needle.lower() in reason.lower():
            return short
    return f"Failed at {row.stage or 'worker'}. See Run Files."
