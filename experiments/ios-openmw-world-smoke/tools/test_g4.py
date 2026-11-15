"""Portable boundary regressions; no Apple SDK or physical acceptance claims."""
import hashlib,io,json,plistlib,stat,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures,native_preflight,package,paths,prepare_dependencies,prepare_shaders,private_profile,provenance,run_cases


class PrivateProfileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        for name in ('Morrowind.esm','Morrowind.bsa','Mods/Example.esp','Loose/Textures/authored.dds'):
            p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'authored:'+name.encode())
    def create(self,**kw):
        return private_profile.create(self.root,kw.get('content',['Morrowind.esm']),['Morrowind.bsa'],kw.get('loose',[]))
    def test_order_hashes_and_no_copy(self):
        before={p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        profile=self.create(content=['Morrowind.esm','Mods/Example.esp'],loose=['Loose'])
        self.assertEqual(profile['content'],['Morrowind.esm','Mods/Example.esp'])
        self.assertEqual(set(profile['files']),{'Morrowind.esm','Mods/Example.esp','Morrowind.bsa','Loose/Textures/authored.dds'})
        self.assertEqual(profile['files']['Morrowind.esm'],hashlib.sha256(before[self.root/'Morrowind.esm']).hexdigest())
        self.assertEqual(before,{p:p.read_bytes() for p in self.root.rglob('*') if p.is_file()})
    def test_unsafe_paths(self):
        for name in ('../secret','/absolute','C:/private','Loose\\secret','Loose/../secret','Loose//Textures','./Morrowind.esm'):
            with self.subTest(name=name),self.assertRaises((ValueError,FileNotFoundError)):
                self.create(content=[name])
    def test_duplicate_basename_and_file(self):
        for names in (['Morrowind.esm','Morrowind.esm'],['Morrowind.esm','mods/MORROWIND.ESM']):
            with self.assertRaisesRegex(ValueError,'Duplicate'):self.create(content=names)
        with self.assertRaisesRegex(ValueError,'Duplicate'):self.create(loose=['Loose','Loose'])
    def test_budget(self):
        with self.assertRaisesRegex(ValueError,'budget'):self.create(content=[])
        with self.assertRaisesRegex(ValueError,'budget'):self.create(content=['x']*255)
    def test_symlink(self):
        try:(self.root/'Alias').symlink_to(self.root/'Loose',target_is_directory=True)
        except OSError:self.skipTest('Local OS does not permit test symlink creation')
        with self.assertRaisesRegex(ValueError,'Linked'):self.create(loose=['Alias'])


class ArchiveTests(unittest.TestCase):
    def archive(self,names):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            for name in names:archive.writestr(name,b'authored source')
        return zipfile.ZipFile(io.BytesIO(data.getvalue()))
    def test_archive_inventory_verification(self):
        with self.archive(['source/header.hpp','source/lib/code.cpp']) as archive,tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name,item in prepare_dependencies.members(archive):
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(archive.read(item))
            self.assertEqual(prepare_dependencies.verify_source(archive,root),2)
            (root/'extra').write_bytes(b'not in source')
            with self.assertRaisesRegex(ValueError,'inventory/hash'):prepare_dependencies.verify_source(archive,root)
            (root/'extra').unlink();(root/'header.hpp').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'inventory/hash'):prepare_dependencies.verify_source(archive,root)
    def test_archive_escapes_and_mixed_roots(self):
        for names in (['source/../escape'],['/absolute'],['source/C:/escape'],['a/x','b/y'],['a/x','a/x']):
            with self.subTest(names=names),self.archive(names) as archive,self.assertRaises(ValueError):
                list(prepare_dependencies.members(archive))
        # ZipFile.writestr normalizes the host separator on Windows. Exercise
        # the raw central-directory input rather than that writer's normalization.
        entry=zipfile.ZipInfo('source/escape');entry.filename='source\\escape'
        from unittest.mock import Mock
        with self.assertRaisesRegex(ValueError,'Unsafe'):
            list(prepare_dependencies.members(Mock(infolist=lambda:[entry])))
    def test_archive_symlink(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            entry=zipfile.ZipInfo('source/link');entry.external_attr=(stat.S_IFLNK|0o777)<<16
            archive.writestr(entry,b'../../escape')
        with zipfile.ZipFile(io.BytesIO(data.getvalue())) as archive,self.assertRaisesRegex(ValueError,'symlink'):
            list(prepare_dependencies.members(archive))


class CompilerTests(unittest.TestCase):
    def test_strict_standard_and_no_substring_escape(self):
        for spelling in ('-std=c++20','-std=c++2a'):provenance.standard([spelling])
        for args in ([],['-std=c++17'],['-std=c++14'],['-std=c++23'],['-std=gnu++20'],
                ['-std=c++20','-std=c++17'],['-std=c++20','-std=c++2a'],['-Dnote=-std=c++20']):
            with self.subTest(args=args),self.assertRaisesRegex(ValueError,'standard'):provenance.standard(args)
    def test_actual_apple_standard_tokens(self):
        entry={'command':'/usr/bin/clang++ -x objective-c++ -std=c++2a -arch arm64 -isysroot "/SDK with spaces/iPhoneOS.sdk" -c main.mm'}
        args=provenance.arguments(entry)
        self.assertIn('-std=c++2a',args);self.assertEqual(provenance.platform(args)['-arch'],['arm64'])
        command=native_preflight.syntax_arguments(args+['-o','file.o','-MF','deps.d','-MT','target','-MMD'])
        self.assertIn('-fsyntax-only',command);self.assertNotIn('file.o',command)
        self.assertIn('/SDK with spaces/iPhoneOS.sdk',command);self.assertIn('main.mm',command)
    def test_precision_conflict(self):
        self.assertTrue(provenance.double(['-DBT_USE_DOUBLE_PRECISION=1']))
        for args in ([],['-DBT_USE_DOUBLE_PRECISION=0'],['-DBT_USE_DOUBLE_PRECISION','-UBT_USE_DOUBLE_PRECISION']):
            self.assertFalse(provenance.double(args))
    def test_apple_preflight_cannot_pass_on_other_platforms(self):
        with patch.object(native_preflight.sys,'platform','win32'),self.assertRaisesRegex(ValueError,'genuine Apple'):
            native_preflight.run(Path('.'),Path('.'),Path('.'))


class FixtureAndShaderTests(unittest.TestCase):
    def test_negative_errors_are_specific_and_crashes_fail(self):
        for name,error in fixtures.NEGATIVE.items():
            self.assertTrue(error.strip())
            run_cases.reject(name,1,error)
            for code,message in ((0,error),(2,error),(-11,error),(1,'unrelated ordinary failure')):
                with self.assertRaises(ValueError):run_cases.reject(name,code,message)
    def test_all_cases_are_authored_and_structurally_readable(self):
        for mode in (*fixtures.POSITIVE,*fixtures.NEGATIVE):
            data=fixtures.inputs(mode)
            self.assertEqual(next(fixtures.records(data['Morrowind.esm']))[0],b'TES3')
            self.assertIn('Morrowind.bsa',data)
            for name in data:self.assertFalse(Path(name).is_absolute());self.assertNotIn('..',Path(name).parts)
    def test_priority_inputs_are_distinguishable(self):
        loose=fixtures.inputs('loose-override')
        self.assertTrue(loose['loose/Textures/fixture.dds'].endswith(b'G4-loose-priority'))
        archives=fixtures.inputs('last-bsa-wins')
        self.assertNotEqual(archives['Morrowind.bsa'],archives['Authored.bsa'])
    def test_translation_is_deterministic_and_upstream_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);before={p:p.read_bytes() for p in prepare_shaders.SOURCE.rglob('*') if p.is_file()}
            first=prepare_shaders.generate(root/'one');second=prepare_shaders.generate(root/'two')
            self.assertEqual(first,second);self.assertEqual(len(first['generated_sha256']),6)
            for path in (root/'one/compatibility').iterdir():
                text=path.read_text();self.assertTrue(text.startswith('#version 300 es'))
                self.assertNotIn('@link',text);self.assertNotIn('#include',text)
            self.assertEqual(before,{p:p.read_bytes() for p in before})
    def test_generation_refuses_source_tree(self):
        with self.assertRaisesRegex(ValueError,'outside sources'):prepare_shaders.generate(paths.ROOT/'src')


