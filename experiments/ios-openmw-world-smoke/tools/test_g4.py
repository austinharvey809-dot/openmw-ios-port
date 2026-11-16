"""Portable boundary regressions; no Apple SDK or physical acceptance claims."""
import base64,hashlib,io,json,os,plistlib,shutil,stat,struct,subprocess,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import fixtures,native_preflight,package,paths,prepare_dependencies,prepare_shaders,private_profile,provenance,run_cases
import dependency_preflight
import osg_compat


class OSGCompatibilityTests(unittest.TestCase):
    def test_exact_khronos_identifier_values(self):
        osg_compat.literal('#define GL_BUFFER_KHR 0x82E0\n','GL_BUFFER_KHR')
        for text in ('#define GL_BUFFER_KHR 0x1234\n','',
                '#define GL_BUFFER_KHR 0x82E0\n#define GL_BUFFER_KHR 0x82E0\n'):
            with self.assertRaises(ValueError):osg_compat.literal(text,'GL_BUFFER_KHR')
    def test_guarded_source_inventory_and_hash(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'osg';name=osg_compat.SERIALIZER
            target=source/name;target.parent.mkdir(parents=True)
            target.write_text('ADD_GLENUM_SERIALIZER( Target,GLenum, GL_BUFFER);\n')
            (root/'data').mkdir();lock={'osg_revision':'authored','source_sha256_lf':{name:hashlib.sha256(target.read_bytes().replace(b'\r\n',b'\n')).hexdigest()}}
            (root/'data/gles-source-lock.json').write_text(json.dumps(lock))
            with patch.object(osg_compat,'ROOT',root):
                self.assertEqual(osg_compat.verify(source)['verified_sources'],1)
                target.write_text('changed default\n')
                with self.assertRaisesRegex(ValueError,'source changed'):osg_compat.verify(source)
                target.with_name('unexpected.cpp').write_text('extra')
                with self.assertRaisesRegex(ValueError,'inventory'):osg_compat.verify(source)
    def test_complete_native_inventory_and_alias_scope(self):
        lock=json.loads((paths.ROOT/'data/gles-source-lock.json').read_text())['source_sha256_lf']
        with tempfile.TemporaryDirectory() as temp:
            build=Path(temp);commands=[]
            for name in lock:
                target='g4-serializers-osg' if '/serializers/' in name else 'g4-plugin-osg' if '/osgPlugins/' in name else Path(name).parts[1]
                args=['clang++','-DGL_BUFFER=GL_BUFFER_KHR'] if name==osg_compat.SERIALIZER else ['clang++']
                commands.append({'file':'/pinned/'+name,'arguments':args,'output':'CMakeFiles/'+target+'.dir/source.o'})
            def write(entries):(build/'compile_commands.json').write_text(json.dumps(entries))
            write(commands);self.assertEqual(len(osg_compat.configured(build)),221)
            for entries in (commands[:-1],commands+[commands[0]]):
                write(entries)
                with self.assertRaisesRegex(ValueError,'inventory'):osg_compat.configured(build)
            commands[0]['arguments'].append('-DGL_BUFFER=GL_BUFFER_KHR');write(commands)
            with self.assertRaisesRegex(ValueError,'leaked'):osg_compat.configured(build)
    def test_preflight_compiles_actual_targets_and_cache_is_revalidated(self):
        code=(paths.ROOT/'tools/native_preflight.py').read_text()
        self.assertIn('*osg_compat.TARGETS',code);self.assertIn('osg_compat.compiled',code)
        workflow=provenance.WORKFLOW.read_text()
        self.assertIn('--target openmw-world-check openmw-g4-osg-registration-check',workflow)
        self.assertIn('HEAD:experiments/ios-angle-smoke',workflow)
        self.assertIn('--show-sdk-build-version',workflow)
        self.assertLess(workflow.index('--resolve "$EVIDENCE/cached-angle.cmake"'),workflow.index('--sdk "$(xcrun --sdk iphoneos --show-sdk-path)"',workflow.index('id: angle\n')))
        self.assertNotIn('restore-keys:',workflow)


class DependencyTests(unittest.TestCase):
    def cmake_platform(self,processor='',arch='arm64',sdk='/SDK path/iPhoneOS27.0.sdk',system='iOS'):
        cmake=os.environ.get('OPENMW_TEST_CMAKE') or shutil.which('cmake')
        if not cmake:self.skipTest('CMake required for actual platform forwarding regression')
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);output=(root/'args.txt').as_posix()
            script=root/'platform.cmake'
            values={'CMAKE_SYSTEM_NAME':system,'CMAKE_HOST_SYSTEM_PROCESSOR':'x86_64','CMAKE_SYSTEM_PROCESSOR':processor,
                'CMAKE_OSX_ARCHITECTURES':arch,'CMAKE_OSX_SYSROOT':sdk,'CMAKE_OSX_DEPLOYMENT_TARGET':'18.0'}
            script.write_text(''.join('set('+name+' "'+value+'")\n' for name,value in values.items())+
                'include("'+(paths.ROOT/'cmake/jpeg_platform.cmake').as_posix()+'")\n'+
                'g4_jpeg_platform_arguments(arguments)\nstring(REPLACE ";" "\\n" text "${arguments}")\nfile(WRITE "'+output+'" "${text}")\n')
            result=subprocess.run([cmake,'-P',str(script)],capture_output=True,text=True)
            return result,(root/'args.txt').read_text().splitlines() if (root/'args.txt').exists() else []
    def test_ios_empty_processor_uses_explicit_target_not_host(self):
        result,args=self.cmake_platform()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('-DCMAKE_SYSTEM_PROCESSOR:STRING=arm64',args)
        self.assertIn('-DCMAKE_OSX_SYSROOT:STRING=/SDK path/iPhoneOS27.0.sdk',args)
        self.assertIn('-DCMAKE_OSX_DEPLOYMENT_TARGET:STRING=18.0',args)
        self.assertFalse(any('x86_64' in arg for arg in args))
    def test_cross_target_conflicts_fail(self):
        for options in ({'processor':'x86_64'},{'arch':'x86_64'},{'arch':'arm64;x86_64'},{'arch':''},{'sdk':'/SDK/iPhoneSimulator.sdk'}):
            with self.subTest(options=options):self.assertNotEqual(self.cmake_platform(**options)[0].returncode,0)
    def test_host_processor_preserved(self):
        result,args=self.cmake_platform(system='Windows',processor='AMD64',arch='',sdk='')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('-DCMAKE_SYSTEM_PROCESSOR:STRING=AMD64',args)
    @staticmethod
    def object(platform=2,minimum=18<<16,cpu=0x0100000c,kind=1,duplicate=False):
        load=struct.pack('<6I',0x32,24,platform,minimum,0,0)
        return struct.pack('<8I',0xfeedfacf,cpu,0,kind,2 if duplicate else 1,len(load)*(2 if duplicate else 1),0,0)+load*(2 if duplicate else 1)
    @staticmethod
    def archive(members,bsd=False):
        result=b'!<arch>\n'
        for name,body in members:
            encoded=name.encode();payload=encoded+body if bsd else body
            stored=('#1/'+str(len(encoded))) if bsd else name+'/'
            header=(f'{stored:<16}{0:<12}{0:<6}{0:<6}{"100644":<8}{len(payload):<10}`\n').encode()
            result+=header+payload+(b'\n' if len(payload)%2 else b'')
        return result
    def test_real_archive_member_traversal_and_platform(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'jpeg.a'
            for bsd in (False,True):
                path.write_bytes(self.archive([('__.SYMDEF',b'symbols'),('codec-long-name.c.o' if bsd else 'codec.c.o',self.object())],bsd=bsd))
                report=dependency_preflight.inspect_archive(path)
                self.assertEqual(report['objects'],1);self.assertEqual(report['platform'],'iPhoneOS')
    def test_every_object_is_checked_and_host_simulator_cannot_pass(self):
        for changes in ({'platform':1},{'platform':7},{'cpu':0x01000007},{'minimum':17<<16},{'kind':2},{'duplicate':True}):
            with self.subTest(changes=changes),tempfile.TemporaryDirectory() as temp:
                path=Path(temp)/'jpeg.a';path.write_bytes(self.archive([('good.o',self.object()),('wrong.o',self.object(**changes))]))
                with self.assertRaises(ValueError):dependency_preflight.inspect_archive(path)
    def test_missing_truncated_and_empty_archives_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'jpeg.a'
            with self.assertRaisesRegex(ValueError,'Missing'):dependency_preflight.inspect_archive(path)
            for data in (b'!<arch>\n',b'not an archive',self.archive([('bad.o',b'text')]),self.archive([('valid.o',self.object())])[:-4]):
                path.write_bytes(data)
                with self.assertRaises(ValueError):dependency_preflight.inspect_archive(path)
    def test_native_dependency_gate_cannot_pass_on_windows(self):
        with patch.object(dependency_preflight.sys,'platform','win32'),self.assertRaisesRegex(ValueError,'genuine Apple'):
            dependency_preflight.run(Path('.'),Path('.'),Path('.'))
    def test_external_configure_and_archive_check_precede_engine(self):
        source=(paths.ROOT/'tools/native_preflight.py').read_text()
        self.assertLess(source.index('dependency_preflight.run'),source.index('for index,entry in enumerate(selected)'))
        source=(paths.ROOT/'tools/dependency_preflight.py').read_text()
        self.assertIn('g4-jpeg-build-configure',source);self.assertIn('inspect_archive(Path(path))',source)
        workflow=provenance.WORKFLOW.read_text()
        self.assertLess(workflow.index('id: g4_preflight'),workflow.index('name: Compile and link genuine device geometry executable'))
    def test_dependency_cache_and_compiler_arguments_must_agree(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);sdk=root/'iPhoneOS.sdk';sdk.mkdir();jpeg=root/'g4-deps/jpeg';jpeg.mkdir(parents=True)
            parent={'CMAKE_C_COMPILER':'/usr/bin/cc','CMAKE_AR':'/usr/bin/ar','CMAKE_RANLIB':'/usr/bin/ranlib',
                'CMAKE_MAKE_PROGRAM':'/usr/bin/make','CMAKE_BUILD_TYPE':'Release'}
            child={**parent,'CMAKE_SYSTEM_NAME':'iOS','CMAKE_SYSTEM_PROCESSOR':'arm64','CMAKE_OSX_ARCHITECTURES':'arm64',
                'CMAKE_OSX_DEPLOYMENT_TARGET':'18.0','CMAKE_OSX_SYSROOT':str(sdk),'ENABLE_STATIC':'ON','ENABLE_SHARED':'OFF',
                'WITH_SIMD':'OFF','WITH_TURBOJPEG':'OFF','WITH_TOOLS':'OFF','WITH_TESTS':'OFF'}
            write=lambda path,values:path.write_text(''.join(n+':STRING='+v+'\n' for n,v in values.items()))
            write(root/'CMakeCache.txt',parent);write(jpeg/'CMakeCache.txt',child)
            system=jpeg/'CMakeFiles/test-version/CMakeSystem.cmake';system.parent.mkdir(parents=True)
            system.write_text('set(CMAKE_SYSTEM_PROCESSOR "arm64")\n')
            command={'file':'codec.c','arguments':['/usr/bin/cc','-arch','arm64','-isysroot',str(sdk),'-miphoneos-version-min=18.0','-c','codec.c']}
            (jpeg/'compile_commands.json').write_text(json.dumps([command]))
            (root/'compile_commands.json').write_text(json.dumps([{**command,'output':'CMakeFiles/g4-png.dir/file'+str(i)+'.o'} for i in range(30)]))
            self.assertEqual(dependency_preflight.configured(root,sdk)['processor'],'arm64')
            for name,value in (('CMAKE_SYSTEM_PROCESSOR',''),('CMAKE_AR','/wrong/ar'),('ENABLE_SHARED','ON')):
                with self.subTest(name=name):
                    write(jpeg/'CMakeCache.txt',{**child,name:value})
                    with self.assertRaises(ValueError):dependency_preflight.configured(root,sdk)
            write(jpeg/'CMakeCache.txt',child)
            command['arguments']+=['-miphoneos-version-min=17.0']
            (jpeg/'compile_commands.json').write_text(json.dumps([command]))
            with self.assertRaisesRegex(ValueError,'deployment'):dependency_preflight.configured(root,sdk)


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


class RunnerEvidenceTests(unittest.TestCase):
    @staticmethod
    def completed(code=0,stdout=b'',stderr=b''):
        return subprocess.CompletedProcess(['authored-child'],code,stdout,stderr)
    def test_partial_results_and_silent_signal_are_retained_before_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'results.json';calls=[]
            def child(*args,**kwargs):
                pending=json.loads(output.read_text());self.assertEqual(pending[-1]['status'],'RUNNING')
                calls.append(args[0])
                return self.completed(0,b'{"status":"PASS","cells":9,"programs":2}') if len(calls)==1 else self.completed(-11)
            with patch.object(fixtures,'POSITIVE',('good','startup-capabilities')),patch.object(fixtures,'NEGATIVE',{}),patch.object(run_cases.subprocess,'run',side_effect=child),patch.object(run_cases.sys,'platform','darwin'):
                with self.assertRaisesRegex(ValueError,'exit=-11 signal=11'):
                    run_cases.run(Path('authored-child'),Path('authored-shaders'),output)
            rows=json.loads(output.read_text());self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['status'],'PASS');self.assertEqual(rows[1]['status'],'FAIL')
            self.assertEqual(rows[1]['signal_name'],'SIGSEGV');self.assertEqual(rows[1]['stdout'],'')
            self.assertEqual(rows[1]['stderr'],'');self.assertTrue(rows[1]['inputs_unchanged'])
            self.assertFalse(list(output.parent.glob('*.tmp')))
    def test_windows_status_and_non_utf8_streams_are_lossless(self):
        with patch.object(run_cases.subprocess,'run',return_value=self.completed(0xc0000005,b'partial\xff',b'warning\x80')):
            row=run_cases.capture(['authored-child'],1)
        self.assertEqual(row['exit_hex'],'0xc0000005');self.assertIsNone(row['signal'])
        self.assertEqual(base64.b64decode(row['stdout_base64']),b'partial\xff')
        self.assertEqual(base64.b64decode(row['stderr_base64']),b'warning\x80')
    def test_signed_windows_status_is_not_mislabeled_as_a_posix_signal(self):
        with patch.object(run_cases.subprocess,'run',return_value=self.completed(-1073741819)),patch.object(run_cases.sys,'platform','win32'):
            row=run_cases.capture(['authored-child'],1)
        self.assertEqual(row['exit'],-1073741819)
        self.assertEqual(row['exit_hex'],'0xc0000005');self.assertIsNone(row['signal'])
    def test_timeout_retains_partial_streams_without_inventing_an_exit_code(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'startup.json'
            error=subprocess.TimeoutExpired(['authored-child'],30,output=b'partial',stderr=b'waiting')
            with patch.object(run_cases.subprocess,'run',side_effect=error),self.assertRaisesRegex(ValueError,'timed out'):
                run_cases.run_startup(Path('authored-child'),output)
            row=json.loads(output.read_text())[0];self.assertTrue(row['timeout'])
            self.assertIsNone(row['exit']);self.assertEqual(row['stdout'],'partial');self.assertEqual(row['stderr'],'waiting')
            self.assertEqual(row['status'],'FAIL')
    def test_spawn_error_and_malformed_success_are_saved(self):
        outcomes=[FileNotFoundError('authored missing binary'),self.completed(0,b'not JSON'),self.completed(0,b'[]'),
            self.completed(0,b'{"status":"PASS","checks":0,"scope":"genuine pinned OSG headless startup guards"}')]
        for outcome in outcomes:
            with self.subTest(outcome=outcome),tempfile.TemporaryDirectory() as temp:
                output=Path(temp)/'startup.json'
                options={'side_effect':outcome} if isinstance(outcome,Exception) else {'return_value':outcome}
                with patch.object(run_cases.subprocess,'run',**options),self.assertRaises(ValueError):
                    run_cases.run_startup(Path('authored-child'),output)
                self.assertEqual(json.loads(output.read_text())[0]['status'],'FAIL')
    def test_mutated_inputs_fail_with_their_before_and_after_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'results.json'
            def mutate(command,**kwargs):
                (Path(command[1])/'Morrowind.esm').write_bytes(b'authored mutation')
                return self.completed(0,b'{"status":"PASS","cells":9,"programs":2}')
            with patch.object(fixtures,'POSITIVE',('good',)),patch.object(fixtures,'NEGATIVE',{}),patch.object(run_cases.subprocess,'run',side_effect=mutate):
                with self.assertRaisesRegex(ValueError,'modified authored inputs'):
                    run_cases.run(Path('authored-child'),Path('authored-shaders'),output)
            row=json.loads(output.read_text())[0];self.assertFalse(row['inputs_unchanged'])
            self.assertNotEqual(row['inputs_before_sha256'],row['inputs_after_sha256'])
    def test_signal_cannot_pass_a_negative_even_with_the_expected_message(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'results.json'
            with patch.object(fixtures,'POSITIVE',()),patch.object(fixtures,'NEGATIVE',{'locked-door':'locked/trapped door'}),patch.object(run_cases.subprocess,'run',return_value=self.completed(-11,b'',b'locked/trapped door')):
                with self.assertRaisesRegex(ValueError,'Wrong native rejection'):
                    run_cases.run(Path('authored-child'),Path('authored-shaders'),output)
            self.assertEqual(json.loads(output.read_text())[0]['status'],'FAIL')
    def test_real_silent_child_exit_is_retained(self):
        row=run_cases.capture([sys.executable,'-c','import os; os._exit(23)'],10)
        self.assertEqual(row['exit'],23);self.assertEqual(row['stdout'],'');self.assertEqual(row['stderr'],'')
        self.assertFalse(row['timeout']);self.assertIsNone(row['signal'])


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
    def test_embedded_capabilities_initialized_before_upstream_registration(self):
        helper=(paths.ROOT/'src/GLCapabilities.hpp').read_text()
        self.assertLess(helper.index('state.initializeExtensionProcs();'),helper.index('registerGLCapabilities(context);'))
        registration=helper.split('inline void registerGLCapabilities',1)[1].split('inline void initializeGLCapabilities',1)[0]
        self.assertLess(registration.index('get<osg::GLExtensions>()'),registration.index('operation(context)'))
        device=(paths.ROOT/'device/src/OSGScene.hpp').read_text()
        self.assertIn('G4::initializeGLCapabilities(window,G4::deviceContextCurrent,checkpoint)',device)
        self.assertNotIn('extensions(window)',device)
        self.assertIn('startup-capabilities',fixtures.POSITIVE)
    def test_context_handle_is_checked_before_any_gl_dispatch(self):
        helper=(paths.ROOT/'src/GLCapabilities.hpp').read_text().split('inline void initializeGLCapabilities',1)[1]
        self.assertLess(helper.index('requireCurrentGLContext(current)'),helper.index('glGetString(GL_VERSION)'))
        device=(paths.ROOT/'device/src/OSGScene.hpp').read_text()
        self.assertLess(device.index('G4::requireCurrentGLContext'),device.index('new osgViewer::GraphicsWindowEmbedded'))
        main=(paths.ROOT/'device/src/main.mm').read_text()
        self.assertIn('eglGetCurrentContext()!=EGL_NO_CONTEXT',main)
        self.assertIn('eglGetCurrentDisplay()!=EGL_NO_DISPLAY',main)
        test=(paths.ROOT/'tests/StartupChecks.hpp').read_text()
        self.assertIn('CGLGetCurrentContext()',test);self.assertIn('wglGetCurrentContext()',test)
        self.assertIn('window->close(false)',test);self.assertNotIn('glGetString(',test)
    def test_early_native_gate_and_partial_evidence_precede_full_world_build(self):
        workflow=provenance.WORKFLOW.read_text()
        self.assertLess(workflow.index('--target openmw-g4-startup-check'),workflow.index('--target openmw-world-check'))
        self.assertIn("'^g4-startup-capabilities$'",workflow)
        for name in ('g4-startup-case.json','g4-world-cases.json','G4_STARTUP_GATE'):
            self.assertIn(name,workflow)
        cmake=(paths.ROOT/'CMakeLists.txt').read_text()
        linkage=cmake.split('target_link_libraries(openmw-g4-startup-check PRIVATE ',1)[1].split(')',1)[0]
        self.assertNotIn('g4-upstream',linkage);self.assertNotIn('Bullet',linkage)
        self.assertIn('--output "${CMAKE_CURRENT_BINARY_DIR}/g4-world-cases.json"',cmake)
    def test_startup_evidence_precedes_renderer_and_is_separate_from_worker_report(self):
        source=(paths.ROOT/'device/src/main.mm').read_text()
        view=source.split('- (void)viewDidLoad {',1)[1].split('- (void)beginPreparation {',1)[0]
        self.assertIn('[self exportResults]',view)
        self.assertIn('@"parser_geometry_ready":@NO',view)
        self.assertIn('G4Expected::Commit',view)
        self.assertIn('@"g4-startup.json"',source)
        self.assertIn('if(events.count>128)',source)
        self.assertIn('NSJSONWritingSortedKeys error:&error',source)
        self.assertIn('@catch(NSException* exception)',source)
        self.assertIn('isEqualToString:startupSession',source)
        self.assertIn('PrepareWorld(report,startupSession)',source)
        activation=source.split('- (void)activate {',1)[1].split('- (void)deactivate {',1)[0]
        self.assertLess(activation.index('renderer->start('),activation.index('[self beginPreparation]'))
    def test_debug_capture_retains_deferred_logging_and_bounded_storage(self):
        # Guard the accepted shared implementation rather than disabling debugging.
        capture=(paths.REPO/'experiments/ios-openmw-nif-render-smoke/device/baseline/src/GLDebugCapture.hpp').read_text()
        callback=capture.split('static void GL_APIENTRY capture(',1)[1].split('bool ownsCurrentContext()',1)[0]
        self.assertNotIn('Log(',callback);self.assertNotIn('glGetError(',callback)
        self.assertIn('std::memcpy',callback);self.assertIn('noexcept',callback)
        renderer=(paths.REPO/'experiments/ios-openmw-nif-render-smoke/device/src/AngleRenderer.hpp').read_text()
        self.assertIn('callback storage outlives explicit EGL teardown',renderer)
        self.assertLess(renderer.index('eglDestroyContext(display, context)'),renderer.index('eglTerminate(display)'))
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
