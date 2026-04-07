from __future__ import annotations

import bpy

from . import preferences, properties
from .operators import MODULES as OPERATOR_MODULES
from .ui import MODULES as UI_MODULES


def _iter_classes():
    yield from properties.CLASSES
    yield from preferences.CLASSES
    for module in OPERATOR_MODULES:
        yield from module.CLASSES
    for module in UI_MODULES:
        yield from module.CLASSES


def register() -> None:
    for cls in _iter_classes():
        bpy.utils.register_class(cls)
    properties.register_properties()


def unregister() -> None:
    properties.unregister_properties()
    for cls in reversed(tuple(_iter_classes())):
        bpy.utils.unregister_class(cls)
