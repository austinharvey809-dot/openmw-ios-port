import ast,hashlib,importlib.util,json,struct,tempfile,unittest
from pathlib import Path
import bridge,fixtures,inspect_cells,layout,provenance

def mesh(mode):
    data=fixtures.inputs(mode)['Morrowind.bsa']
    size,count=struct.unpack_from('<II',data,4);start=12+size+8*count
    for i in range(count):
        ni=12+12*count+struct.unpack_from('<I',data,12+8*count+4*i)[0]
        end=data.index(b'\0',ni)
        if data[ni:end].lower().endswith(b'.nif'):
            n,off=struct.unpack_from('<II',data,12+8*i)
            return data[start+off:start+off+n]
    raise ValueError('Missing authored NIF')

class InteriorContracts(unittest.TestCase):
    def test_authored_inputs_are_deterministic(self):
        for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
            with self.subTest(mode=mode):self.assertEqual(fixtures.inputs(mode),fixtures.inputs(mode))
    def test_all_cases_distinct(self):
        values=[hashlib.sha256(b''.join(fixtures.inputs(m).values())).hexdigest() for m in (*fixtures.POSITIVE,*fixtures.NEGATIVE)]
        self.assertEqual(len(values),len(set(values)))
    def test_genuine_esm_record_framing_and_reference_inventory(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);fixtures.write(root)
            objects,cells=inspect_cells.scan(root/'Morrowind.esm')
            self.assertEqual(len(cells),1);self.assertEqual(cells[0][0],fixtures.CELL)
            self.assertEqual(len(cells[0][2]),8)
            self.assertEqual({v['type'] for v in objects.values()},{'STAT','MISC','DOOR','ACTI','CONT','LIGH'})
            self.assertEqual(len(objects),8)
    def test_original_style_materials_have_normals(self):
        records=layout.inspect(mesh('good'))['records']
        data=next(r for r in records if r['type']=='NiTriShapeData')
        self.assertTrue(data['normals']);self.assertEqual(data['triangles'],2)
        self.assertFalse(next(r for r in layout.inspect(mesh('missing-normal'))['records'] if r['type']=='NiTriShapeData')['normals'])
    def test_collision_and_particle_branches_are_separately_counted(self):
        for mode in ('collision','particles'):
            nodes,c,e=inspect_cells.visible(layout.inspect(mesh(mode)))
            self.assertEqual(len(nodes),1);self.assertEqual((c,e),(1,0) if mode=='collision' else (0,1))
    def test_deleted_reference_is_preserved_as_a_record_not_dropped_by_encoder(self):
        with tempfile.TemporaryDirectory() as d:
            fixtures.write(Path(d),'deleted-reference')
            _,cells=inspect_cells.scan(Path(d)/'Morrowind.esm')
            self.assertEqual(len(cells[0][2]),9);self.assertIn(b'DELE',cells[0][2][-1])
    def test_bounded_esm_diagnostic_rejects_truncated_and_oversized(self):
        data=fixtures.inputs()['Morrowind.esm']
        for bad in (data[:-1],data[:6],b'CELL'+struct.pack('<III',0xffffffff,0,0)):
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'bad.esm';p.write_bytes(bad)
                with self.assertRaises(ValueError):list(inspect_cells.records(p))
    def test_negative_light_fixture_retains_signed_light_flag(self):
        with tempfile.TemporaryDirectory() as d:
            fixtures.write(Path(d),'negative-light');objects,_=inspect_cells.scan(Path(d)/'Morrowind.esm')
            self.assertEqual(struct.unpack_from('<i',objects['lamp']['light'],20)[0]&4,4)
    def test_scale_negative_case_is_nan_because_genuine_reader_clamps_finite_values(self):
        self.assertIn(struct.pack('<f',float('nan')),fixtures.inputs('bad-scale')['Morrowind.esm'])
    def test_bridge_is_deterministic_and_does_not_touch_accepted_source(self):
        before={n:hashlib.sha256((bridge.REPO/n).read_bytes()).hexdigest() for n in json.loads((bridge.ROOT/'baseline-lock.json').read_text())['source_sha256_lf']}
        with tempfile.TemporaryDirectory() as a,tempfile.TemporaryDirectory() as b:
            bridge.generate(Path(a));bridge.generate(Path(b))
            code=(Path(a)/'MeshBridge.cpp').read_text();self.assertEqual(code,(Path(b)/'MeshBridge.cpp').read_text())
            for term in ('reader.parse(vfs.get(key))','resources.images','RC_RootCollisionNode','RC_NiBSParticleNode','AttachLight','Decoded texture budget exceeded'):
                self.assertIn(term,code)
            self.assertNotIn('esm.open(',code)
        self.assertTrue(all(hashlib.sha256((bridge.REPO/n).read_bytes()).hexdigest()==v for n,v in before.items()))
    def test_changed_bridge_anchor_fails(self):
        with self.assertRaises(ValueError):bridge.replace('no marker','expected','new')
    def test_public_source_manifest_has_no_artifacts_or_private_files(self):
        sources=provenance.sources()
        self.assertIn('src/Interior.cpp',sources);self.assertIn('tools/bridge.py',sources)
        self.assertTrue(all('artifacts/' not in n and 'private/' not in n for n in sources))
        self.assertFalse(any(n.endswith(('.esm','.bsa','.nif','.dds','.ipa')) for n in sources))
    def test_prepared_manifest_binds_own_sources_and_workflow(self):
        with tempfile.TemporaryDirectory() as d:
            report=provenance.prepare(Path(d));self.assertEqual(report['source_sha256_lf'],provenance.sources())
            self.assertTrue(report['workflow_sha256_lf']);self.assertTrue((Path(d)/'G2Expected.hpp').is_file())
    def test_native_source_uses_real_cell_and_shared_templates(self):
        code=(bridge.ROOT/'src/Interior.cpp').read_text()
        for term in ('ESM::Cell::getNextRef','cell.load(reader,deleted,false)','reference.mPos','r.mScale',
                     'models.emplace','loadMesh(resources,b.model)','instance->addChild(owned.scene)','owned.lightOffset*matrix'):
            self.assertIn(term,code)
    def test_navigation_and_lighting_are_not_swap_only_success_gates(self):
        code=(bridge.ROOT/'device/src/main.mm').read_text();scene=(bridge.ROOT/'device/src/OSGScene.hpp').read_text()
        for term in ('leftThumbstick','rightThumbstick','navigation.turn','inputs_unchanged','particle_branches_omitted','UNVERIFIED'):
            self.assertIn(term,code)
        self.assertIn('osg_NormalMatrix',scene);self.assertIn('lightPosition',scene);self.assertNotIn('std::cos(time * .22)',scene)
    def test_existing_data_container_and_private_import_are_preserved(self):
        code=(bridge.ROOT/'device/CMakeLists.txt').read_text()
        self.assertIn('org.openmw.experiments.real-model',code);self.assertNotIn('Morrowind.bsa',code)
        main=(bridge.ROOT/'device/src/main.mm').read_text();self.assertIn('Documents(@"Model")',main)
        self.assertNotIn('manifest[@"object_id"]',main)
    def test_workflow_is_manual_and_contains_strict_native_gates(self):
        code=(bridge.REPO/'.github/workflows/ios-openmw-interior-device.yml').read_text()
        self.assertIn('workflow_dispatch:',code);self.assertNotIn('\n  push:',code)
        for term in ('openmw-interior-check','--no-tests=error','g2-configured-audit.json','IOSOpenMWInterior-unsigned.ipa','if: always()'):
            self.assertIn(term,code)
    def test_packager_exact_inventory_remains_mandatory(self):
        code=(bridge.ROOT/'tools/package.py').read_text()
        for term in ('Exact public inventory mismatch','provenance.sources()','p.graph','validate(reopened','Reopened IPA differs','org.openmw.experiments.real-model'):
            self.assertIn(term,code)
    def test_false_native_pass_is_rejected(self):
        import run_cases
        from unittest.mock import patch
        from types import SimpleNamespace
        with patch.object(run_cases.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"status":"FAIL","instances":6,"triangles":12}',stderr='')):
            with self.assertRaisesRegex(ValueError,'Native gate failed'):run_cases.run(Path('not-executed'))
    def test_every_negative_case_requires_a_specific_diagnostic(self):
        import run_cases
        self.assertTrue(all(text.strip() for text in fixtures.NEGATIVE.values()))
        for mode,expected in fixtures.NEGATIVE.items():
            with self.subTest(mode=mode):
                run_cases.check_rejection(mode,1,'context: '+expected)
                for code,message in ((1,'Unrelated ordinary failure'),(0,expected),(-11,expected)):
                    with self.assertRaisesRegex(ValueError,'Wrong native rejection'):
                        run_cases.check_rejection(mode,code,message)
    def test_empty_negative_contract_fails_closed(self):
        import run_cases
        from unittest.mock import patch
        with patch.dict(fixtures.NEGATIVE,{'missing-mesh':''}):
            with self.assertRaisesRegex(ValueError,'Empty native rejection'):
                run_cases.check_rejection('missing-mesh',1,'anything')
            with self.assertRaisesRegex(ValueError,'Empty native rejection'):
                run_cases.run(Path('must-not-be-executed'))
    def test_g1d_suite_uses_the_existing_g2_provider(self):
        code=(bridge.REPO/'.github/workflows/ios-openmw-interior-device.yml').read_text()
        self.assertIn('--target openmw-interior-check openmw-real-model-check',code)
        self.assertIn('ctest --test-dir "$RUNNER_TEMP/g2-host-build/provider" -R \'^g1d-\' --no-tests=error',code)
        self.assertIn('-p test_g1d.py',code)
        self.assertNotIn('cmake -S "$G1D"',code)
    def test_startup_cpu_work_is_separated_from_main_thread_attachment(self):
        code=(bridge.ROOT/'device/src/main.mm').read_text()
        cpu=code[code.index('static G2::Environment PrepareGeometry'):code.index('// Main-thread, one-shot')]
        attachment=code[code.index('G2::Environment LoadGeometry()'):code.index('// The extracted v2')]
        self.assertIn('!NSThread.isMainThread',cpu);self.assertNotIn('Evidence[',cpu)
        self.assertIn('G2::load(path)',cpu);self.assertIn('FileSHA(',cpu)
        self.assertNotIn('G2::load(',attachment);self.assertNotIn('FileSHA(',attachment)
        self.assertIn('NSThread.isMainThread',attachment);self.assertIn('std::move(*PreparedAttachment)',attachment)
        self.assertIn('dispatch_get_global_queue(QOS_CLASS_UTILITY',code)
        self.assertIn('dispatch_get_main_queue()',code)
        self.assertIn('if(Evidence!=session)return',code)
        self.assertIn('if(self->sceneActive)[self activate]',code)
        self.assertIn('sceneActive=false;',code)
    def test_all_python_sources_parse(self):
        for p in (bridge.ROOT/'tools').glob('*.py'):ast.parse(p.read_text(),filename=str(p))

    def configured_fixture(self,root,standard='-std=c++20',sdk_name='iPhoneOS.sdk',arch='arm64'):
        generated=root/'g2-generated';generated.mkdir();include=root/'headers';sdk=root/sdk_name;sdk.mkdir()
        for name in ('OpenThreads/Config','OpenThreads/Version','osg/Config','osg/GL','osg/Version'):
            p=include/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('#define OSG_GLES3_AVAILABLE\n')
        (generated/'osg-include.txt').write_text(str(include)+'\n')
        commands=[]
        for source in (bridge.ROOT/'src/Interior.cpp',generated/'MeshBridge.cpp',bridge.ROOT/'device/src/main.mm'):
            args=['clang++','-x','objective-c++' if str(source).endswith('.mm') else 'c++',*([standard] if standard else []),
                  '-arch',arch,'-isysroot',str(sdk),'-DBT_USE_DOUBLE_PRECISION','-I'+str(include)]
            commands.append({'file':str(source),'arguments':args})
        commands.append({'file':str(root/'pinned/src/osg/State.cpp'),'arguments':[]})
        (root/'compile_commands.json').write_text(json.dumps(commands));return sdk,commands

    def test_configured_accepts_cxx20_and_apple_objcxx2a(self):
        for spelling in ('-std=c++20','-std=c++2a'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);sdk,commands=self.configured_fixture(root,spelling)
                self.assertEqual(provenance.configured(root,sdk)['osg_providers'],1)
    def test_configured_rejects_wrong_or_substring_standards(self):
        for spelling in ('','-std=c++17','-std=c++23','-std=gnu++20','-Dnote=-std=c++20'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);sdk,commands=self.configured_fixture(root,spelling)
                with self.assertRaisesRegex(ValueError,'standard'):provenance.configured(root,sdk)
    def test_configured_rejects_host_sdk_or_architecture(self):
        for sdk_name,arch in (('MacOSX.sdk','arm64'),('iPhoneOS.sdk','x86_64')):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);sdk,commands=self.configured_fixture(root,sdk_name=sdk_name,arch=arch)
                with self.assertRaises(ValueError):provenance.configured(root,sdk)
    def test_configured_rejects_duplicate_provider_and_missing_header(self):
        for defect in ('provider','header','comment','conflicting-std'):
            with tempfile.TemporaryDirectory() as temp:
                root=Path(temp);sdk,commands=self.configured_fixture(root)
                if defect=='provider':commands.append(commands[-1])
                elif defect=='header':(root/'headers/OpenThreads/Config').unlink()
                elif defect=='comment':(root/'headers/osg/GL').write_text('// #define OSG_GLES3_AVAILABLE\n')
                else:commands[0]['arguments'].append('-std=c++17')
                (root/'compile_commands.json').write_text(json.dumps(commands))
                with self.assertRaises(ValueError):provenance.configured(root,sdk)

if __name__=='__main__':unittest.main()
