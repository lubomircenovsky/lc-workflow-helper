"""Pure bake pass and GLB contract tests; no Blender installation required."""
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from babylon_export.core import compute_bake_passes, baked_material_name, safe_batch_name, inspect_glb, verify_glb
from constants import PANEL_ORDER_DEFAULT, normalize_panel_order
from babylon_export.exporters import is_gltf_exporter, selected_exporter, exporter_filepath
from babylon_export.reporting import issue_outcome, last_operation_status


class OperationReportingTests(unittest.TestCase):
    def test_severity_precedence(self):
        for levels, expected in (([], 'OK'), (['INFO'], 'OK'),
                                 (['WARNING'], 'WARNING'),
                                 (['WARNING', 'ERROR'], 'ERROR')):
            with self.subTest(levels=levels):
                self.assertEqual(issue_outcome([SimpleNamespace(level=v) for v in levels]), expected)

    def test_historical_outcomes_and_collection_identity(self):
        collection = SimpleNamespace(name='Target')
        state = SimpleNamespace(last_operation='CHECK', last_outcome='OK',
                                report_collection=collection, last_report='Export failed!')
        # The report string never controls the outcome.
        self.assertEqual(last_operation_status(state, collection),
                         ('ok', 'Last Check: no issues reported'))
        for outcome, icon in (('WARNING', 'warning'), ('ERROR', 'error'),
                              ('CANCELLED', 'cancelled'), ('UNKNOWN', 'idle')):
            state.last_outcome = outcome
            self.assertEqual(last_operation_status(state, collection)[0], icon)
        state.last_outcome = 'OK'
        other = SimpleNamespace(name='Other')
        self.assertEqual(last_operation_status(state, other), ('info', 'Last report: Target'))
        state.report_collection = None
        self.assertEqual(last_operation_status(state, other),
                         ('info', 'Last report: collection unavailable'))


def glb(document, binary=b'PNG!'):
    chunk = json.dumps(document).encode()
    chunk += b' ' * (-len(chunk) % 4)
    binary += b'\x00' * (-len(binary) % 4)
    return (struct.pack('<4sII', b'glTF', 2, 28 + len(chunk) + len(binary)) +
            struct.pack('<II', len(chunk), 0x4E4F534A) + chunk +
            struct.pack('<II', len(binary), 0x004E4942) + binary)


def document():
    return {'asset': {'version': '2.0'}, 'materials': [{'name': 'Paint_baked'}],
            'meshes': [{'primitives': [{'attributes': {'POSITION': 0, 'TEXCOORD_0': 1}, 'material': 0,
                         'extensions': {'KHR_materials_variants': {'mappings': [
                             {'material': 0, 'variants': [0]}]}}}]}],
            'extensionsUsed': ['KHR_materials_variants'],
            'extensions': {'KHR_materials_variants': {'variants': [{'name': 'Paint'}]}},
            'bufferViews': [{'buffer': 0, 'byteOffset': 0, 'byteLength': 4}],
            'images': [{'bufferView': 0, 'mimeType': 'image/png'}]}


