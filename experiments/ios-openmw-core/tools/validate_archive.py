"""Strict, stdlib-only validation of the five-source iPhoneOS static archive."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import struct
import subprocess

SOURCES = (
    'components/files/conversion.cpp',
    'components/files/openfile.cpp',
    'components/files/constrainedfilestreambuf.cpp',
    'components/platform/fileposix.cpp',
    'components/vfs/manager.cpp',
)
SYMBOL_TABLES = {'/', '/SYM64/', '__.SYMDEF', '__.SYMDEF SORTED', '__.SYMDEF_64', '__.SYMDEF_64 SORTED'}


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def archive_objects(data):
    """Read BSD ar (Xcode/libtool) and GNU name tables without shell extraction."""
    require(data.startswith(b'!<arch>\n'), 'Expected a regular static archive, not a fat archive or raw object')
    offset, names, objects, long_names = 8, set(), [], b''
    while offset < len(data):
        require(offset + 60 <= len(data), 'Truncated archive header')
        header = data[offset:offset + 60]
        require(header[58:] == b'`\n', 'Invalid archive member header')
        try:
            size = int(header[48:58].decode('ascii').strip())
            name = header[:16].decode('ascii').strip()
        except (ValueError, UnicodeError) as error:
            raise ValidationError('Invalid archive name/size') from error
        require(size >= 0, 'Negative archive member size')
        offset += 60
        require(offset + size <= len(data), 'Truncated archive member')
        payload = data[offset:offset + size]
        offset += size
        if size % 2:
            require(offset < len(data) and data[offset:offset + 1] == b'\n', 'Missing archive padding')
            offset += 1
        if name == '//':
            require(not long_names, 'Duplicate GNU archive name table')
            long_names = payload
            continue
        if name.startswith('#1/'):
            try:
                length = int(name[3:])
                require(0 < length <= len(payload), 'Invalid BSD extended name length')
                name = payload[:length].rstrip(b'\0').decode('utf-8')
                payload = payload[length:]
            except (ValueError, UnicodeError) as error:
                raise ValidationError('Invalid BSD archive member name') from error
        elif name.startswith('/') and name not in SYMBOL_TABLES:
            try:
                index = int(name[1:])
                require(0 <= index < len(long_names), 'Invalid GNU archive name offset')
                end = long_names.find(b'/\n', index)
                require(end >= index, 'Unterminated GNU archive member name')
                name = long_names[index:end].decode('utf-8')
            except (ValueError, UnicodeError) as error:
                raise ValidationError('Invalid GNU archive member name') from error
        elif name not in SYMBOL_TABLES:
            name = name.removesuffix('/')
        if name in SYMBOL_TABLES:
            continue
        require(name and '/' not in name and '\\' not in name and '\0' not in name
                and name not in {'.', '..'}, 'Unsafe archive member name')
        require(name not in names, 'Duplicate archive object: ' + name)
        names.add(name)
        objects.append((name, payload))
    require(objects, 'Archive contains no objects')
    return objects


def inspect_object(data):
    require(len(data) >= 32, 'Truncated Mach-O object')
    magic, cpu, subtype, kind, count, size, flags, reserved = struct.unpack_from('<8I', data)
    require(magic == 0xFEEDFACF, 'Expected a little-endian 64-bit Mach-O object (bitcode/fat input rejected)')
    require(cpu == 0x0100000C and subtype == 0, 'Object must be ordinary ARM64, not x86_64 or arm64e')
    require(kind == 1, 'Archive member is not MH_OBJECT')
    require(0 < count <= size // 8 and 32 + size <= len(data), 'Invalid Mach-O command inventory')
    offset, build = 32, None
    for _ in range(count):
        require(offset + 8 <= 32 + size, 'Truncated Mach-O load command')
        command, length = struct.unpack_from('<II', data, offset)
        require(length >= 8 and length % 8 == 0 and offset + length <= 32 + size, 'Invalid Mach-O command size')
        require(command not in {0x24, 0x25, 0x2F, 0x30}, 'Legacy/ambiguous platform command rejected; LC_BUILD_VERSION required')
        if command == 0x32:
            require(build is None and length >= 24, 'Missing/duplicate build-version metadata')
            target, minimum, sdk, tools = struct.unpack_from('<4I', data, offset + 8)
            require(length == 24 + 8 * tools, 'Malformed LC_BUILD_VERSION tools')
            require(target == 2, 'Object platform is not iOS device (macOS/simulator/Catalyst rejected)')
            require(minimum == (18 << 16), 'Object deployment target is not exactly iOS 18.0')
            build = {'architecture': 'arm64', 'platform': 'IOS', 'minimum_os': '18.0',
                     'sdk': f'{sdk >> 16}.{(sdk >> 8) & 255}.{sdk & 255}'}
        offset += length
    require(offset == 32 + size and build is not None, 'Missing/inconsistent iOS build metadata')
    return build


def validate(data):
    expected = {Path(source).name: source for source in SOURCES}
    found, result = set(), []
    for name, payload in archive_objects(data):
        # Xcode typically names foo.o; other CMake generators use foo.cpp.o.
        candidates = [source for base, source in expected.items()
                      if name in {base + '.o', base.removesuffix('.cpp') + '.o'}]
        require(len(candidates) == 1, 'Unexpected object outside the five-source target: ' + name)
        source = candidates[0]
        require(source not in found, 'Multiple objects for the same translation unit: ' + source)
        found.add(source)
        result.append({'member': name, 'source': source, 'sha256': hashlib.sha256(payload).hexdigest(),
                       **inspect_object(payload)})
    require(found == set(SOURCES), 'Archive does not contain exactly the five OpenMW translation units')
    return {'valid': True, 'sha256': hashlib.sha256(data).hexdigest(), 'objects': result,
            'scope': 'Static data-component compilation only; no iPhone or Engine execution'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    report = args.evidence / 'archive-validation.json'

    def tool(arguments, log):
        completed = subprocess.run(['xcrun', *arguments], capture_output=True, text=True)
        with log.open('a', encoding='utf-8') as stream:
            stream.write('$ xcrun ' + ' '.join(map(str, arguments)) + '\n')
            stream.write(completed.stdout + completed.stderr)
        require(completed.returncode == 0, f'xcrun {arguments[0]} failed; see {log.name}')
        return completed.stdout.strip()

    try:
        require(platform.system() == 'Darwin', 'Native archive inspection requires existing macOS Xcode tools')
        data = args.archive.read_bytes()
        objects = archive_objects(data)
        log = args.evidence / 'archive-tools.log'
        tool(['lipo', str(args.archive), '-info'], log)
        require(tool(['lipo', str(args.archive), '-archs'], log) == 'arm64', 'Archive contains architectures other than ARM64')
        tool(['lipo', str(args.archive), '-verify_arch', 'arm64'], log)
        tool(['ar', '-t', str(args.archive)], log)
        # Validate names before writing any extracted objects. Keep raw metadata
        # even for platform failures; never use ar to extract archive paths.
        output = args.evidence / 'objects'
        output.mkdir(exist_ok=True)
        for index, (name, payload) in enumerate(objects):
            path = output / f'{index:02d}-{name}'
            path.write_bytes(payload)
            tool(['otool', '-hv', str(path)], output / f'{path.name}.otool.txt')
            tool(['otool', '-l', str(path)], output / f'{path.name}.otool.txt')
        result = validate(data)
        report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValidationError) as error:
        report.write_text(json.dumps({'valid': False, 'error': str(error)}, indent=2) + '\n', encoding='utf-8')
        print('Data-core archive validation failed:', error)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
