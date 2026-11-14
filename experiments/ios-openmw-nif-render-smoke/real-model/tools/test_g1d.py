import importlib.util,json,struct,tempfile,unittest,hashlib
from pathlib import Path
import assets,fixtures,provenance,nif_layout
class Contracts(unittest.TestCase):
    def test_deterministic_authored_inputs(self):
        self.assertEqual(fixtures.inputs(),fixtures.inputs())
        self.assertEqual(set(fixtures.inputs()),{'Morrowind.esm','Morrowind.bsa'})
        self.assertIn(b'DDS ',fixtures.inputs()['Morrowind.bsa'])
        self.assertIn(b'NiTriShapeData',fixtures.inputs()['Morrowind.bsa'])
    def test_negative_variants_are_distinct(self):
        import hashlib
        values=[hashlib.sha256(fixtures.inputs(m)['Morrowind.bsa']).hexdigest() for m in ('good','cycle','transform','index','path','missing','image')]
        self.assertEqual(len(set(values)),7)
    def test_export_cannot_write_repository_or_installation(self):
        for output in (assets.REPO/'private',Path('A:/SteamLibrary/steamapps/common/Morrowind/Data Files/test')):
            with self.assertRaises(ValueError):assets.export(Path('A:/SteamLibrary/steamapps/common/Morrowind'),output)
    def test_native_reader_and_engine_components_are_real(self):
        code=(assets.ROOT/'src/StaticModel.cpp').read_text()
        for token in ('reader.parse(vfs.get(key))','source->mTransform.toMatrix()','correctTexturePath','GenericObjectCache','USE_OSGPLUGIN(dds)','original->getColor','mTriangles','mChildren'):
            self.assertIn(token,code)
        self.assertNotIn('G1A::copyGeometry',code)
    def test_public_app_has_no_asset_copy_step(self):
        code=(assets.ROOT/'device/CMakeLists.txt').read_text()
        self.assertNotIn('Morrowind.bsa',code);self.assertNotIn('Data Files',code)
        main=(assets.ROOT/'device/src/main.mm').read_text()
        self.assertIn('Documents(@"Model")',main);self.assertIn('Private asset hash mismatch',main)
    def test_provenance_binds_source_hashes(self):
        with tempfile.TemporaryDirectory() as t:
            provenance.prepare(Path(t));d=json.loads((Path(t)/'g1d-build.json').read_text())
            self.assertIn('src/StaticModel.cpp',d['source_sha256_lf'])
    def test_camera_uses_world_bounds_and_orbit(self):
        s=(assets.ROOT/'device/src/OSGScene.hpp').read_text()
        self.assertIn('ComputeBoundsVisitor',s);self.assertIn('std::cos(time * .22)',s)
        self.assertNotIn('DrawElementsUShort',s)

# Executable offline tests of self-authored records and bounded diagnostics.
# OSG state assertions live in model_check.cpp and require the native harness.


def model(mode='good'):
    with tempfile.TemporaryDirectory() as temp:
        archive = Path(temp) / 'authored.bsa'
        archive.write_bytes(fixtures.inputs(mode)['Morrowind.bsa'])
        name, offset, size = next(x for x in assets.old.bsa_entries(archive) if x[0] == assets.MODEL)
        with archive.open('rb') as stream:
            stream.seek(offset)
            return stream.read(size)


