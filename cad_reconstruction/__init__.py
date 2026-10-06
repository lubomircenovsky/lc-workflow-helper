from __future__ import annotations


def non_ui_classes():
    from . import operators, problem_select, protection, result_actions, settings, uv_prep

    return (*settings.CLASSES, *operators.CLASSES, *result_actions.CLASSES,
            *uv_prep.CLASSES, *protection.CLASSES, *problem_select.CLASSES)


def register_properties():
    from . import settings

    settings.register_properties()


def unregister_properties():
    from . import result_actions, settings, status_overlay

    result_actions.cancel_active_cleanup()
    status_overlay.clear()
    settings.unregister_properties()
