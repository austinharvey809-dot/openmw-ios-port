"""Strict unsigned UIKit data-app/link validation using existing read-only SDK/Mach-O helpers.

No signing, binary rewriting, fetching or rendering dependency is introduced.
Portable --validate-only checks archive/resources/metadata, without claiming SDK availability.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import plistlib
import re
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
HELPER = REPO / 'experiments/ios-angle-smoke/tools/package_ios.py'
SPEC = importlib.util.spec_from_file_location('_openmw_data_smoke_sdk_packaging', HELPER)
core = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = core  # dataclass resolves its defining module during import.
SPEC.loader.exec_module(core)

Entry, ValidationError, require = core.Entry, core.ValidationError, core.require
APP_NAME = 'IOSOpenMWDataSmoke.app'
EXECUTABLE = 'IOSOpenMWDataSmoke'
BUNDLE_ID = 'org.openmw.experiments.ios-openmw-data-smoke'
PREFIX = 'Payload/' + APP_NAME + '/'
OSG_REVISION = '9b384d5439977784e5cd250ff8ff7966928ddd27'
REFERENCE = ROOT / 'data/fixtures.json'
REQUIRED = ('Info.plist', EXECUTABLE, 'Fixtures/valid.esm', 'Fixtures/base.bsa',
            'Fixtures/fixtures.json', 'data-build.json', 'Licenses/OpenMW-LICENSE.txt', 'Licenses/OSG-LICENSE.txt')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_object(data, label):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate ' + label + ' key: ' + key)
            result[key] = value
        return result
    try:
        result = json.loads(data, object_pairs_hook=unique_object)
    except (ValueError, UnicodeError) as error:
        raise ValidationError('Invalid ' + label) from error
    require(isinstance(result, dict), label + ' must be an object')
    return result


def validate_device_executable(data):
    """Metadata validation only: no claim of successful native link/runtime."""
    details = core.macho(data)
    require(details['filetype'] == 2, 'Expected MH_EXECUTE device executable')
    require(details['minimum_os'] == (18, 0, 0), 'Executable minimum deployment target must be iOS 18.0')
    require(not details['rpaths'], 'Static-only data executable must not contain LC_RPATH')
    require(details['install_name'] is None, 'Executable must not have a dylib install name')
    # Reject conflicting legacy metadata rather than ignoring commands that the
    # inherited application parser does not need for graphics bundle validation.
    count, size = struct.unpack_from('<II', data, 16)
    offset = 32
    for _ in range(count):
        command, length = struct.unpack_from('<II', data, offset)
        require(length % 8 == 0, 'Misaligned executable load command')
        require(command not in {0x24, 0x25, 0x2F, 0x30}, 'Legacy/ambiguous executable platform metadata')
        if command == 0x32:
            tools = struct.unpack_from('<I', data, offset + 20)[0]
            require(length == 24 + 8 * tools, 'Malformed executable LC_BUILD_VERSION')
        offset += length
    require(offset == 32 + size, 'Inconsistent executable load commands')
    for dependency in details['dependencies']:
        require(dependency.startswith(('/usr/lib/', '/System/Library/Frameworks/')),
                'Non-system or build-host executable dependency: ' + dependency)
        require(not any(token in dependency for token in ('OpenGLES.framework', 'OpenGL.framework', 'Metal.framework',
                'MoltenVK', 'libvulkan', 'GL4ES', 'libEGL', 'libGLES', 'osg.framework')),
                'Unexpected rendering dependency in data-only executable: ' + dependency)
    return details


def resolve_system_dependencies(details, sdk=None):
    if sdk is not None:
        core.check_sdk(sdk)
    result = []
    for name in details['dependencies']:
        record = {'dependency': name}
        record.update(core.system_dependency(name, sdk, '18.0') if sdk is not None
                      else {'kind': 'system-availability-not-checked'})
        result.append(record)
    return result


def validate_bundle(files, sdk=None):
    for name, entry in files.items():
        core.safe_name(name)
        require(stat.S_ISREG(entry.mode), 'Bundle entry is not a regular file: ' + name)
        require('_CodeSignature' not in PurePosixPath(name).parts
                and PurePosixPath(name).suffix.lower() not in core.FORBIDDEN_SUFFIXES,
                'Signing/provisioning material forbidden in unsigned bundle: ' + name)
        require(not name.startswith('Frameworks/') and not any(part.endswith('.framework') for part in PurePosixPath(name).parts)
                and PurePosixPath(name).suffix.lower() not in {'.a', '.dylib'},
                'Static data application must not bundle libraries/frameworks: ' + name)
        if name != EXECUTABLE:
            require(not entry.mode & 0o111, 'Unexpected executable resource: ' + name)
            require(not entry.data.startswith((core.MACHO_MAGIC, b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf',
                    b'\xca\xfe\xba\xbe', b'\xbe\xba\xfe\xca', b'\xce\xfa\xed\xfe')),
                    'Unexpected additional native binary: ' + name)
    require(all(name in files for name in REQUIRED), 'Missing required data application resource')
    try:
        info = plistlib.loads(files['Info.plist'].data)
    except (ValueError, plistlib.InvalidFileException) as error:
        raise ValidationError('Invalid Info.plist') from error
    require(isinstance(info, dict), 'Info.plist must be a dictionary')
    require(info.get('CFBundleExecutable') == EXECUTABLE, 'Mismatched CFBundleExecutable')
    require(info.get('CFBundleIdentifier') == BUNDLE_ID and info.get('CFBundlePackageType') == 'APPL', 'Wrong application identity/type')
    require(info.get('CFBundleSupportedPlatforms') == ['iPhoneOS'] and info.get('UIDeviceFamily') == [1]
            and info.get('LSRequiresIPhoneOS') is True, 'Not an iPhone device application')
    require(core.version_tuple(info.get('MinimumOSVersion')) == (18, 0, 0), 'Info.plist must require iOS 18.0')
    require(isinstance(info.get('UILaunchScreen'), dict)
            and not any(key in info for key in ('UIMainStoryboardFile', 'UILaunchStoryboardName')), 'Expected inline launch-screen configuration')
    require(info.get('UIFileSharingEnabled') is True and info.get('LSSupportsOpeningDocumentsInPlace') is True,
            'Diagnostic file export configuration missing')
    scenes = info.get('UIApplicationSceneManifest', {})
    require(isinstance(scenes, dict) and scenes.get('UIApplicationSupportsMultipleScenes') is False, 'Expected single application scene')
    configurations = scenes.get('UISceneConfigurations', {})
    require(isinstance(configurations, dict), 'Invalid scene configurations')
    delegates = configurations.get('UIWindowSceneSessionRoleApplication', [])
    require(isinstance(delegates, list) and len(delegates) == 1 and isinstance(delegates[0], dict)
            and delegates[0].get('UISceneDelegateClassName') == 'DataSceneDelegate', 'Expected DataSceneDelegate configuration')
    require(files[EXECUTABLE].mode & 0o111, 'Application executable lacks executable permissions')
    details = validate_device_executable(files[EXECUTABLE].data)
    require({'/System/Library/Frameworks/UIKit.framework/UIKit', '/System/Library/Frameworks/Foundation.framework/Foundation'}
            <= set(details['dependencies']), 'Missing required UIKit/Foundation dependency')
    reference = REFERENCE.read_bytes()
    require(files['Fixtures/fixtures.json'].data == reference, 'Bundled fixture manifest differs from reviewed source')
    manifest = json_object(reference, 'fixture manifest')
    require(manifest.get('schema_version') == 1 and isinstance(manifest.get('inputs'), dict)
            and set(manifest['inputs']) == {'valid.esm', 'base.bsa'}, 'Invalid deterministic fixture inventory')
    for name, expected in manifest['inputs'].items():
        data = files['Fixtures/' + name].data
        require(isinstance(expected, dict) and type(expected.get('size')) is int
                and expected['size'] == len(data) and expected.get('sha256') == sha(data),
                'Bundled fixture size/hash mismatch: ' + name)
    resource = manifest.get('resource')
    require(isinstance(resource, dict) and all(isinstance(resource.get(key), str) and resource[key]
            for key in ('id', 'model', 'key', 'hex', 'sha256')), 'Invalid expected synthetic resource metadata')
    try:
        payload = bytes.fromhex(resource['hex'])
    except ValueError as error:
        raise ValidationError('Invalid expected synthetic payload hex') from error
    require(type(resource.get('size')) is int and resource['size'] == len(payload)
            and resource['sha256'] == sha(payload), 'Expected payload size/hash mismatch')
    build = json_object(files['data-build.json'].data, 'data build provenance')
    require(isinstance(build.get('source_commit'), str) and re.fullmatch(r'[0-9a-f]{40}', build['source_commit']), 'Invalid source commit')
    require(build.get('osg_revision') == OSG_REVISION and type(build.get('genuine_engine_units')) is int
            and build['genuine_engine_units'] == 20 and type(build.get('registration_helper_units')) is int
            and build['registration_helper_units'] == 1
            and build.get('scope') == 'prepared source provenance; not device runtime proof', 'Wrong source inventory/OSG provenance')
    for name in ('Licenses/OpenMW-LICENSE.txt', 'Licenses/OSG-LICENSE.txt'):
        require(bool(files[name].data.strip()), 'Missing license text: ' + name)
    return {'bundle_identifier': BUNDLE_ID, 'executable': EXECUTABLE, 'architecture': 'arm64', 'platform': 'IOS',
            'minimum_os': '18.0', 'required_resources': list(REQUIRED), 'source_commit': build['source_commit'],
            'osg_revision': OSG_REVISION, 'fixture_manifest_sha256': sha(reference), 'resource_sha256': resource['sha256'],
            'binaries': {EXECUTABLE: details}, 'dependencies': resolve_system_dependencies(details, sdk),
            'sdk_availability_checked': sdk is not None, 'scope': 'Unsigned device executable packaging; no physical runtime proof'}


def collect_bundle(app):
    require(app.is_dir() and not app.is_symlink() and app.name == APP_NAME, 'Expected ' + APP_NAME)
    files = {}
    for path in sorted(app.rglob('*')):
        require(not path.is_symlink(), 'Symlink in application: ' + str(path))
        if path.is_file():
            files[path.relative_to(app).as_posix()] = Entry(path.read_bytes(), path.stat().st_mode)
    return files


def write_ipa(files, destination):
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for directory in ('Payload/', PREFIX):
            entry = zipfile.ZipInfo(directory); entry.create_system = 3
            entry.external_attr = (stat.S_IFDIR | 0o755) << 16
            archive.writestr(entry, b'')
        for name, source in sorted(files.items()):
            core.safe_name(name)
            entry = zipfile.ZipInfo(PREFIX + name); entry.create_system = 3
            entry.external_attr = (stat.S_IFREG | stat.S_IMODE(source.mode)) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, source.data)


def validate_ipa(path, sdk=None, expected=None):
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        require(len({entry.filename for entry in entries}) == len(entries), 'Duplicate IPA archive entries')
        require(archive.testzip() is None, 'IPA CRC check failed')
        files = {}
        require({'Payload/', PREFIX} <= {entry.filename for entry in entries}, 'Missing Payload/application directory structure')
        for entry in entries:
            name = entry.filename.rstrip('/')
            core.safe_name(name)
            require(name in {'Payload', PREFIX.rstrip('/')} or name.startswith(PREFIX), 'Unexpected IPA application/root: ' + name)
            mode = entry.external_attr >> 16
            require(not stat.S_ISLNK(mode) and not entry.flag_bits & 1, 'Symlink/encrypted IPA entry: ' + name)
            if entry.is_dir():
                require(stat.S_ISDIR(mode), 'Invalid IPA directory permissions: ' + name)
            else:
                require(entry.filename.startswith(PREFIX), 'File outside IPA application: ' + name)
                files[name[len(PREFIX):]] = Entry(archive.read(entry), mode)
        report = validate_bundle(files, sdk)
        if expected is not None:
            require(files == expected, 'IPA contents/permissions differ from validated bundle')
        report.update(archive_root=PREFIX, files=len(files), sha256=sha(path.read_bytes()), unsigned=True)
        return report


def write_checksums(evidence):
    rows = [sha(p.read_bytes()) + '  ' + p.relative_to(evidence).as_posix()
            for p in sorted(evidence.rglob('*')) if p.is_file() and p.name != 'SHA256SUMS']
    (evidence / 'SHA256SUMS').write_text('\n'.join(rows) + '\n', encoding='utf-8')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--app', type=Path)
    group.add_argument('--validate-only', type=Path, metavar='IPA')
    group.add_argument('--link-executable', type=Path)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args(argv)
    args.evidence.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        if args.app:
            require(args.sdk is not None and args.output is not None, 'Packaging requires --sdk and --output')
            files = collect_bundle(args.app)
            report = validate_bundle(files, args.sdk)
            outputs = core.inspect_dependencies(args.app, report)
            (args.evidence / 'otool-L.txt').write_text('\n'.join(outputs.values()), encoding='utf-8')
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=args.output.parent, suffix='.ipa.tmp', delete=False) as handle:
                temporary = Path(handle.name)
            write_ipa(files, temporary)
            report = validate_ipa(temporary, args.sdk, files)
            os.replace(temporary, args.output); temporary = None
            report['ipa'] = str(args.output)
        elif args.link_executable:
            require(args.sdk is not None and args.output is None, 'Link inspection requires --sdk and no --output')
            details = validate_device_executable(args.link_executable.read_bytes())
            report = {'valid': True, 'executable': args.link_executable.name,
                      'binaries': {args.link_executable.name: details},
                      'dependencies': resolve_system_dependencies(details, args.sdk),
                      'sdk_availability_checked': True, 'sha256': sha(args.link_executable.read_bytes()),
                      'scope': 'Observed iPhoneOS executable artifact/link metadata only; no device runtime proof'}
            outputs = core.inspect_dependencies(args.link_executable.parent, report)
            (args.evidence / 'otool-L.txt').write_text('\n'.join(outputs.values()), encoding='utf-8')
        else:
            require(args.output is None, '--validate-only does not write an IPA')
            report = validate_ipa(args.validate_only, args.sdk)
            report['ipa'] = str(args.validate_only)
        report['valid'] = True
        (args.evidence / 'validation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps({'valid': True, 'scope': report['scope'], 'sdk_availability_checked': report['sdk_availability_checked']}, indent=2))
        return 0
    except (ValidationError, OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        (args.evidence / 'validation.json').write_text(json.dumps({'valid': False, 'error': str(error)}, indent=2) + '\n', encoding='utf-8')
        print('Data smoke validation failed:', error)
        return 1
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        write_checksums(args.evidence)


if __name__ == '__main__':
    raise SystemExit(main())
