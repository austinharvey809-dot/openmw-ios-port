"""Offline tests exercise fixture/packaging policy; native parsing and GPU gates are separate."""
import copy
import json
import os
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import fixtures
import resources as r
import package_textured
import run_texture
from support import ROOT, REPO, DEVICE, base, package, host, load

# Exercise the existing real Mach-O, selected-SDK and IPA policy tests against
# this app's private instance of the complete original validator.
saved = {name: sys.modules.get(name) for name in ('provenance', 'package_device')}
try:
    sys.modules.update(provenance=base, package_device=package)
    old_tests = load('_g1c_original_package_tests', DEVICE / 'tools/test_g1b.py')
finally:
    for name, value in saved.items():
        if value is None:
            del sys.modules[name]
        else:
            sys.modules[name] = value


class DevicePolicyTests(old_tests.BinaryAndPackageTests):
    pass


class FixtureTests(unittest.TestCase):
    def test_exact_deterministic_fixture_inventory(self):
        self.assertEqual(fixtures.audit(), fixtures.manifest())
        self.assertEqual(len(fixtures.fixture_bytes()), 10)
        self.assertEqual(len(fixtures.cases()), 7)
        fixtures.generate()  # Idempotent; never replaces changed bytes.

    def test_genuine_esm_bsa_payloads_and_reference(self):
        values = fixtures.fixture_bytes()
        self.assertTrue(values['textured.nif'].startswith(b'NetImmerse File Format, Version 4.0.0.2\n'))
        self.assertIn(b'NiTexturingProperty', values['textured.nif'])
        self.assertIn(b'NiSourceTexture', values['textured.nif'])
        self.assertIn(fixtures.TEXTURE_REFERENCE.encode(), values['textured.nif'])
        self.assertIn(values['textured.nif'], values['textured.bsa'])
        self.assertIn(values['pattern.tga'], values['textured.bsa'])
        self.assertIn(b'TeXtUrEd.NIF\0', values['textured.esm'])

    def test_tga_pixels_orientation_and_material_expectations(self):
        image = fixtures.tga()
        header = struct.unpack('<BBBHHBHHHHBB', image[:18])
        self.assertEqual((header[2], header[8], header[9], header[10], header[11]), (2, 8, 8, 32, 8))
        rgba = b''.join(bytes((image[i+2], image[i+1], image[i], image[i+3])) for i in range(18, len(image), 4))
        self.assertEqual(rgba, fixtures.pixels())
        self.assertEqual(fixtures.digest(rgba), fixtures.manifest()['rgba_sha256'])
        self.assertEqual(list(rgba[:4]), [255, 32, 32, 255])

    def test_extra_missing_modified_or_directory_fixture_rejected(self):
        for mode in ('extra', 'missing', 'modified', 'directory', 'manifest'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / 'data'
                shutil.copytree(fixtures.DATA, target)
                if mode == 'extra':
                    (target / 'unexpected.txt').write_bytes(b'x')
                elif mode == 'manifest':
                    (target / 'fixture-manifest.json').write_text('{}')
                else:
                    path = target / 'pattern.tga'
                    path.unlink()
                    if mode == 'modified':
                        path.write_bytes(b'changed')
                    elif mode == 'directory':
                        path.mkdir()
                with self.assertRaises(ValueError):
                    fixtures.audit(target)

    def test_negative_archives_have_explicit_stage_hashes(self):
        cases = fixtures.cases()
        self.assertEqual(cases[0]['diagnostic'], '')
        self.assertTrue(all(c['diagnostic'] for c in cases[1:]))
        self.assertNotEqual(cases[0]['nif_sha256'], cases[3]['nif_sha256'])
        self.assertNotEqual(cases[0]['texture_sha256'], cases[-1]['texture_sha256'])


class ResourceTests(unittest.TestCase):
    def test_actual_decoder_source_must_match_lock_not_only_reference_checkout(self):
        osg = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
        original = osg / 'src/osgPlugins/tga/ReaderWriterTGA.cpp'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'src/osgPlugins/tga/ReaderWriterTGA.cpp'
            path.parent.mkdir(parents=True)
            path.write_bytes(original.read_bytes())
            r.checked_decoder(root)
            path.write_bytes(path.read_bytes() + b'// changed')
            with self.assertRaisesRegex(ValueError, 'TGA decoder'):
                r.checked_decoder(root)
            path.unlink()
            with self.assertRaises(ValueError):
                r.checked_decoder(root)

    def test_completed_sources_and_resource_decoder_lock(self):
        osg = Path(os.environ.get('OPENMW_ESM_OSG_SOURCE', REPO.parent / 'OpenSceneGraph-pinned'))
        self.assertEqual(r.audit(osg)['g1b_preserved_files'], 19)

    def prepared(self, output):
        (output / 'resources').mkdir(parents=True)
        (output / 'include').mkdir()
        metadata = {'source_commit': 'a'*40, 'geometry_sha256': 'b'*64}
        (output / 'resources/g1b-build.json').write_text(json.dumps(metadata))
        r.extend(output)
        values = base.files(output / 'resources')
        return values, json.loads(values['g1b-build.json'])

    def test_prepared_extra_inventory_hashes_and_compiled_expectations(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            values, metadata = self.prepared(output)
            self.assertEqual(set(metadata['resources_sha256']), set(values) - {'g1b-build.json'})
            self.assertTrue(all(host.sha(values[n]) == sha for n, sha in metadata['resources_sha256'].items()))
            with patch.object(r, 'original_prepared', return_value=(values, metadata)):
                self.assertEqual(r.prepared_resources(output)[1]['g1c']['fixture_manifest'], fixtures.manifest())
            expected = (output / 'include/G1CExpectations.hpp').read_text()
            for key in ('textured.nif', 'pattern.tga'):
                self.assertIn(fixtures.manifest()['files'][key]['sha256'], expected)
            self.assertIn(host.sha(values['g1b-build.json']), (output / 'include/G1BExpectations.hpp').read_text())

    def test_extra_prepared_resource_and_stale_source_rejected(self):
        for mode in ('extra', 'missing', 'bytes', 'source', 'closure'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                output = Path(directory)
                values, metadata = self.prepared(output)
                if mode == 'extra':
                    values['TexturedFixtures/unexpected'] = b'x'
                elif mode == 'missing':
                    del values['TexturedFixtures/pattern.tga']
                elif mode == 'bytes':
                    values['TexturedFixtures/pattern.tga'] = b'changed'
                elif mode == 'source':
                    metadata['g1c']['source_sha256_lf']['injected'] = 'c'*64
                else:
                    metadata['g1c']['source_closure']['tga_sha256_lf'] = 'd'*64
                with patch.object(r, 'original_prepared', return_value=(values, metadata)), self.assertRaises(ValueError):
                    r.prepared_resources(output)

    def test_configured_extra_consumers_require_actual_headers_standards_and_single_decoder(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            canonical = (build / 'osg/include').as_posix()
            entries = [{'file': '/repo/' + name, 'arguments': ['clang++', '-I'+canonical, '-std=c++2a', '-c', name]}
                       for name in ('TextureAdapter.cpp', 'components/misc/resourcehelpers.cpp', 'texture_check.cpp',
                                    'osgPlugins/tga/ReaderWriterTGA.cpp')]
            for mode in ('valid', 'missing', 'duplicate', 'headers', 'standard', 'extra-plugin'):
                values = copy.deepcopy(entries)
                if mode == 'missing': values.pop()
                elif mode == 'duplicate': values.append(copy.deepcopy(values[0]))
                elif mode == 'headers': values[0]['arguments'].remove('-I'+canonical)
                elif mode == 'standard': values[0]['arguments'][2] = '-std=c++17'
                elif mode == 'extra-plugin': values.append({'file':'/repo/osgPlugins/png/ReaderWriterPNG.cpp'})
                (build / 'compile_commands.json').write_text(json.dumps(values))
                with self.subTest(mode=mode), patch.object(base, 'configured', return_value={}), \
                        patch.object(r, 'checked_decoder'):
                    if mode == 'valid':
                        self.assertEqual(len(r.configured(build, Path('.'))['textured_consumers']), 4)
                    else:
                        with self.assertRaises(ValueError): r.configured(build, Path('.'))


class SourceTests(unittest.TestCase):
    def test_provider_matches_verified_recipe_with_only_project_and_relative_path_adaptations(self):
        expected = (DEVICE / 'cmake/provider.cmake').read_text()
        expected = expected.replace('project(OpenMWG1B ', 'project(OpenMWG1C ')
        expected = expected.replace('"${CMAKE_CURRENT_SOURCE_DIR}/../../.."', '"${CMAKE_CURRENT_SOURCE_DIR}/../../../.."')
        expected = expected.replace('"${CMAKE_CURRENT_SOURCE_DIR}/baseline/tools/',
            '"${G1B_REPO}/experiments/ios-openmw-nif-render-smoke/device/baseline/tools/')
        expected = expected.replace('"${CMAKE_CURRENT_SOURCE_DIR}/cmake/precision.cmake"',
            '"${G1B_REPO}/experiments/ios-openmw-nif-render-smoke/device/cmake/precision.cmake"')
        self.assertEqual((ROOT / 'device/cmake/provider.cmake').read_text(), expected)

    def test_single_device_provider_and_generated_headers(self):
        cmake = (ROOT / 'device/CMakeLists.txt').read_text()
        provider = (ROOT / 'device/cmake/provider.cmake').read_text()
        self.assertEqual(provider.count('add_subdirectory("${OSG_SOURCE}"'), 1)
        self.assertIn('g1c-tga g1c-texture', cmake)
        self.assertIn('BEFORE PUBLIC "$<BUILD_INTERFACE:${_generated}>"', cmake)
        self.assertIn('BulletCollision LinearMath osg OpenThreads', cmake)
        self.assertIn('OPENTHREADS_ATOMIC_USE_MUTEX ON', (DEVICE / 'cmake/precision.cmake').read_text())
        self.assertNotIn('G0C_OSG_INCLUDE', cmake)

    def test_real_resource_and_owned_geometry_path(self):
        source = (ROOT / 'src/TextureAdapter.cpp').read_text()
        for call in ('parser.parse(result->vfs.get(key))', 'G1A::copyGeometry(geometry)',
                     'Misc::ResourceHelpers::correctTexturePath', 'Resource::GenericObjectCache',
                     'cache.clear()', 'USE_OSGPLUGIN(tga)', 'decoder->readImage(input',
                     'setVertexAttribArray(6', 'setTextureAttribute(0', 'Texture resource SHA-256 mismatch'):
            self.assertIn(call, source)
        self.assertNotIn('readImageFile', source)

    def test_decoded_uv_material_shader_and_immutable_egl_owner(self):
        scene = (ROOT / 'device/src/OSGScene.hpp').read_text()
        self.assertIn('texture(baseTexture, uv)*color', scene)
        self.assertIn('program->addBindAttribLocation("nifUV", 6)', scene)
        self.assertNotIn('colors->assign', scene)
        self.assertNotIn('DrawElementsUShort', scene)
        main = (ROOT / 'device/src/main.mm').read_text()
        self.assertIn('#include "AngleRenderer.hpp"', main)
        self.assertFalse((ROOT / 'device/src/AngleRenderer.hpp').exists())
        self.assertIn('Snapshot(textures, expected, 11)', main)
        self.assertIn('G1CExpected::PixelsSHA256', main)
        self.assertIn('for (std::size_t i = 0; i < 6;', main)
        self.assertIn('g1c-render.json', main)
        self.assertIn('UNVERIFIED: independent screenshot/export review required', main)
        self.assertIn('@"actual_display_fps"] = NSNull.null', main)

    def test_manual_workflow_has_all_native_and_runtime_gates(self):
        text = r.WORKFLOW.read_text()
        self.assertIn('workflow_dispatch:', text)
        self.assertNotIn('\n  push:', text)
        self.assertNotIn('continue-on-error', text)
        self.assertIn('needs: [host-regressions, angle-device]', text)
        self.assertIn('test_g1c.py', text)
        self.assertIn("-R '^g1a-' --no-tests=error", text)
        self.assertIn("-R '^g1c-' --no-tests=error", text)
        for phase in ('link', 'bundle', 'ipa', 'reopen'):
            self.assertIn('package_textured.py" '+phase, text)
        cmake = (ROOT / 'device/CMakeLists.txt').read_text()
        self.assertIn('$<TARGET_FILE:IOSOpenMWTexturedNif>', cmake)
        self.assertIn('$<TARGET_BUNDLE_DIR:IOSOpenMWTexturedNif>', cmake)
        self.assertIn('if: always()', text)


class RuntimeEvidenceTests(unittest.TestCase):
    def report(self):
        return dict(status='PASS', source_equivalence=True, parser_vfs_cache_released=True,
                    scope='CPU parsing/resource/owned OSG data; no GPU claim', negative_cases=11, cache_hits=1,
                    vertices=3, triangles=1, uv_sets=1, texture_key=fixtures.manifest()['texture_key'],
                    pixels_sha256=fixtures.manifest()['rgba_sha256'], geometry_sha256=base.expected_geometry_hash())

    def test_positive_native_report_contract(self):
        run_texture.validate(self.report(), fixtures.manifest())

    def test_geometry_image_ownership_and_negative_requirements_cannot_be_omitted(self):
        for key in self.report():
            value = self.report()
            del value[key]
            with self.subTest(missing=key), self.assertRaises(ValueError):
                run_texture.validate(value, fixtures.manifest())

    def test_counter_boolean_wrong_resource_and_gpu_claims_rejected(self):
        for key, wrong in (('cache_hits', True), ('pixels_sha256', '0'*64), ('geometry_sha256', '0'*64),
                           ('negative_cases', 10), ('texture_key', 'loose/pattern.tga'),
                           ('scope', 'GPU rendering PASS'), ('source_equivalence', False)):
            value = self.report()
            value[key] = wrong
            with self.subTest(key=key), self.assertRaises(ValueError):
                run_texture.validate(value, fixtures.manifest())

    def test_missing_or_directory_executable_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for product in (Path(directory), Path(directory) / 'missing'):
                with self.assertRaisesRegex(ValueError, 'executable'):
                    run_texture.run(product, Path(directory) / 'evidence')


if __name__ == '__main__':
    unittest.main()
