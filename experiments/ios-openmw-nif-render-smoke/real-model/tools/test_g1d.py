import importlib.util,json,struct,tempfile,unittest
from pathlib import Path
import assets,fixtures,provenance
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
if __name__=='__main__':unittest.main()
