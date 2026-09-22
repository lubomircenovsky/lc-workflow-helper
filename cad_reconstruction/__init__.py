from __future__ import annotations


def non_ui_classes():
    from . import operators, settings

    return (*settings.CLASSES, *operators.CLASSES)


def register_properties():
    from . import settings

    settings.register_properties()


def unregister_properties():
    from . import settings, status_overlay

    status_overlay.clear()
    settings.unregister_properties()