class PackagingTests(unittest.TestCase):
    def setUp(self):
        self.entry=package.p.Entry;self.mode=stat.S_IFREG|0o644
        self.manifest={'public_resources_sha256':{},'commit':'authored-commit','source_sha256_lf':{'unit':'hash'},
            'workflow_sha256_lf':hashlib.sha256(provenance.WORKFLOW.read_bytes().replace(b'\r\n',b'\n')).hexdigest()}
        self.original={'g1b-build.json':json.dumps({'angle_libraries':[]}).encode()}
        self.info={'CFBundleIdentifier':'org.openmw.experiments.real-model','CFBundleExecutable':'IOSOpenMWWorld',
            'CFBundleSupportedPlatforms':['iPhoneOS'],'MinimumOSVersion':'18.0'}
        for target,value in ((patch.object(package.p,'prepared_resources',return_value=(self.original,{})),None),
                (patch.object(package.provenance,'sources',return_value={'unit':'hash'}),None),
                (patch.object(package.support.host,'git',return_value=b'authored-commit'),None)):
            target.start();self.addCleanup(target.stop)
        self.graph=patch.object(package.p,'graph',return_value=([],{})).start();self.addCleanup(patch.stopall)
    def entries(self):
        data=json.dumps(self.manifest).encode()
        return {'Info.plist':self.entry(plistlib.dumps(self.info),self.mode),'g4-build.json':self.entry(data,self.mode),
            'IOSOpenMWWorld':self.entry(b'authored binding '+hashlib.sha256(data).hexdigest().encode(),stat.S_IFREG|0o755)}
    def test_existing_macho_gate_always_executes(self):
        package.validate(self.entries(),Path('.'),Path('.'));self.graph.assert_called_once()
        self.graph.side_effect=ValueError('host macOS binary rejected')
        with self.assertRaisesRegex(ValueError,'host macOS'):package.validate(self.entries(),Path('.'),Path('.'))
    def test_private_or_extra_asset_rejected(self):
        entries=self.entries();entries['Morrowind.bsa']=self.entry(b'authored stand-in',self.mode)
        with self.assertRaisesRegex(ValueError,'inventory'):package.validate(entries,Path('.'),Path('.'))
    def test_private_asset_cannot_self_authorize(self):
        self.manifest['public_resources_sha256']['Shaders/private.dds']=hashlib.sha256(b'authored').hexdigest()
        entries=self.entries();entries['Shaders/private.dds']=self.entry(b'authored',self.mode)
        with self.assertRaisesRegex(ValueError,'Game assets'):package.validate(entries,Path('.'),Path('.'))
    def test_hash_binding_platform_and_nonregular_rejected(self):
        for change,error in ((lambda e:e.update(IOSOpenMWWorld=self.entry(b'no binding',self.mode)),'binding'),
                (lambda e:e.update(IOSOpenMWWorld=self.entry(e['IOSOpenMWWorld'].data,stat.S_IFDIR|0o755)),'Nonregular')):
            entries=self.entries();change(entries)
            with self.assertRaisesRegex(ValueError,error):package.validate(entries,Path('.'),Path('.'))
        self.info['CFBundleSupportedPlatforms']=['MacOSX']
        with self.assertRaisesRegex(ValueError,'identity/platform'):package.validate(self.entries(),Path('.'),Path('.'))


