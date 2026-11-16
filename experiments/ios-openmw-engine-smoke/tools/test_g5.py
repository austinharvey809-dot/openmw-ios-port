"""Focused integration contracts; native behavior is tested by two CPU suites."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import struct
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import prepare_engine
import prepare_frontend
import verify_lua
import run_engine_cases

ROOT=prepare_engine.ROOT;REPO=prepare_engine.REPO


class EngineProjection(unittest.TestCase):
    def test_only_two_unprovided_application_apis_are_excluded(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp);prepare_engine.prepare(output)
            report=json.loads((output/'engine-projection.json').read_text())
            self.assertEqual([x['signature'] for x in report['omitted_definitions']],json.loads((ROOT/'engine-lock.json').read_text())['excluded_definitions'])
            text=(output/'esmstore.cpp').read_text();original=(REPO/'apps/openmw/mwworld/esmstore.cpp').read_text()
            for signature in ('    void ESMStore::load(', '    void ESMStore::setUp(', '    void ESMStore::rebuildIdsIndex('):
                a,b=prepare_engine.function_span(original,signature);c,d=prepare_engine.function_span(text,signature)
                self.assertEqual(original[a:b],text[c:d])
            self.assertNotIn('ESMStore::loadESM4(',text);self.assertNotIn('ESMStore::getSpellList(',text)

    def test_lua_helpers_retain_genuine_bodies(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp);prepare_engine.prepare(output);text=(output/'readonly.cpp').read_text()
            original=(REPO/'components/lua/luastate.cpp').read_text()
            for signature in ('    sol::table makeReadOnly(', '    std::string toString(', '    std::string Internal::formatCastingError(', '    sol::protected_function_result LuaState::throwIfError('):
                a,b=prepare_engine.function_span(original,signature);self.assertIn(original[a:b],text)

    def test_tampered_source_rejected(self):
        original=Path.read_bytes
        def corrupt(path):
            data=original(path)
            return data+b'\n// drift' if path==REPO/'apps/openmw/mwworld/esmstore.cpp' else data
        with tempfile.TemporaryDirectory() as temp,patch.object(Path,'read_bytes',corrupt):
            with self.assertRaisesRegex(ValueError,'source provenance mismatch'):prepare_engine.prepare(Path(temp))

    def test_ambiguous_function_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous'):prepare_engine.function_span('void f(){} void f(){}','void f(')

    def test_reference_merge_is_accepted_body(self):
        source=(prepare_frontend.G4/'src/WorldIndex.cpp').read_text()
        a,b=prepare_engine.function_span(source,'std::vector<ESM::CellRef> WorldIndex::references(')
        self.assertIn('mMovedRefs',source[a:b]);self.assertIn('mLeasedRefs',source[a:b])
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp);defaults=output/'defaults';defaults.write_text('namespace G4Defaults {}')
            prepare_frontend.prepare(output,defaults)
            generated=(output/'References.cpp').read_text()
            self.assertIn(source[a:b].replace('WorldIndex::','EngineIndex::').replace('G4','G5'),generated)

    def test_frontend_preserves_identity_context_guard_and_current_shader_gate(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp);defaults=output/'defaults';defaults.write_text('namespace G4Defaults {}')
            prepare_frontend.prepare(output,defaults)
            scene=(output/'OSGScene.hpp').read_text();main=(output/'main.mm').read_text()
            self.assertLess(scene.index('initializeGLCapabilities(window'),scene.index('configureLabels(*state)'))
            self.assertIn('requireCurrentGLContext',scene)
            self.assertIn('!linked||!linked->isLinked()',scene)
            self.assertIn('g5-startup.json',main);self.assertIn('g5-render.json',main)
            self.assertIn('MWWorld::ESMStore',main);self.assertIn('Documents(@"Model")',main)
            self.assertNotIn('G5-loose-priority',(output/'world_check.cpp').read_text())


class Cases(unittest.TestCase):
    def test_fixture_is_authored_and_contains_book_data(self):
        source=run_engine_cases.inputs('good')
        self.assertIn(b'g5_book',source['Morrowind.esm'])
        self.assertTrue(any(tag==b'BOOK' for tag,_ in run_engine_cases.fixtures.records(source['Morrowind.esm'])))

    def test_negative_lua_payloads_differ_in_relevant_field(self):
        good=run_engine_cases.inputs('lua')['Authored.esp']
        bad=run_engine_cases.inputs('lua-invalid')['Authored.esp']
        self.assertNotEqual(good,bad)
        self.assertIn(b'LUAI',bad);self.assertIn(b'LUAD',good)

    def test_native_runner_retains_failures(self):
        row=run_engine_cases.runner.capture([str(ROOT/'no-such-executable')],1)
        self.assertTrue(row['spawn_error']);self.assertIsNone(row['exit'])
        self.assertIn('stderr_base64',row);self.assertFalse(row['timeout'])

    def test_missing_sdk_cannot_pass_package(self):
        spec=importlib.util.spec_from_file_location('g5_package_test',ROOT/'tools/package.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with self.assertRaisesRegex(ValueError,'SDK is mandatory'):module.validate({},None,None)

    def symbol_fixture(self,undefined=False,engine=True):
        # Authored symbol-table fixture for the parser only, not a valid device
        # executable or evidence of Apple compilation/packaging.
        names=['_osgdb_'+n for n in ('dds','tga','bmp','png','jpeg','osg','osg2')]
        names+=['_wrapper_serializer_library_osg','_wrapper_serializer_BufferIndexBinding']
        if engine:names+=['__ZN7MWWorld8ESMStore4loadE','__ZN7MWWorld8ESMStore5setUpEv']
        strings=b'\0';symbols=b''
        for name in names:
            symbols+=struct.pack('<IBBHQ',len(strings),1 if undefined else 15,0 if undefined else 1,0,0)
            strings+=name.encode()+b'\0'
        header=struct.pack('<8I',0xfeedfacf,0x0100000c,0,2,1,24,0,0)
        command=struct.pack('<6I',2,24,56,len(names),56+len(symbols),len(strings))
        return header+command+symbols+strings

    def package_module(self):
        spec=importlib.util.spec_from_file_location('g5_symbol_package_test',ROOT/'tools/package.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

    def test_registration_gate_requires_defined_symbols(self):
        module=self.package_module()
        self.assertTrue(module.registrations(self.symbol_fixture())['engine_store_load_and_setup'])
        with self.assertRaisesRegex(ValueError,'registrations absent'):module.registrations(self.symbol_fixture(undefined=True))

    def test_g4_registrations_alone_cannot_prove_g5_store_linkage(self):
        with self.assertRaisesRegex(ValueError,'ESMStore implementation absent'):
            self.package_module().registrations(self.symbol_fixture(engine=False))

    def test_inherited_manifest_cannot_forge_accepted_source_identity(self):
        module=self.package_module()
        with self.assertRaisesRegex(ValueError,'Accepted G4 exact source provenance differs'):
            module.provenance.accepted_contract({'source_sha256_lf':{}})

    def test_pins_match_official_lua_archive_contract(self):
        lua=json.loads((ROOT/'dependencies.json').read_text())['lua']
        self.assertEqual(lua['sha256'],'2335b6c582a52654f94612bf10d2f4672805d05329aa6568b1d8cd9e5c6fb8e6')
        self.assertTrue(lua['url'].startswith('https://www.lua.org/'))

    def test_editable_manifest_cannot_replace_authenticated_lua_archive(self):
        lock=json.loads((ROOT/'dependencies.json').read_text())['lua']
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp);source=output/'lua-5.4.9';source.mkdir()
            (output/'lua-source.json').write_text(json.dumps({'archive':lock,'files':{}}))
            (output/'lua-5.4.9.tar.gz').write_bytes(b'forged archive')
            with self.assertRaisesRegex(ValueError,'Lua archive changed'):verify_lua.verify(source)


class Workflow(unittest.TestCase):
    def test_private_artifacts_cannot_enter_published_source_scope(self):
        spec=importlib.util.spec_from_file_location('g5_preserve_test',ROOT/'tools/preserve.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        self.assertTrue(module.allowed_source('experiments/ios-openmw-engine-smoke/src/EngineIndex.cpp'))
        self.assertTrue(module.allowed_source('.github/workflows/ios-openmw-engine-device.yml'))
        for path in ('experiments/ios-openmw-engine-smoke/artifacts/secret.json',
                     'experiments/ios-openmw-engine-smoke/private/profile.json',
                     'experiments/ios-openmw-engine-smoke/data/Morrowind.esm',
                     '.github/workflows/ios-openmw-engine-device.yml.backup'):
            self.assertFalse(module.allowed_source(path),path)

    def test_lua_native_contract_requires_upstream_ios_platform_flag(self):
        spec=importlib.util.spec_from_file_location('g5_preflight_test',ROOT/'tools/native_preflight.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temp:
            sdk=Path(temp)/'authored-sdk-contract'
            flags=['clang','-std=c99','-arch','arm64','-isysroot',str(sdk),'-DLUA_USE_IOS','-c','authored-loslib.c']
            module.consumer_contract({'file':'authored-loslib.c','arguments':flags},sdk)
            with self.assertRaisesRegex(ValueError,'genuine iOS platform configuration'):
                module.consumer_contract({'file':'authored-loslib.c','arguments':[a for a in flags if a!='-DLUA_USE_IOS']},sdk)
            with self.assertRaisesRegex(ValueError,'genuine iOS platform configuration'):
                module.consumer_contract({'file':'authored-loslib.c','arguments':flags+['-ULUA_USE_IOS']},sdk)

    def test_manual_only_and_retains_accepted_gates(self):
        text=(REPO/'.github/workflows/ios-openmw-engine-device.yml').read_text()
        self.assertIn('  workflow_dispatch:',text)
        self.assertNotIn('  push:',text);self.assertNotIn('  pull_request:',text)
        for name in ('g4-startup-capabilities','openmw-g4-osg-registration-check','g1d-native-tests.log',
                     'g2-native-tests.log','g3-native-tests.log','g4-native-tests.log','g5-native-tests.log',
                     'g5-early-compile.json','IOSOpenMWEngine-unsigned.ipa'):
            self.assertIn(name,text)
        self.assertIn("['checks']==29",text)
        self.assertLess(text.index('Early genuine G5 engine and UIKit Apple consumer gate'),
                        text.index('Verify native dependency archives, compile new OSG targets and link registrations'))

    def test_accepted_g4_files_have_not_changed(self):
        lock=json.loads((ROOT/'engine-lock.json').read_text())
        for name,want in lock['sources'].items():
            self.assertEqual(hashlib.sha256((REPO/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest(),want,name)


if __name__=='__main__':unittest.main()
