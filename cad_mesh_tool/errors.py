"""Typed CAD worker errors.

Recovery and optional cleanup stages decide by exception type, never by the
wording of a message. Both classes derive from ValueError so existing callers
that catch ValueError keep their behaviour; messages are unchanged because
reports and the panel explain failures from their text.
"""


class GeometricConflict(ValueError):
    """A candidate is geometrically unsafe; recovery may retry with fewer features."""


class StageRejected(ValueError):
    """An optional cleanup stage was rejected; the last validated mesh is kept."""
