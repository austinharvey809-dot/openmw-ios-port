"""Strict G1B binary/bundle/IPA gates; no successful gate asserts physical rendering."""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import stat
import struct
import tempfile
import zipfile

from provenance import ROOT, REPO, G1A, host, PIN, files, sha, require, expected_geometry_hash

core = host.load('_g1b_angle_primitives', REPO / 'experiments/ios-angle-smoke/tools/package_ios.py')
APP_NAME, EXECUTABLE = 'IOSOpenMWNifTriangle.app', 'IOSOpenMWNifTriangle'
BUNDLE_ID = 'org.openmw.experiments.ios-openmw-nif-triangle'
PREFIX = 'Payload/' + APP_NAME + '/'
core.APP_NAME, core.PREFIX = APP_NAME, PREFIX
Entry = core.Entry


def prepared_resources(prepared):
    resources = files(prepared / 'resources')
    metadata = json.loads(resources['g1b-build.json'])
    require(metadata['source_commit'] == host.git('rev-parse', 'HEAD').decode().strip()
            and metadata['g1a_validated_commit'] == PIN and metadata['osg_revision'] == host.LOCK['osg_revision']
            and metadata['graphics_baseline_commit'] == host.LOCK['graphics_baseline_commit']
            and metadata['overlay_version'] == 2 and metadata['profile'] == 'GLES3'
            and metadata['platform_target'] == 'iPhoneOS-arm64' and metadata['minimum_os'] == '18.0', 'Wrong G1B provenance')
    require(set(resources) == set(metadata['resources_sha256']) | {'g1b-build.json'}, 'Prepared inventory mismatch')
    require(all(sha(resources[name]) == digest for name, digest in metadata['resources_sha256'].items()),
            'Prepared resource digest mismatch')
    require({name.removeprefix('Fixtures/'): data for name, data in resources.items() if name.startswith('Fixtures/')}
            == files(host.DATA), 'Fixtures differ from preserved originals')
    require(metadata['fixture_snapshot'] == host.fixture_snapshot(), 'Fixture snapshot/provenance mismatch')
    require(metadata['geometry_sha256'] == expected_geometry_hash(), 'Wrong geometry expectation')
    require(metadata['dependency_pins'] == {name: host.LOCK[name] for name in
            ('angle_revision', 'depot_tools_revision', 'bullet_url', 'bullet_sha512')}, 'Dependency pin changed')
    for name, digest in metadata['source_sha256_lf'].items():
        core.safe_name(name)
        source = (REPO / name).resolve()
        require(source.is_relative_to(REPO) and sha(source.read_bytes().replace(b'\r\n', b'\n')) == digest,
                'G1B source changed after preparation')
    require(metadata['adapter_sha256_lf'] == sha((G1A / 'src/GeometryAdapter.cpp').read_bytes().replace(b'\r\n', b'\n')),
            'G1A adapter changed')
    overlay = json.loads(resources['Provenance/ios-osg-overlay.json'])
    require(overlay['revision'] == host.LOCK['osg_revision'] and overlay['overlay_version'] == 2, 'Wrong OSG overlay')
    require(resources['Provenance/osg-lock.json'] == (ROOT / 'baseline/data/osg-lock.json').read_bytes(), 'Wrong OSG lock')
    bullet = json.loads(resources['Provenance/bullet-provenance.json'])
    require(bullet['archive_sha512'] == host.LOCK['bullet_sha512'] and bullet['source_url'] == host.LOCK['bullet_url'],
            'Wrong Bullet provenance')
    for name in host.GENERATED:
        require(bool(resources['Provenance/generated/' + name].strip()), 'Missing generated-header provenance')
    require({'Licenses/OpenMW-LICENSE.txt', 'Licenses/OSG-LICENSE.txt', 'Licenses/ANGLE/LICENSE', 'Licenses/Bullet-0.txt'}
            <= set(resources) and any(name.startswith('Licenses/OpenThreads/') for name in resources), 'Missing licenses')
    require(all(resources[name].strip() for name in ('Licenses/OpenMW-LICENSE.txt', 'Licenses/OSG-LICENSE.txt',
                'Licenses/ANGLE/LICENSE', 'Licenses/Bullet-0.txt')), 'Empty required license')
    angle = json.loads(resources['Provenance/ANGLE/angle-build.json'])
    require(angle['angle_revision'] == host.LOCK['angle_revision'] and angle['target'] == 'arm64-apple-ios18.0'
            and angle['metal_only'] is True and angle['validation'] == 'device-binary-and-sdk-passed'
            and angle['libraries'] == metadata['angle_libraries'], 'Wrong ANGLE validation/provenance')
    hashes = json.loads(resources['Provenance/ANGLE/package-hashes.json'])
    require(resources['Provenance/ANGLE/angle-lock.json'] ==
            (REPO / 'experiments/ios-angle-smoke/data/angle-lock.json').read_bytes(), 'Wrong ANGLE lock')
    require(resources['Provenance/ANGLE/args.gn'] ==
            (REPO / 'experiments/ios-angle-smoke/args.gn').read_bytes(), 'Wrong ANGLE build options')
    for name, data in resources.items():
        if name.startswith('Frameworks/'):
            require(hashes.get(name) == sha(data), 'ANGLE framework differs from verified package')
        elif name.startswith('Licenses/ANGLE/'):
            require(hashes.get('Licenses/' + name.removeprefix('Licenses/ANGLE/')) == sha(data), 'ANGLE notice differs from verified package')
        elif name.startswith('Provenance/ANGLE/') and not name.endswith('/package-hashes.json'):
            require(hashes.get(name.removeprefix('Provenance/ANGLE/')) == sha(data), 'ANGLE provenance package hash mismatch')
    require({name for name in hashes if name.startswith('Frameworks/')} ==
            {name for name in resources if name.startswith('Frameworks/')}, 'ANGLE framework inventory mismatch')
    header = (prepared / 'include/G1BExpectations.hpp').read_text()
    require('BuildSHA256[] = "' + sha(resources['g1b-build.json']) + '";' in header,
            'Prepared metadata differs from compiled contract')
    return resources, metadata


