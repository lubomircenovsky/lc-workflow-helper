"""Phase 2 boundary. No SimpleBake code or module-level imports."""
import addon_utils
import bpy


def availability():
    """Return (module name, version) only for an enabled SimpleBake addon."""
    enabled = bpy.context.preferences.addons
    for module in addon_utils.modules():
        info = getattr(module, 'bl_info', {})
        if ('simplebake' in module.__name__.lower() or info.get('name', '').lower() == 'simplebake'):
            if module.__name__ in enabled:
                return module.__name__, tuple(info.get('version', ()))
    return None, ()


def bake_properties(scene):
    return getattr(scene, 'SimpleBake_Props', None) if availability()[0] else None


def configure_simplebake(settings, bake_pass, objects):
    """Phase 2: load preset, force PBR/per-material/existing UV, set object list."""
    raise NotImplementedError("Pečení přes SimpleBake – fáze 2")


def start_bake():
    """Phase 2: invoke the asynchronous foreground bake with window context."""
    raise NotImplementedError("Pečení přes SimpleBake – fáze 2")


def poll_bake():
    """Phase 2: completion, cancellation and timeout handling."""
    raise NotImplementedError("Pečení přes SimpleBake – fáze 2")


def cancel_bake():
    """Phase 2: request halt; wait for poll_bake before restoring originals."""
    raise NotImplementedError("Pečení přes SimpleBake – fáze 2")


def collect_bake_images(bake_pass):
    """Phase 2: return {(object, material): {channel: Image}} using SB tags."""
    raise NotImplementedError("Pečení přes SimpleBake – fáze 2")