class PropertyLayouts(unittest.TestCase):
    def test_emission_only_ignore_is_a_native_negative_case(self):
        records = nif_layout.inspect(model('light-emission-ignore'))['records']
        prop = next(r for r in records if r['type'] == 'NiVertexColorProperty')
        self.assertEqual((prop['vertex_mode'], prop['lighting_mode']), (0, 0))
        self.assertIn(prop['index'], records[2]['properties'])
        self.assertEqual(fixtures.NEGATIVE['light-emission-ignore'], 'Emission-only lighting')
        # Preserve the rug's supported (SrcIgnore, EmiAmbDif) combination.
        rug = nif_layout.inspect(model('rug-properties'))['records']
        prop = next(r for r in rug if r['type'] == 'NiVertexColorProperty')
        self.assertEqual((prop['vertex_mode'], prop['lighting_mode']), (0, 1))

    def test_all_positive_layouts_consumed_exactly(self):
        for mode in fixtures.POSITIVE:
            with self.subTest(mode=mode):
                result = nif_layout.inspect(model(mode))
                self.assertTrue(result['complete_byte_consumption'])
                self.assertEqual(result['record_count'], len(result['records']))
                self.assertEqual(result['roots'], [0])

    def test_rug_property_values_without_original_bytes(self):
        result = nif_layout.inspect(model('rug-properties'))
        records = {r['type']: r for r in result['records']}
        self.assertEqual(records['NiVertexColorProperty']['vertex_mode'], 0)
        self.assertEqual(records['NiVertexColorProperty']['lighting_mode'], 1)
        self.assertFalse(records['NiTriShapeData']['vertex_colors'])
        self.assertEqual(records['NiTexturingProperty']['apply_mode'], 3)
        self.assertEqual(records['NiTexturingProperty']['textures'][0]['filter'], 2)

    def test_parent_inheritance_and_child_override_records(self):
        inherited = nif_layout.inspect(model('inheritance'))['records']
        self.assertEqual(len(inherited[0]['properties']), 6)
        self.assertEqual(inherited[2]['properties'], [])
        overridden = nif_layout.inspect(model('override'))['records']
        parent, child = overridden[0]['properties'], overridden[2]['properties']
        self.assertTrue(set(parent).isdisjoint(child))
        self.assertEqual({overridden[x]['type'] for x in child},
                         {'NiVertexColorProperty', 'NiZBufferProperty', 'NiStencilProperty', 'NiAlphaProperty'})

    def test_every_truncation_is_rejected(self):
        data = model('rug-properties')
        for length in range(len(data)):
            with self.subTest(length=length), self.assertRaises(ValueError):
                nif_layout.inspect(data[:length])

    def test_trailing_data_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Trailing'):
            nif_layout.inspect(model() + b'extra')

    def test_unknown_record_type_fails_not_skips(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported diagnostic layout'):
            nif_layout.inspect(model().replace(b'NiTriShapeData', b'NiUnknownType'))

    def test_embedded_type_name_is_not_a_record(self):
        data = model().replace(fixtures.g.string('Root'), fixtures.g.string('NiVertexColorProperty'))
        result = nif_layout.inspect(data)
        self.assertEqual(result['record_count'], 7)
        self.assertNotIn('NiVertexColorProperty', [r['type'] for r in result['records']])

    def test_root_and_property_references_checked(self):
        data = model('rug-properties')
        with self.assertRaisesRegex(ValueError, 'reference'):
            nif_layout.inspect(data[:-4] + struct.pack('<i', 9999))
        needle = fixtures.g.av('Quad', (4, 6, 7))
        self.assertIn(needle, data)
        with self.assertRaisesRegex(ValueError, 'reference'):
            nif_layout.inspect(data.replace(needle, fixtures.g.av('Quad', (4, 6, 9999))))

    def test_invalid_geometry_and_nonfinite_values_rejected(self):
        for mode in ('index', 'transform', 'vertex-nan', 'material-invalid'):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                nif_layout.inspect(model(mode))

    def test_cases_are_distinct_and_reproducible(self):
        cases = (*fixtures.POSITIVE, *fixtures.NEGATIVE)
        values = [hashlib.sha256(model(m)).hexdigest() for m in cases if m not in ('missing', 'image')]
        self.assertEqual(len(values), len(set(values)))
        for mode in cases:
            self.assertEqual(fixtures.inputs(mode), fixtures.inputs(mode))

    def test_unknown_fixture_mode_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Unknown fixture'):
            fixtures.inputs('typo')

    def test_native_runner_retains_state_and_diagnostic_assertions(self):
        code = (assets.ROOT / 'tests/model_check.cpp').read_text()
        for assertion in ('Depth flags/child override mismatch', 'Inherited culling mismatch',
                          'Alpha blend inheritance/override mismatch', 'Sibling property isolation mismatch',
                          'Material/vertex-color selection mismatch', 'Genuine filter mismatch'):
            self.assertIn(assertion, code)
        runner = (assets.ROOT / 'tools/run_cases.py').read_text()
        self.assertIn('fixtures.NEGATIVE[mode] not in r.stderr', runner)
        self.assertIn('NiDitherProperty#7', runner)

    def test_native_runner_rejects_failure_status_with_matching_counts(self):
        from unittest.mock import patch
        from types import SimpleNamespace
        import run_cases
        fake = SimpleNamespace(returncode=0, stderr='', stdout=json.dumps(
            {'status': 'FAIL', 'vertices': 4, 'triangles': 2, 'shapes': 1}))
        with patch.object(run_cases.subprocess, 'run', return_value=fake):
            with self.assertRaisesRegex(ValueError, 'status/counts'):
                run_cases.run(Path('unused-native-harness'))


if __name__ == '__main__':
    unittest.main()
