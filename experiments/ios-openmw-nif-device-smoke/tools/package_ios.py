"""G0C unsigned device gates, reusing F's SDK/Mach-O and strict ZIP primitives."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import stat
import struct
import tempfile
import zipfile

from common import ROOT, REPO, G0B, OSG_REVISION, HOST_COMMIT, load, sha, require, tree

f = load('_g0c_f_package', ROOT.parent / 'ios-openmw-data-smoke/tools/package_ios.py')
core, Entry = f.core, f.Entry
APP_NAME, EXECUTABLE = 'IOSOpenMWNifSmoke.app', 'IOSOpenMWNifSmoke'
BUNDLE_ID = 'org.openmw.experiments.ios-openmw-nif-smoke'
PREFIX = 'Payload/' + APP_NAME + '/'
# A separate module instance reuses F's generic collectors/writer unchanged.
f.APP_NAME, f.EXECUTABLE, f.PREFIX = APP_NAME, EXECUTABLE, PREFIX
collect_bundle, write_ipa = f.collect_bundle, f.write_ipa
FRAMEWORKS = {'/System/Library/Frameworks/' + name + '.framework/' + name
              for name in ('UIKit', 'Foundation', 'OpenGLES')}


def device_binary(data, sdk=None):
    details = core.macho(data)  # Exact ARM64, iOS LC_BUILD_VERSION, no signatures/encryption.
    require(details['filetype'] == 2 and details['minimum_os'] == (18, 0, 0), 'Expected iOS 18.0 MH_EXECUTE')
    require(not details['rpaths'] and details['install_name'] is None, 'Unexpected RPATH/install-name')
    offset = 32
    count, size = struct.unpack_from('<II', data, 16)
    for _ in range(count):
        command, length = struct.unpack_from('<II', data, offset)
        require(length % 8 == 0 and command not in {0x24, 0x25, 0x2f, 0x30}, 'Ambiguous native platform metadata')
        if command == 0x32:
            require(length == 24 + 8 * struct.unpack_from('<I', data, offset + 20)[0], 'Malformed LC_BUILD_VERSION')
        offset += length
    require(offset == 32 + size, 'Malformed load-command extent')
    dependencies = []
    for name in details['dependencies']:
        require(name in FRAMEWORKS or name in {'/usr/lib/libc++.1.dylib', '/usr/lib/libSystem.B.dylib',
                '/usr/lib/libobjc.A.dylib'}, 'Unexpected dependency: ' + name)
        dependencies.append(core.system_dependency(name, sdk, '18.0') if sdk else {'availability': 'unverified'})
    return details, dependencies


def prepared_resources(prepared):
    files = tree(prepared / 'resources')
    metadata = f.json_object(files['nif-build.json'], 'G0C provenance')
    require(metadata['osg_revision'] == OSG_REVISION and metadata['g0b_validated_commit'] == HOST_COMMIT
            and metadata['platform_target'] == 'iPhoneOS-arm64' and metadata['minimum_os'] == '18.0', 'Wrong provenance target')
    hashes = metadata['resources_sha256']
    require(set(hashes) == set(files) - {'nif-build.json'}, 'Provenance inventory mismatch')
    require(all(sha(files[name]) == digest for name, digest in hashes.items()), 'Prepared resource hash mismatch')
    manifest = f.json_object(files['Fixtures/fixture-manifest.json'], 'G0B fixtures')
    expected_fixtures = {p.name: p.read_bytes() for p in (G0B / 'data').iterdir() if p.is_file()}
    require({name.removeprefix('Fixtures/'): data for name, data in files.items() if name.startswith('Fixtures/')}
            == expected_fixtures, 'Prepared G0B bytes/inventory differ')
    require(len(manifest['files']) == 10, 'Wrong fixture count')
    for name, record in manifest['files'].items():
        data = files['Fixtures/' + name]
        require(record == {'size': len(data), 'sha256': sha(data)}, 'Fixture manifest mismatch')
    from prepare import bullet
    require(metadata['bullet_sha512'] == bullet.SHA512 and metadata['bullet_url'] == bullet.URL, 'Wrong Bullet pin')
    provenance = f.json_object(files['Provenance/bullet-provenance.json'], 'Bullet provenance')
    require(provenance['archive_sha512'] == bullet.SHA512 and provenance['source_url'] == bullet.URL,
            'Unverified Bullet provenance')
    from prepare import GENERATED
    require(all('Provenance/generated/' + name in files for name in GENERATED), 'Missing generated header provenance')
    require({'Licenses/OpenMW-LICENSE.txt', 'Licenses/OSG-LICENSE.txt', 'Licenses/Bullet-0.txt'} <= set(files),
            'Missing license resources')
    require(all(data.strip() for name, data in files.items() if name.startswith('Licenses/')), 'Empty license resource')
    header = (prepared / 'include/G0CExpectations.hpp').read_text(encoding='utf-8')
    require('BuildSHA256[] = "' + sha(files['nif-build.json']) + '";' in header,
            'Prepared metadata differs from compiled-header contract')
    return files, metadata


def validate_bundle(files, prepared, sdk=None):
    resources, metadata = prepared_resources(prepared)
    require(set(files) == set(resources) | {'Info.plist', EXECUTABLE}, 'Unexpected/missing app file inventory')
    for name, entry in files.items():
        core.safe_name(name)
        require(stat.S_ISREG(entry.mode) and '_CodeSignature' not in PurePosixPath(name).parts,
                'Nonregular/signed bundle input')
        require(PurePosixPath(name).suffix.lower() not in core.FORBIDDEN_SUFFIXES, 'Signing/provisioning input')
        if name != EXECUTABLE:
            require(not entry.mode & 0o111 and not entry.data.startswith(core.MACHO_MAGIC), 'Executable resource')
    require(all(files[name].data == data for name, data in resources.items()), 'App resource bytes differ')
    info = plistlib.loads(files['Info.plist'].data)
    require(info.get('CFBundleExecutable') == EXECUTABLE and info.get('CFBundleIdentifier') == BUNDLE_ID
            and info.get('CFBundlePackageType') == 'APPL', 'Wrong app identity')
    require(info.get('CFBundleSupportedPlatforms') == ['iPhoneOS'] and info.get('UIDeviceFamily') == [1]
            and info.get('LSRequiresIPhoneOS') is True and core.version_tuple(info.get('MinimumOSVersion')) == (18, 0, 0),
            'Wrong app platform/deployment')
    require(info.get('UIFileSharingEnabled') is True and info.get('LSSupportsOpeningDocumentsInPlace') is True
            and isinstance(info.get('UILaunchScreen'), dict), 'Missing export/launch settings')
    scenes = info.get('UIApplicationSceneManifest', {})
    require(scenes.get('UIApplicationSupportsMultipleScenes') is False and
            scenes.get('UISceneConfigurations', {}).get('UIWindowSceneSessionRoleApplication') ==
            [{'UISceneConfigurationName': 'Default', 'UISceneDelegateClassName': 'NifSceneDelegate'}], 'Wrong scene configuration')
    require(files[EXECUTABLE].mode & 0o111, 'Missing executable mode')
    binary, dependencies = device_binary(files[EXECUTABLE].data, sdk)
    require({'/System/Library/Frameworks/UIKit.framework/UIKit', '/System/Library/Frameworks/Foundation.framework/Foundation'}
            <= set(binary['dependencies']), 'Missing UIKit/Foundation linkage')
    require(sha(resources['nif-build.json']).encode() in files[EXECUTABLE].data,
            'App does not embed this provenance contract')
    return {'valid': True, 'binaries': {EXECUTABLE: binary}, 'dependencies': dependencies,
            'source_commit': metadata['source_commit'], 'osg_revision': OSG_REVISION,
            'scope': 'G0C device packaging only; physical parsing unverified'}


def validate_ipa(path, prepared, sdk=None, expected=None):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len({e.filename for e in entries}) == len(entries) and archive.testzip() is None, 'Duplicate/corrupt IPA')
        require({'Payload/', PREFIX} <= {e.filename for e in entries}, 'Missing IPA root directories')
        files = {}
        for entry in entries:
            name = entry.filename.rstrip('/')
            core.safe_name(name)
            require(name in {'Payload', PREFIX.rstrip('/')} or name.startswith(PREFIX), 'Unexpected IPA root')
            mode = entry.external_attr >> 16
            require(not stat.S_ISLNK(mode) and not entry.flag_bits & 1, 'Linked/encrypted IPA entry')
            if entry.is_dir():
                require(stat.S_ISDIR(mode), 'Wrong directory mode')
            else:
                require(entry.filename.startswith(PREFIX), 'File outside app')
                files[name[len(PREFIX):]] = Entry(archive.read(entry), mode)
        report = validate_bundle(files, prepared, sdk)
        require(expected is None or files == expected, 'Reopened IPA differs from bundle')
    report.update(sha256=sha(path.read_bytes()), unsigned=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('link', 'bundle', 'ipa', 'reopen'))
    parser.add_argument('--product', type=Path, required=True)
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        core.check_sdk(args.sdk)
        if args.phase == 'link':
            binary, dependencies = device_binary(args.product.read_bytes(), args.sdk)
            report = {'valid': True, 'binaries': {args.product.name: binary}, 'dependencies': dependencies,
                      'sha256': sha(args.product.read_bytes()), 'scope': 'G0C0 device link; no runtime claim'}
            outputs = core.inspect_dependencies(args.product.parent, report)
        elif args.phase == 'reopen':
            report = validate_ipa(args.product, args.prepared, args.sdk)
            outputs = {}
        else:
            files = collect_bundle(args.product)
            report = validate_bundle(files, args.prepared, args.sdk)
            outputs = core.inspect_dependencies(args.product, report)
            if args.phase == 'ipa':
                require(args.output is not None, 'IPA output required')
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix='.ipa.tmp', delete=False) as handle:
                    temporary = Path(handle.name)
                write_ipa(files, temporary)
                report = validate_ipa(temporary, args.prepared, args.sdk, files)
                os.replace(temporary, args.output); temporary = None
        (args.evidence / (args.phase + '-otool.txt')).write_text('\n'.join(outputs.values()), encoding='utf-8')
        (args.evidence / (args.phase + '.json')).write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    except Exception as error:
        (args.evidence / (args.phase + '.json')).write_text(json.dumps({'valid': False, 'error': str(error)}) + '\n')
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