def native(data):
    details = core.macho(data)
    offset = 32
    count, size = struct.unpack_from('<II', data, 16)
    for _ in range(count):
        command, length = struct.unpack_from('<II', data, offset)
        require(length % 8 == 0 and command not in {0x24, 0x25, 0x2f, 0x30}, 'Ambiguous native metadata')
        if command == 0x32:
            require(length == 24 + 8 * struct.unpack_from('<I', data, offset + 20)[0], 'Malformed LC_BUILD_VERSION')
        offset += length
    require(offset == 32 + size, 'Malformed command extent')
    return details


def graph(entries, executable, roles, sdk):
    require(set(roles) == {'egl', 'gles'} and len(set(roles.values())) == 2, 'Expected distinct EGL/GLES providers')
    expected_binaries = {executable} | set(roles.values())
    require(all(path.startswith('Frameworks/') for path in roles.values()), 'ANGLE role outside Frameworks')
    binaries = {name: native(entry.data) for name, entry in entries.items() if entry.data.startswith(core.MACHO_MAGIC)}
    require(set(binaries) == expected_binaries, 'Unexpected/missing native binary inventory')
    for name, details in binaries.items():
        require(stat.S_ISREG(entries[name].mode) and entries[name].mode & 0o111, 'Nonexecutable native input')
        require(details['filetype'] == (2 if name == executable else 6), 'Wrong native product type')
        require(details['minimum_os'] == (18, 0, 0) if name == executable else details['minimum_os'] <= (18, 0, 0),
                'Wrong native deployment target')
        if name == executable:
            require(details['install_name'] is None and details['rpaths'] == ['@executable_path/Frameworks'],
                    'Unexpected application install-name/RPATH')
        else:
            require(details['install_name'] == '@rpath/' + name.removeprefix('Frameworks/'), 'Wrong ANGLE install-name')
            require(all(path in {'@loader_path', '@loader_path/..', '@executable_path/Frameworks', '@loader_path/Frameworks'}
                        for path in details['rpaths']), 'Unexpected ANGLE RPATH')
    dependencies, visited = [], set()

    def walk(loader, inherited=()):
        if loader in visited:
            return
        visited.add(loader)
        details = binaries[loader]
        paths = tuple(core.expand_path(path, loader, allow_root=True) for path in details['rpaths']) + inherited
        for name in details['dependencies']:
            require(not any(token in name for token in ('OpenGLES.framework', 'OpenGL.framework', 'MoltenVK',
                    'libvulkan', 'GL4ES')), 'Forbidden alternate graphics provider')
            record = {'loader': loader, 'dependency': name}
            if name.startswith('/'):
                # Same real selected-iPhoneOS-SDK TAPI/linker checks as the established ANGLE gate.
                require(name.startswith(('/usr/lib/', '/System/Library/Frameworks/')), 'Host dependency')
                record.update(core.system_dependency(name, sdk, '18.0') if sdk else {'availability': 'unverified'})
            else:
                candidates = ([core.normalize_bundle_path(path + '/' + name.removeprefix('@rpath/')) for path in paths]
                              if name.startswith('@rpath/') else [core.expand_path(name, loader)])
                target = next((path for path in candidates if path in binaries), None)
                require(target is not None, 'Unresolved bundled dependency: ' + name)
                record.update(target=target, kind='bundled')
                walk(target, paths)
            dependencies.append(record)
    walk(executable)
    require(visited == expected_binaries, 'Unreferenced ANGLE binary')
    return binaries, dependencies