class BakePlanTests(unittest.TestCase):
    def test_defaults_and_only_changed_objects(self):
        defaults = {('a', 0): 'wood', ('a', 1): 'steel', ('b', 0): 'wood'}
        passes = compute_bake_passes(defaults, {0: {('a', 0): 'blue'}}, [0])
        self.assertEqual(passes[0].to_bake, {('a', 'wood'), ('a', 'steel'), ('b', 'wood')})
        self.assertEqual(passes[1].objects, {'a'})
        self.assertEqual(passes[1].assignments, {('a', 0): 'blue', ('a', 1): 'steel'})
        self.assertEqual(passes[1].to_bake, {('a', 'blue')})

    def test_same_material_once_per_object(self):
        passes = compute_bake_passes({('a', 0): 'wood', ('a', 1): 'wood'},
                                     {0: {('a', 0): 'blue'}, 1: {('a', 1): 'blue'}}, [0, 1])
        self.assertEqual(len(passes), 2)
        self.assertEqual(passes[0].to_bake, {('a', 'wood')})

    def test_variant_starts_from_default_not_previous_variant(self):
        passes = compute_bake_passes({('a', 0): 'wood', ('a', 1): 'steel'},
                                     {0: {('a', 0): 'blue'}, 1: {('a', 1): 'red'}}, [0, 1])
        self.assertEqual(passes[2].assignments[('a', 0)], 'wood')

    def test_no_material_produces_no_bake(self):
        self.assertEqual(compute_bake_passes({('a', 0): None}, {}, [0]), [])

    def test_variant_material_on_empty_slot(self):
        passes = compute_bake_passes({('a', 0): None}, {0: {('a', 0): 'blue'}}, [0])
        self.assertEqual(passes[0].variant_idx, 0)

    def test_default_material_used_by_variant_needs_no_extra_pass(self):
        passes = compute_bake_passes({('a', 0): 'wood', ('a', 1): 'steel'},
                                     {0: {('a', 0): 'steel'}}, [0])
        self.assertEqual(len(passes), 1)

    def test_input_not_mutated(self):
        defaults, overrides = {('a', 0): 'wood'}, {0: {('a', 0): 'blue'}}
        compute_bake_passes(defaults, overrides, [0])
        self.assertEqual(defaults, {('a', 0): 'wood'})
        self.assertEqual(overrides, {0: {('a', 0): 'blue'}})

    def test_shared_material_names(self):
        self.assertEqual(baked_material_name('Paint', 'Cube'), 'Paint_baked')
        self.assertEqual(baked_material_name('Paint', 'Cube', shared=True), 'Paint__Cube_baked')

    def test_batch_file_name(self):
        self.assertEqual(safe_batch_name('Door: a/b? '), 'Door_ a_b_')
        self.assertEqual(safe_batch_name(' . '), 'Bake')

    def test_old_panel_order_gets_new_panel(self):
        for old in ('scene_info,kalibra_tools,materials',
                    'kalibra_tools,babylon_export,materials', 'babylon_export,kalibra_tools'):
            result = normalize_panel_order(old)
            self.assertEqual(result.count('project_specific_tools'), 1)
            self.assertNotIn('babylon_export', result)
            self.assertNotIn('kalibra_tools', result)
            self.assertEqual(set(result), set(PANEL_ORDER_DEFAULT))
        self.assertEqual(normalize_panel_order('materials,kalibra_tools,babylon_export,uv')[:3],
                         ('materials', 'project_specific_tools', 'uv'))

    def test_selected_pairs_only_with_full_assignments(self):
        defaults = {('door', 0): 'wood', ('door', 1): 'plain', ('glass', 0): 'glass'}
        passes = compute_bake_passes(defaults, {0: {('door', 0): 'blue'}}, [0],
                                     selected_materials={'wood', 'blue'})
        self.assertEqual(passes[0].to_bake, {('door', 'wood')})
        self.assertEqual(passes[0].assignments, {('door', 0): 'wood', ('door', 1): 'plain'})
        self.assertEqual(passes[1].to_bake, {('door', 'blue')})

    def test_no_checked_materials_means_no_passes(self):
        self.assertEqual(compute_bake_passes({('door', 0): 'wood'}, {}, [], selected_materials=set()), [])

    def test_unselected_variant_does_not_schedule_an_object(self):
        passes = compute_bake_passes({('door', 0): 'wood'}, {0: {('door', 0): 'plain'}}, [0],
                                     selected_materials={'wood'})
        self.assertEqual(len(passes), 1)


class ExporterTests(unittest.TestCase):
    def exporter(self, identifier, name='', path=''):
        return SimpleNamespace(name=name, filepath=path, export_properties=SimpleNamespace(
            bl_rna=SimpleNamespace(identifier=identifier), filepath=''))

    def test_unnamed_gltf_is_detected_by_type(self):
        gltf = self.exporter('EXPORT_SCENE_OT_gltf')
        self.assertTrue(is_gltf_exporter(gltf))
        fake = self.exporter('EXPORT_SCENE_OT_fbx', name='glTF 2.0')
        self.assertFalse(is_gltf_exporter(fake))
        collection = SimpleNamespace(exporters=[fake, gltf], lcw_babylon_export=SimpleNamespace(exporter_name='1'))
        self.assertIs(selected_exporter(collection), gltf)
        collection.lcw_babylon_export.exporter_name = '0'
        self.assertIsNone(selected_exporter(collection))

    def test_first_gltf_and_empty_path(self):
        gltf = self.exporter('EXPORT_SCENE_OT_gltf')
        collection = SimpleNamespace(exporters=[gltf], lcw_babylon_export=SimpleNamespace(exporter_name=''))
        self.assertIs(selected_exporter(collection), gltf)
        self.assertEqual(exporter_filepath(gltf), '')
        gltf.export_properties.filepath = 'model.glb'
        self.assertEqual(exporter_filepath(gltf), 'model.glb')


