from __future__ import annotations

import bpy

from . import preferences, properties
from .operators import MODULES as OPERATOR_MODULES
from .ui import MODULES as UI_MODULES


def _iter_non_ui_classes():
    yield from properties.CLASSES
    yield from preferences.CLASSES
    for module in OPERATOR_MODULES:
        yield from module.CLASSES


def _iter_ui_classes():
    for module in UI_MODULES:
        yield from module.CLASSES


def _unregister_handlers() -> None:
    for module in UI_MODULES:
        unregister_handlers = getattr(module, "unregister_handlers", None)
        if callable(unregister_handlers):
            unregister_handlers()


def _register_handlers() -> None:
    for module in UI_MODULES:
        register_handlers = getattr(module, "register_handlers", None)
        if callable(register_handlers):
            register_handlers()


def _prepare_ui_register() -> None:
    for module in UI_MODULES:
        prepare_register = getattr(module, "prepare_register", None)
        if callable(prepare_register):
            prepare_register()


def _safe_unregister_classes(classes) -> None:
    for cls in reversed(tuple(classes)):
        try:
            bpy.utils.unregister_class(cls)
        except RuntimeError:
            registered_cls = getattr(bpy.types, cls.__name__, None)
            if registered_cls is None or registered_cls is cls:
                continue
            try:
                bpy.utils.unregister_class(registered_cls)
            except RuntimeError:
                continue


def _cleanup_partial_registration() -> None:
    _unregister_handlers()
    properties.unregister_properties()
    _safe_unregister_classes(_iter_ui_classes())
    _safe_unregister_classes(_iter_non_ui_classes())


def register() -> None:
    _cleanup_partial_registration()
    registered_classes = []
    try:
        for cls in _iter_non_ui_classes():
            bpy.utils.register_class(cls)
            registered_classes.append(cls)
        properties.register_properties()
        _prepare_ui_register()
        for cls in _iter_ui_classes():
            bpy.utils.register_class(cls)
            registered_classes.append(cls)
        _register_handlers()
    except Exception:
        _unregister_handlers()
        properties.unregister_properties()
        _safe_unregister_classes(registered_classes)
        raise


def unregister() -> None:
    _unregister_handlers()
    properties.unregister_properties()
    _safe_unregister_classes(_iter_ui_classes())
    _safe_unregister_classes(_iter_non_ui_classes())
