"""Babylon export; the optional bake adapter is deliberately lazy."""


def non_ui_classes():
    from . import operators, settings
    return (*settings.CLASSES, *operators.CLASSES)


def register_properties():
    from .settings import register_properties as register
    register()


def unregister_properties():
    from .settings import unregister_properties as unregister
    unregister()