class VerifyGLBTests(unittest.TestCase):
    def test_file_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'minimal.glb'
            path.write_bytes(glb(document()))
            self.assertTrue(verify_glb(path, expected_variants=1)['ok'])

    def test_minimal_glb(self):
        report = inspect_glb(glb(document()), expected_variants=1, require_variants=True)
        self.assertTrue(report['ok'], report['errors'])
        self.assertEqual((report['variants'], report['images'], report['mappings']), (1, 1, 1))

    def test_second_uv_rejected(self):
        doc = document()
        doc['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_1'] = 2
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_missing_uv_rejected(self):
        doc = document()
        del doc['meshes'][0]['primitives'][0]['attributes']['TEXCOORD_0']
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_draco_rejected(self):
        doc = document()
        doc['extensionsUsed'].append('KHR_draco_mesh_compression')
        self.assertIn('GLB obsahuje kompresi Draco.', inspect_glb(glb(doc))['errors'])

    def test_undeclared_draco_rejected(self):
        doc = document()
        doc['meshes'][0]['primitives'][0]['extensions']['KHR_draco_mesh_compression'] = {}
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_variant_count_rejected(self):
        self.assertFalse(inspect_glb(glb(document()), expected_variants=2)['ok'])

    def test_invalid_variant_mapping_rejected(self):
        doc = document()
        doc['meshes'][0]['primitives'][0]['extensions']['KHR_materials_variants']['mappings'][0]['variants'] = [3]
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_source_material_rejected(self):
        doc = document()
        doc['materials'][0]['name'] = 'Paint'
        self.assertFalse(inspect_glb(glb(doc), expected_baked_materials={'Paint_baked'})['ok'])

    def test_plain_materials_allowed_with_selected_baked_names(self):
        doc = document()
        doc['materials'].append({'name': 'Glass'})
        primitive = doc['meshes'][0]['primitives'][0]
        primitive['extensions']['KHR_materials_variants']['mappings'].append({'material': 1, 'variants': [0]})
        report = inspect_glb(glb(doc), expected_baked_materials={'Paint_baked'})
        self.assertTrue(report['ok'], report['errors'])

    def test_missing_selected_baked_material_rejected(self):
        doc = document()
        doc['materials'][0]['name'] = 'Paint'
        self.assertFalse(inspect_glb(glb(doc), expected_baked_materials={'Paint_baked'})['ok'])

    def test_all_unselected_without_images(self):
        doc = document()
        doc['materials'][0]['name'] = 'Plain'
        doc['images'] = []
        self.assertTrue(inspect_glb(glb(doc), expected_baked_materials=set())['ok'])

    def test_selected_name_still_requires_suffix(self):
        doc = document()
        doc['materials'][0]['name'] = 'Paint'
        self.assertFalse(inspect_glb(glb(doc), expected_baked_materials={'Paint'})['ok'])

    def test_invalid_material_index_rejected(self):
        doc = document()
        doc['meshes'][0]['primitives'][0]['material'] = 4
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_missing_variant_extension_rejected(self):
        doc = document()
        doc.pop('extensions')
        self.assertFalse(inspect_glb(glb(doc), require_variants=True)['ok'])

    def test_broken_glb_framing_rejected(self):
        data = glb(document())
        for broken in (b'', data[:-1], b'NOPE' + data[4:], data[:4] + struct.pack('<I', 1) + data[8:]):
            with self.subTest(data=broken[:12]), self.assertRaises(ValueError):
                inspect_glb(broken)

    def test_image_bounds_rejected(self):
        doc = document()
        doc['bufferViews'][0]['byteLength'] = 500
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_image_mime_rejected(self):
        doc = document()
        doc['images'][0]['mimeType'] = 'text/plain'
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_external_images_rejected(self):
        doc = document()
        doc['images'] = [{'uri': 'outside.png'}]
        self.assertFalse(inspect_glb(glb(doc))['ok'])

    def test_absent_images_rejected(self):
        doc = document()
        doc['images'] = []
        self.assertFalse(inspect_glb(glb(doc), expected_baked_materials={'Paint_baked'})['ok'])


if __name__ == '__main__':
    unittest.main()
