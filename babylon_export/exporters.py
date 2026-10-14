"""Identify Collection Exporters by operator RNA, independent of their label."""
MISSING_EXPORT_PATH = (
    'Exportér nemá výstupní cestu. Nastavte ji v Collection Exporteru kolekce.'
)


def is_gltf_exporter(exporter):
    props = exporter.export_properties
    return props is not None and props.bl_rna.identifier == 'EXPORT_SCENE_OT_gltf'


def exporter_filepath(exporter):
    if exporter is None:
        return ''
    return exporter.filepath or getattr(exporter.export_properties, 'filepath', '')


def selected_exporter(collection, settings=None):
    settings = settings or collection.lcw_babylon_export
    first = next((e for e in collection.exporters if is_gltf_exporter(e)), None)
    if first is None:
        return None
    if hasattr(settings, 'is_property_set') and not settings.is_property_set('exporter_name'):
        return first
    value = settings.exporter_name
    if not value:
        return first
    if value.isdigit() and int(value) < len(collection.exporters):
        exporter = collection.exporters[int(value)]
        return exporter if is_gltf_exporter(exporter) else None
    return None
