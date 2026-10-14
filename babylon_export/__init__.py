"""Babylon export; the optional bake adapter is deliberately lazy.

No bpy import at module level: pure modules of this package are unit-tested
outside Blender.
"""


def _stop_bake_on_load(_dummy):
    # The scene of a running bake is about to be replaced; only global
    # SimpleBake preferences still need to be put back.
    from .bake import abandon_active_job
    abandon_active_job(restore_data=False)


def non_ui_classes():
    from . import operators, settings
    return (*settings.CLASSES, *operators.CLASSES)


def register_properties():
    import bpy
    from .settings import register_properties as register
    register()
    _stop_bake_on_load._bpy_persistent = True  # keep the handler across file loads
    if _stop_bake_on_load not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_stop_bake_on_load)


def unregister_properties():
    import bpy
    from .bake import abandon_active_job
    from .settings import unregister_properties as unregister
    if _stop_bake_on_load in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_stop_bake_on_load)
    abandon_active_job(restore_data=True)
    unregister()