class Contracts(unittest.TestCase):
    def test_device_shader_acceptance_precedes_publication(self):
        source=(paths.ROOT/'src/Session.cpp').read_text()
        self.assertLess(source.index('accept(*ready.area)'),source.index('root->removeChild(current->scene)'))
        device=(paths.ROOT/'device/src/OSGScene.hpp').read_text()
        self.assertIn('shaderLinked=false;acceptArea(owned->area())',device)
        self.assertIn('stamp->getReferenceTime()',device)
        self.assertIn('shaderAcceptedLoad()',device)
    def test_peak_memory_revision_guard_and_serial_file_log(self):
        source=(paths.ROOT/'device/src/main.mm').read_text()
        self.assertIn('std::lock_guard lock(DiagnosticFileMutex)',source)
        self.assertIn('vmCount>=TASK_VM_INFO_REV3_COUNT',source)
        self.assertIn('ledger_phys_footprint_peak',source)
        self.assertIn('sampled_peak_physical_footprint_bytes',source)
    def test_accepted_sources_unchanged(self):self.assertEqual(paths.verify()['accepted_g3_commit'],'d60ca603e82935a9ccce9ae5ec8dc9ec22013580')
    def test_manual_ci_preserves_native_gates(self):
        workflow=provenance.WORKFLOW.read_text()
        self.assertIn('workflow_dispatch:',workflow)
        for forbidden in ('pull_request:','schedule:','push:','continue-on-error: true'):self.assertNotIn(forbidden,workflow)
        for gate in ("'^g1d-'","'^g2-'","'^g3-'","'^g4-'",'device_sdk_check.py','native_preflight.py','package.py','validate_dependency.py'):
            self.assertIn(gate,workflow)
        self.assertIn('source archives only',workflow);self.assertNotIn('restore-keys:',workflow)
    def test_identity_and_controller_first(self):
        cmake=(paths.ROOT/'device/CMakeLists.txt').read_text();main=(paths.ROOT/'device/src/main.mm').read_text()
        self.assertIn('org.openmw.experiments.real-model',cmake);self.assertIn('Documents',main)
        self.assertNotIn('UIButton',main);self.assertIn('GCController',main)
        self.assertIn('world-profile.json',main);self.assertIn('Model',main)

if __name__=='__main__':unittest.main(verbosity=2)
