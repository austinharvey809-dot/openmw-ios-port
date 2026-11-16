"""Explicit local original-content inspection. Never copy game data or run in CI."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_cases import child_fault_capture, retained

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def capture(command):
    started = time.monotonic()
    with child_fault_capture():
        process = subprocess.Popen([str(x) for x in command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            stdout, stderr = process.communicate(timeout=120)
        except subprocess.TimeoutExpired:
            process.kill(); stdout, stderr = process.communicate()
            raise RuntimeError('Private native inspection timed out')
        memory = {'status': 'UNVERIFIED', 'scope': 'Windows CPU process only, not iOS physical footprint'}
        if os.name == 'nt':
            class Counters(ctypes.Structure):
                _fields_ = [('cb', ctypes.c_uint32), ('pageFaults', ctypes.c_uint32)] + [
                    (name, ctypes.c_size_t) for name in ('peakWorkingSet', 'workingSet', 'peakPagedPool',
                        'pagedPool', 'peakNonpagedPool', 'nonpagedPool', 'pagefile', 'peakPagefile', 'privateBytes')]
            function = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
            function.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_uint32]
            function.restype = ctypes.c_int
            counters = Counters(); counters.cb = ctypes.sizeof(counters)
            if function(int(process._handle), ctypes.byref(counters), counters.cb):
                memory.update(status='MEASURED', peak_working_set_bytes=counters.peakWorkingSet,
                    peak_pagefile_bytes=counters.peakPagefile)
    row = {'exit': process.returncode, 'stdout': stdout.decode(errors='replace'),
        'stderr': stderr.decode(errors='replace'), 'elapsed_seconds': time.monotonic() - started,
        'binary_sha256': digest(Path(command[0])), 'memory': memory}
    if process.returncode != 0:
        raise RuntimeError('Private native failure exit=' + hex(process.returncode & 0xffffffff) + ': ' + row['stderr'][-4000:])
    row['result'] = json.loads(row['stdout'])
    if row['result'].get('status') != 'PASS':
        raise ValueError('Private native report did not pass')
    return row


def run(data, build, shaders, output, plugins):
    if os.environ.get('CI'):
        raise ValueError('Private asset inspection is local only; never run in CI')
    output.mkdir(parents=True, exist_ok=True)
    for name in plugins:
        if Path(name).name != name or '/' in name or '\\' in name:
            raise ValueError('Private plugins must be filenames')
    names = ['Morrowind.esm', 'Morrowind.bsa', *plugins]
    before = {name: digest(data / name) for name in names}
    suffix = '.exe' if os.name == 'nt' else ''
    rows = {}
    try:
        rows['live-ownership'] = capture([build / ('openmw-g6-live-check' + suffix), data,
            REPO / 'files/settings-default.cfg', 'private', *plugins])
        # Shared renderer's actual private stream/door probe uses its original
        # single-content profile. Multiple-content ownership is checked above.
        if not plugins:
            rows['world-streaming'] = capture([build / ('openmw-g6-world-check' + suffix), data, shaders, 'inspect-stream'])
            rows['interior'] = capture([build / ('openmw-g6-world-check' + suffix), data, shaders,
                "inspect-interior:Seyda Neen, Fargoth's House"])
    finally:
        after = {name: digest(data / name) for name in names}
        report = {'schema': 1, 'platform': sys.platform, 'private_content_sha256': before,
            'private_inputs_unchanged': before == after, 'ordered_plugins': plugins, 'results': rows,
            'scope': 'Local CPU live ownership / genuine resource and scene graph only; no Apple or GPU execution'}
        retained.save(output / 'private-results.json', report)
    if before != after:
        raise ValueError('Original private asset bytes changed')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('private-data', 'build', 'shaders', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--plugin', action='append', default=[])
    args = parser.parse_args()
    result = run(args.private_data, args.build, args.shaders, args.output, args.plugin)
    print(json.dumps({'status': 'PASS', 'private_inputs_unchanged': result['private_inputs_unchanged'],
        'cases': list(result['results']), 'evidence': str(args.output / 'private-results.json')}, indent=2))