def validate_bundle(entries, prepared, sdk=None):
    resources, metadata = prepared_resources(prepared)
    require(set(entries) == set(resources) | {'Info.plist', EXECUTABLE}, 'Exact bundle inventory mismatch')
    require(all(entries[name].data == data for name, data in resources.items()), 'Bundle resource bytes differ')
    roles = metadata['angle_libraries']
    binaries_expected = {EXECUTABLE} | set(roles.values())
    for name, entry in entries.items():
        core.safe_name(name)
        require(stat.S_ISREG(entry.mode) and '_CodeSignature' not in PurePosixPath(name).parts
                and PurePosixPath(name).suffix.lower() not in core.FORBIDDEN_SUFFIXES | {'.a'}, 'Nonregular/signed/static bundle input')
        if name not in binaries_expected:
            require(not entry.mode & 0o111 and not entry.data.startswith(core.MACHO_MAGIC), 'Executable resource')
    info = plistlib.loads(entries['Info.plist'].data)
    require(info.get('CFBundleExecutable') == EXECUTABLE and info.get('CFBundleIdentifier') == BUNDLE_ID
            and info.get('CFBundlePackageType') == 'APPL', 'Wrong G1B identity')
    require(info.get('CFBundleSupportedPlatforms') == ['iPhoneOS'] and info.get('UIDeviceFamily') == [1]
            and info.get('LSRequiresIPhoneOS') is True and core.version_tuple(info.get('MinimumOSVersion')) == (18, 0, 0),
            'Wrong bundle platform/deployment')
    require(info.get('UIFileSharingEnabled') is True and info.get('LSSupportsOpeningDocumentsInPlace') is True
            and isinstance(info.get('UILaunchScreen'), dict), 'Missing launch/export settings')
    require(not any(key in info for key in ('UIMainStoryboardFile', 'UILaunchStoryboardName')), 'Unexpected storyboard')
    scene = info.get('UIApplicationSceneManifest', {})
    require(scene.get('UIApplicationSupportsMultipleScenes') is False and scene.get('UISceneConfigurations', {})
            .get('UIWindowSceneSessionRoleApplication') ==
            [{'UISceneConfigurationName': 'Default', 'UISceneDelegateClassName': 'G1BSceneDelegate'}], 'Wrong scene delegate')
    for path in roles.values():
        framework = plistlib.loads(entries[str(PurePosixPath(path).parent / 'Info.plist')].data)
        require(framework.get('CFBundleExecutable') == PurePosixPath(path).name
                and framework.get('CFBundlePackageType') == 'FMWK'
                and framework.get('CFBundleSupportedPlatforms') == ['iPhoneOS'], 'Wrong framework plist')
    binaries, dependencies = graph(entries, EXECUTABLE, roles, sdk)
    require({'/System/Library/Frameworks/UIKit.framework/UIKit', '/System/Library/Frameworks/Foundation.framework/Foundation'}
            <= set(binaries[EXECUTABLE]['dependencies']), 'Missing UIKit/Foundation linkage')
    require(sha(resources['g1b-build.json']).encode() in entries[EXECUTABLE].data, 'Executable lacks metadata contract')
    return {'valid': True, 'binaries': binaries, 'dependencies': dependencies, 'source_commit': metadata['source_commit'],
            'sdk_availability_checked': sdk is not None, 'scope': 'G1B binary/package validation; physical rendering unverified'}


