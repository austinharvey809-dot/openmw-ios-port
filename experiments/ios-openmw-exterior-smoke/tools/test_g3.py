import ast,hashlib,importlib.util,json,struct,tempfile,unittest
from pathlib import Path
import paths,fixtures,mesh_bridge,provenance,run_cases

class ExteriorRegression(unittest.TestCase):
    def test_accepted_g2_and_upstream_sources_unchanged(self):self.assertGreater(paths.verify()['unchanged_sources'],35)

    def test_authored_world_is_reproducible_and_distinct(self):
        seen=set()
        for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
            with self.subTest(mode=mode):
                a=fixtures.inputs(mode);self.assertEqual(a,fixtures.inputs(mode));self.assertEqual(set(a),{'Morrowind.esm','Morrowind.bsa'})
                digest=hashlib.sha256(a['Morrowind.esm']+a['Morrowind.bsa']).hexdigest();self.assertNotIn(digest,seen);seen.add(digest)

    def test_authored_land_decodes_height_scale_and_transposed_textures(self):
        import inspect_exterior
        for mode in ('good','sloped'):
            with tempfile.TemporaryDirectory() as temp:
                p=Path(temp)/'data.esm';p.write_bytes(fixtures.inputs(mode)['Morrowind.esm'])
                lands=[dict(s) for kind,s in inspect_exterior.old.records(p) if kind==b'LAND'];self.assertEqual(len(lands),25)
                for fields in lands:
                    x,y=struct.unpack('<ii',fields[b'INTV']);values=inspect_exterior.heights(fields[b'VHGT'])
                    self.assertEqual(values[0],x*512 if mode=='sloped' else 0)
                    self.assertEqual(values[64],(x+1)*512 if mode=='sloped' else 0)
        original=struct.pack('<256H',*range(256));out=inspect_exterior.tile_indices(original)
        self.assertEqual(out[4],16);self.assertEqual(out[16],4);self.assertEqual(sorted(out),list(range(256)))

    def test_truncated_and_nonfinite_land_rejected_by_diagnostic(self):
        import inspect_exterior
        for data in (b'',struct.pack('<f',float('nan'))+bytes(4228)):
            with self.assertRaises(ValueError):inspect_exterior.heights(data)
        with self.assertRaises(ValueError):inspect_exterior.tile_indices(bytes(511))

    def test_multitexture_fixture_requires_a_neighbor_only_material(self):
        import inspect_exterior
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);fixtures.write(root,'multi-texture')
            lands={};ltex=[]
            for kind,subs in inspect_exterior.old.records(root/'Morrowind.esm'):
                fields=dict(subs)
                if kind==b'LAND':lands[struct.unpack('<ii',fields[b'INTV'])]=inspect_exterior.tile_indices(fields[b'VTEX'])
                if kind==b'LTEX':ltex.append(struct.unpack('<I',fields[b'INTV'])[0])
            self.assertEqual(ltex,[0,1,2])
            for (x,y),raster in lands.items():
                if -3<=x<=-1 and -10<=y<=-8:
                    self.assertEqual(set(raster),{1,2});self.assertEqual(raster[0],1);self.assertEqual(raster[8],2)
            self.assertEqual(set(lands[-4,-9]),{3});self.assertEqual(set(lands[-2,-7]),{3})
            images=[data for name,data in fixtures.archive_members((root/'Morrowind.bsa').read_bytes()) if name.lower().endswith(b'.dds')]
            self.assertEqual(len(images),3);self.assertEqual({struct.unpack_from('<H',b,136)[0] for b in images},{0xffff,0xf800,0x001f})

    def test_every_negative_has_specific_contract(self):
        for mode,expected in fixtures.NEGATIVE.items():
            self.assertTrue(expected.strip());run_cases.reject(mode,1,expected)
            for code,text in ((0,expected),(-11,expected),(1,'unrelated error')):
                with self.assertRaises(ValueError):run_cases.reject(mode,code,text)

    def test_generated_material_bridge_retains_source_validations(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp);a=mesh_bridge.generate(path);b=mesh_bridge.generate(path);self.assertEqual(a,b)
            code=(path/'WorldMesh.cpp').read_text()
            for text in ('G3::applyMaterial','G3::inheritProperty','Index out of range','Degenerate triangle','Cyclic/oversized hierarchy','Nonfinite transform','Texture storage budget exceeded','Zero normal','G1D stage='):
                self.assertIn(text,code)
            shader=(path/'MaterialShader.hpp').read_text()
            for name in ('getEmissionColor','getAmbientColor','getDiffuseColor','ColorMode_Emission','struct Material'):self.assertIn(name,shader)
            self.assertNotIn('#include ',shader)

    def test_controller_first_no_movement_overlays_or_trigger_flight(self):
        code=(paths.ROOT/'device/src/main.mm').read_text()
        for forbidden in ('UIStackView','UIPanGestureRecognizer','touchForward','moveDown:','virtual joystick'):
            self.assertNotIn(forbidden,code)
        for text in ('leftThumbstick','rightThumbstick','nav.vertical=0','nav.jump()','self.overlay.hidden=!diagnostics','toggleDiagnostics','navigation.suspend()'):
            self.assertIn(text,code)

    def test_physics_uses_upstream_loader_and_same_terrain_indices(self):
        for name in ('CMakeLists.txt','device/CMakeLists.txt'):
            top=(paths.ROOT/name).read_text();self.assertLess(top.index('set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS}")'),top.index('add_subdirectory'))
        cmake=(paths.ROOT/'common.cmake').read_text()
        for text in ('components/nifbullet/bulletnifloader.cpp','components/resource/bulletshape.cpp','components/sceneutil/material.cpp','components/terrain/buffercache.cpp','BulletDynamics BulletCollision LinearMath','BT_USE_DOUBLE_PRECISION'):
            self.assertIn(text,cmake)
        code=(paths.ROOT/'src/Terrain.cpp').read_text()
        self.assertIn('buffers.getIndexBuffer(side,0)',code);self.assertIn('ESMTerrain::sampleBlendmaps',code)
        self.assertIn('mesh->addTriangle',code);self.assertIn('drawable->addPrimitiveSet(indices)',code)
        physics=(paths.ROOT/'src/Physics.cpp').read_text()
        for text in ('Resource::makeInstance','matrix.decompose','std::min(dt,MaxFrameDelta)','frameSteps<MaxFrameSteps','setInternalGhostPairCallback(nullptr)'):self.assertIn(text,physics)

    def test_configured_language_sdk_precision_and_single_provider(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sdk=root/'iPhoneOS.sdk';include=root/'include';gen=root/'g3-generated';gen.mkdir();(gen/'osg-include.txt').write_text(str(include))
            for name in ('OpenThreads/Config','OpenThreads/Version','osg/Config','osg/GL','osg/Version'):
                p=include/name;p.parent.mkdir(exist_ok=True,parents=True);p.write_text('#define OSG_GLES3_AVAILABLE\n')
            sources=[paths.ROOT/'src/Exterior.cpp',paths.ROOT/'src/Terrain.cpp',paths.ROOT/'src/Physics.cpp',gen/'WorldMesh.cpp',paths.ROOT/'device/src/main.mm',paths.REPO/'components/nifbullet/bulletnifloader.cpp',paths.REPO/'components/esm3/loadland.cpp',paths.REPO/'components/terrain/buffercache.cpp']
            args=['clang++','-std=c++2a','-arch','arm64','-isysroot',str(sdk),'-DBT_USE_DOUBLE_PRECISION','-I'+str(include)]
            entries=[{'file':str(s),'arguments':args[:]} for s in sources]+[{'file':str(root/'src/osg/State.cpp'),'arguments':args[:]},
                {'file':str(root/'src/BulletDynamics/Dynamics/btDiscreteDynamicsWorld.cpp'),'arguments':args[:]},
                {'file':str(root/'src/BulletCollision/CollisionDispatch/btCollisionWorld.cpp'),'arguments':args[:]},
                {'file':str(root/'src/LinearMath/btAlignedAllocator.cpp'),'arguments':args[:]}]
            file=root/'compile_commands.json'
            def save(value):file.write_text(json.dumps(value))
            save(entries);self.assertEqual(provenance.configured(root,sdk)['osg_providers'],1)
            for old,new in (('-std=c++2a','-std=c++17'),('arm64','x86_64'),('-DBT_USE_DOUBLE_PRECISION','-DOTHER'),(str(sdk),str(root/'MacOSX.sdk'))):
                bad=json.loads(json.dumps(entries));bad[0]['arguments']=[new if a==old else a for a in args];save(bad)
                with self.assertRaises(ValueError):provenance.configured(root,sdk)
            for provider in (-1,-2,-3,-4):
                save(entries+[entries[provider]])
                with self.assertRaises(ValueError):provenance.configured(root,sdk)
            for provider in (-1,-2,-3):
                for old,new in (('-DBT_USE_DOUBLE_PRECISION','-DOTHER'),('-DBT_USE_DOUBLE_PRECISION','-DBT_USE_DOUBLE_PRECISION=0'),('arm64','x86_64'),(str(sdk),str(root/'MacOSX.sdk'))):
                    bad=json.loads(json.dumps(entries));bad[provider]['arguments']=[new if a==old else a for a in args];save(bad)
                    with self.assertRaises(ValueError):provenance.configured(root,sdk)

    def test_bullet_audit_checks_all_units_and_consistent_host_platform(self):
        from unittest.mock import patch
        args=['clang++','-DBT_USE_DOUBLE_PRECISION','-arch','arm64','-isysroot','/SDK/MacOSX.sdk']
        entries=[{'file':str(paths.ROOT/'src/Physics.cpp'),'arguments':args[:]}]+[
            {'file':'/bullet/src/'+name,'arguments':args[:]} for name in ('BulletDynamics/Dynamics/btDiscreteDynamicsWorld.cpp','BulletCollision/CollisionDispatch/btCollisionWorld.cpp','LinearMath/btAlignedAllocator.cpp','LinearMath/btVector3.cpp')]
        self.assertEqual(provenance.bullet_configuration(entries)['providers']['LinearMath'],2)
        bad=json.loads(json.dumps(entries));bad[-1]['arguments'].remove('-DBT_USE_DOUBLE_PRECISION')
        with self.assertRaisesRegex(ValueError,'LinearMath lacks'):provenance.bullet_configuration(bad)
        bad=json.loads(json.dumps(entries));bad[-2]['file']='/another/src/LinearMath/btAlignedAllocator.cpp'
        with self.assertRaisesRegex(ValueError,'Multiple Bullet'):provenance.bullet_configuration(bad)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);file=root/'compile_commands.json';file.write_text(json.dumps(entries))
            with patch.object(provenance.sys,'platform','darwin'):
                self.assertEqual(provenance.host_configured(root)['precision'],'double')
                for entry in entries:entry['arguments']=[a.replace('MacOSX.sdk','iPhoneOS.sdk') for a in entry['arguments']]
                file.write_text(json.dumps(entries))
                with self.assertRaisesRegex(ValueError,'native macOS ARM64'):provenance.host_configured(root)

    def test_manual_workflow_retains_early_gate_and_accepted_regressions(self):
        workflow=(paths.REPO/'.github/workflows/ios-openmw-exterior-device.yml').read_text()
        self.assertIn('workflow_dispatch:',workflow);self.assertNotIn('  push:',workflow)
        self.assertLess(workflow.index('tools/device_sdk_check.py'),workflow.index('Acquire and verify unchanged Bullet'))
        for text in ('test_g2.py','test_g3.py',"-R '^g1d-'","-R '^g2-'","-R '^g3-'",'provenance.py" --configured','tools/package.py','validate_dependency.py','if: always()'):
            self.assertIn(text,workflow)
        self.assertIn('provider/provider/g1c/prepared',workflow)

    def test_private_inputs_are_not_public_bundle_resources(self):
        code=(paths.ROOT/'tools/package.py').read_text()
        self.assertIn("if set(entries)!=set(allowed)|{'Info.plist','IOSOpenMWExterior','g3-build.json'}",code)
        for text in ('p.graph','validate(reopened','Reopened IPA differs','Source commit mismatch','org.openmw.experiments.real-model'):
            self.assertIn(text,code)
        app=(paths.ROOT/'device/src/main.mm').read_text()
        self.assertIn('Documents(@"Model")',app);self.assertIn('Private inputs changed during loading',app)

    def test_real_package_validator_binding_inventory_platform_and_reopen(self):
        import plistlib,zipfile
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('_g3_review_package',paths.ROOT/'tools/package.py')
        package=importlib.util.module_from_spec(spec);spec.loader.exec_module(package)
        def binary(deps,kind=2,install=None,platform=2):
            commands=[struct.pack('<6I',0x32,24,platform,18<<16,27<<16,0)]
            for command,value,base in [(0xc,d,24) for d in deps]+[(0x8000001c,'@executable_path/Frameworks',12)]+([(0xd,install,24)] if install else []):
                value=value.encode()+b'\0';size=(base+len(value)+7)&~7
                commands.append(struct.pack('<III',command,size,base)+bytes(base-12)+value+bytes(size-base-len(value)))
            body=b''.join(commands);return struct.pack('<8I',0xfeedfacf,0x0100000c,0,kind,len(commands),len(body),0,0)+body
        roles={'egl':'Frameworks/libEGL.framework/libEGL','gles':'Frameworks/libGLESv2.framework/libGLESv2'}
        metadata={'angle_libraries':roles};original={'g1b-build.json':json.dumps(metadata).encode()}
        for path in roles.values():original[path]=binary([],6,'@rpath/'+path.removeprefix('Frameworks/'))
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);provenance.prepare(root/'generated');data=(root/'generated/g3-build.json').read_bytes();digest=hashlib.sha256(data).hexdigest().encode()
            native=binary(['@rpath/'+p.removeprefix('Frameworks/') for p in roles.values()])+digest
            info=plistlib.dumps({'CFBundleIdentifier':'org.openmw.experiments.real-model','CFBundleExecutable':'IOSOpenMWExterior','CFBundleSupportedPlatforms':['iPhoneOS'],'MinimumOSVersion':'18.0'})
            entries={n:package.p.Entry(b,0o100755) for n,b in original.items() if n.startswith('Frameworks/')}
            entries.update({'Info.plist':package.p.Entry(info,0o100644),'IOSOpenMWExterior':package.p.Entry(native,0o100755),'g3-build.json':package.p.Entry(data,0o100644)})
            # Only acquisition is mocked: source binding, graph, architecture and inventory are real.
            with patch.object(package.p,'prepared_resources',return_value=(original,{})):
                self.assertTrue(package.validate(entries,root,root/'iPhoneOS.sdk')['valid'])
                ipa=root/'public.ipa';package.p.core.write_ipa(entries,ipa)
                with zipfile.ZipFile(ipa) as z:
                    reopened={n[len(package.p.core.PREFIX):]:package.p.Entry(z.read(n),z.getinfo(n).external_attr>>16) for n in z.namelist() if not n.endswith('/')}
                self.assertEqual(reopened,entries);self.assertTrue(package.validate(reopened,root,root/'iPhoneOS.sdk')['valid'])
                bad=dict(entries);bad['Morrowind.bsa']=package.p.Entry(b'private sentinel',0o100644)
                with self.assertRaisesRegex(ValueError,'Exact public inventory'):package.validate(bad,root,root/'iPhoneOS.sdk')
                bad=dict(entries);bad['IOSOpenMWExterior']=package.p.Entry(binary([],platform=1)+digest,0o100755)
                with self.assertRaises(ValueError):package.validate(bad,root,root/'iPhoneOS.sdk')
                bad=dict(entries);bad['IOSOpenMWExterior']=package.p.Entry(native.replace(digest,b'0'*64),0o100755)
                with self.assertRaisesRegex(ValueError,'provenance binding'):package.validate(bad,root,root/'iPhoneOS.sdk')

    def test_new_diagnostics_probe_retains_g2_and_checks_current_sdk(self):
        code=(paths.ROOT/'tools/device_sdk_check.py').read_text()
        for text in ('old.run(output/','old.core.macho','old.core.system_dependency','diagnostics-compile-link.log'):self.assertIn(text,code)
        probe=(paths.ROOT/'tests/diagnostics_probe.mm').read_text()
        for text in ('task_info','phys_footprint','thermalState','buttonA'):self.assertIn(text,probe)

    def test_all_new_python_syntax(self):
        for p in paths.ROOT.rglob('*.py'):
            if not {'artifacts','build','__pycache__'}&set(p.relative_to(paths.ROOT).parts):ast.parse(p.read_text(),filename=str(p))

if __name__=='__main__':unittest.main()
