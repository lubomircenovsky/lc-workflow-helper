from __future__ import annotations

def non_ui_classes():
    from . import operators, settings

    return (*settings.CLASSES, *operators.CLASSES)


def register_properties() -> None:
    from . import settings

    settings.register_properties()


def unregister_properties() -> None:
    from . import settings

    settings.unregister_properties()