def collect_bundle(path):
    entries = core.collect_bundle(path)
    parents = {str(parent) for name in entries for parent in PurePosixPath(name).parents if str(parent) != '.'}
    for entry in path.rglob('*'):
        require(entry.is_file() or entry.is_dir(), 'Nonregular bundle entry')
        if entry.is_dir():
            require(entry.relative_to(path).as_posix() in parents, 'Unexpected/empty bundle directory')
    return entries


def validate_ipa(path, prepared, sdk=None, expected=None):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len({entry.filename for entry in entries}) == len(entries) and archive.testzip() is None, 'Duplicate/corrupt IPA')
        require({'Payload/', PREFIX} <= {entry.filename for entry in entries}, 'Missing IPA root directories')
        content, directories = {}, set()
        for entry in entries:
            name = entry.filename.rstrip('/')
            core.safe_name(name)
            require(name in {'Payload', PREFIX.rstrip('/')} or name.startswith(PREFIX), 'Unexpected IPA root')
            mode = entry.external_attr >> 16
            require(not stat.S_ISLNK(mode) and not entry.flag_bits & 1, 'Linked/encrypted IPA entry')
            if entry.is_dir():
                require(stat.S_ISDIR(mode), 'Wrong IPA directory mode')
                directories.add(name)
            else:
                require(entry.filename.startswith(PREFIX), 'File outside app')
                content[name[len(PREFIX):]] = Entry(archive.read(entry), mode)
        parents = {'Payload', PREFIX.rstrip('/')} | {PREFIX + str(parent) for name in content
                    for parent in PurePosixPath(name).parents if str(parent) != '.'}
        require(directories <= parents, 'Unexpected/empty IPA directory')
        report = validate_bundle(content, prepared, sdk)
        require(expected is None or content == expected, 'Reopened IPA differs from validated bundle')
    report.update(unsigned=True, sha256=sha(path.read_bytes()))
    return report


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('phase', choices=('link', 'bundle', 'ipa', 'reopen'))
    for name in ('product', 'prepared', 'sdk', 'evidence'):
        cli.add_argument('--' + name, type=Path, required=True)
    cli.add_argument('--output', type=Path)
    args = cli.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        core.check_sdk(args.sdk)
        if args.phase == 'reopen':
            report = validate_ipa(args.product, args.prepared, args.sdk)
            outputs = {}
        elif args.phase == 'link':
            require(args.product.is_file() and not args.product.is_symlink(), 'Link product must be a regular file')
            resources, metadata = prepared_resources(args.prepared)
            entries = {name: Entry(data, stat.S_IFREG | (0o755 if name in metadata['angle_libraries'].values() else 0o644))
                       for name, data in resources.items() if name.startswith('Frameworks/')}
            entries[args.product.name] = Entry(args.product.read_bytes(), args.product.stat().st_mode)
            binaries, dependencies = graph(entries, args.product.name, metadata['angle_libraries'], args.sdk)
            report = {'valid': True, 'binaries': binaries, 'dependencies': dependencies, 'scope': 'Device link only; no runtime claim'}
            outputs = core.inspect_dependencies(args.product.parent, {'binaries': {args.product.name: binaries[args.product.name]}})
        else:
            entries = collect_bundle(args.product)
            report = validate_bundle(entries, args.prepared, args.sdk)
            outputs = core.inspect_dependencies(args.product, report)
            if args.phase == 'ipa':
                require(args.output is not None, 'IPA output required')
                args.output.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix='.ipa.tmp', delete=False) as handle:
                    temporary = Path(handle.name)
                core.write_ipa(entries, temporary)
                report = validate_ipa(temporary, args.prepared, args.sdk, entries)
                os.replace(temporary, args.output)
                temporary = None
        (args.evidence / (args.phase + '-otool.txt')).write_text('\n'.join(outputs.values()))
        (args.evidence / (args.phase + '.json')).write_text(json.dumps(report, indent=2) + '\n')
    except Exception as error:
        (args.evidence / (args.phase + '.json')).write_text(json.dumps({'valid': False, 'error': str(error)}) + '\n')
        raise
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
