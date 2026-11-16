"""Acquire/verify genuine G6 dependency sources; no installation or tool execution."""
import argparse
import hashlib
import io
import json
import shutil
import ssl
import tarfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def inventory(root):
    files = {}
    for path in root.rglob('*'):
        if path.is_symlink():
            raise ValueError('Dependency symlink: ' + str(path))
        if path.is_file():
            files[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return files


def entries(raw, archive, ignored=()):
    if archive.endswith('.zip'):
        with zipfile.ZipFile(io.BytesIO(raw)) as stream:
            for item in stream.infolist():
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Dependency archive symlink')
                yield item.filename, None if item.is_dir() else stream.read(item)
    else:
        with tarfile.open(fileobj=io.BytesIO(raw), mode='r:*') as stream:
            for item in stream:
                if item.name in ignored:
                    if not item.issym():
                        raise ValueError('Expected unused Android symlink changed')
                    continue
                if not (item.isfile() or item.isdir()):
                    raise ValueError('Dependency archive special member')
                yield item.name, stream.extractfile(item).read() if item.isfile() else None


def acquire(output, offline=False, cafile=None):
    lock = json.loads((ROOT / 'dependencies.json').read_text())
    output.mkdir(parents=True, exist_ok=True)
    result = {}
    for name, rule in lock.items():
        archive = output / rule['archive']
        if not archive.exists() and not offline:
            context = ssl.create_default_context(cafile=str(cafile) if cafile else None)
            with urllib.request.urlopen(rule['url'], context=context, timeout=120) as response:
                raw = response.read(rule['bytes'] + 1)
            if len(raw) != rule['bytes'] or hashlib.new(rule['algorithm'], raw).hexdigest() != rule['hash']:
                raise ValueError('Dependency download size/hash mismatch: ' + name)
            archive.write_bytes(raw)
        raw = archive.read_bytes()
        if len(raw) != rule['bytes'] or hashlib.new(rule['algorithm'], raw).hexdigest() != rule['hash']:
            raise ValueError('Dependency archive size/hash mismatch: ' + name)
        expected = {}
        for member, value in entries(raw, rule['archive'], rule.get('ignored_android_symlinks', ())):
            path = PurePosixPath(member)
            if path.is_absolute() or '..' in path.parts or '\\' in member or ':' in member:
                raise ValueError('Unsafe dependency archive path')
            parts = path.parts
            if rule.get('prefix'):
                if not parts or parts[0] != rule['prefix']:
                    raise ValueError('Unexpected dependency root')
                parts = parts[1:]
            if value is None or not parts:
                continue
            relative = '/'.join(parts)
            if rule.get('include_prefixes') and not any(
                    relative.startswith(prefix) for prefix in rule['include_prefixes']):
                continue
            if relative in expected:
                raise ValueError('Duplicate dependency member')
            expected[relative] = hashlib.sha256(value).hexdigest()
            target = output / rule['directory'] / relative
            if not offline and not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value)
        source = output / rule['directory']
        if inventory(source) != expected:
            raise ValueError('Dependency extracted inventory/hash mismatch: ' + name)
        result[name] = {'source': str(source.resolve()), 'archive': rule, 'files': expected}
    report = output / 'g6-dependencies.json'
    raw_report = (json.dumps(result, indent=2) + '\n').encode('utf-8')
    if not report.exists() or report.read_bytes() != raw_report:
        report.write_bytes(raw_report)
    return result


def mygui_view(source, output):
    if output.resolve().is_relative_to(source.resolve()) or source.resolve().is_relative_to(output.resolve()):
        raise ValueError('MyGUI source and view directories must be separate')
    # G4's archive verifier checks the entire unmodified original MyGUI tree.
    # Do not link this ABI view against an unmodified/prebuilt MyGUI library.
    original = source / 'MyGUI_UString.h'
    raw = original.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '58bab3e34ea4c0041e7c87ec14362ae3ba29f2899766e733202641d6de695296':
        raise ValueError('Pinned MyGUI UString source mismatch')
    from prepare import replace_once, write_if_changed
    text = raw.decode('utf-8-sig')
    text = replace_once(text, 'using unicode_char = uint32;', 'using unicode_char = char32_t;')
    text = replace_once(text, 'using code_point = uint16;', 'using code_point = char16_t;')
    output.mkdir(parents=True, exist_ok=True)
    expected = inventory(source)
    for name in expected:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name == 'MyGUI_UString.h':
            write_if_changed(target, text.encode('utf-8'))
        else:
            write_if_changed(target, (source / name).read_bytes())
    expected['MyGUI_UString.h'] = hashlib.sha256(text.encode()).hexdigest()
    if inventory(output) != expected:
        raise ValueError('MyGUI compatibility-view inventory mismatch')
    return expected


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--cafile', type=Path)
    args = parser.parse_args()
    result = acquire(args.output, args.offline, args.cafile)
    print(json.dumps({name: item['source'] for name, item in result.items()}, indent=2))
