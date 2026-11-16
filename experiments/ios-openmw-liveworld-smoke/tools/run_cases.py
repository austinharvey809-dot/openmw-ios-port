"""Genuine live-world cases, with retained exact native failure diagnostics."""
import argparse
from contextlib import contextmanager
import importlib.util
import json
import os
import struct
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
G4 = REPO / 'experiments/ios-openmw-world-smoke'
sys.path.insert(0, str(G4 / 'tools'))
import fixtures
spec = importlib.util.spec_from_file_location('_g6_retained_native_runner', G4 / 'tools/run_cases.py')
retained = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retained)

POSITIVE = {'ownership': 9, 'transform': 10, 'enabled': 9, 'count': 12, 'move': 12,
    'retirement': 9, 'foreign': 8, 'cell-budget': 9, 'plugin-override': 7, 'plugin-new': 7,
    'plugin-move': 4, 'plugin-delete': 3, 'actors': 9, 'concurrency': 8, 'unicode': 11, 'quarantine': 10, 'fog': 13}
NEGATIVE = {'missing-base': 'G6 missing base', 'deleted-base': 'G6 missing base',
    'reference-budget': 'G6 reference budget exceeded', 'total-budget': 'G6 reference budget exceeded',
    'zero-budget': 'G6 zero live-world budget', 'duplicate-id': 'G6 duplicate live content reference identity',
    'runtime-delete': 'G6 runtime deletion requires genuine MWWorld::World script lifecycle'}


@contextmanager
def child_fault_capture():
    # Local regression subprocesses must report faults to the retained evidence,
    # rather than waiting on an interactive application-error dialog. This is
    # process-local and restored afterwards, not a system security setting.
    if os.name != 'nt':
        yield; return
    import ctypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetErrorMode.restype = ctypes.c_uint32
    kernel.SetErrorMode.argtypes = [ctypes.c_uint32]
    kernel.SetErrorMode.restype = ctypes.c_uint32
    previous = kernel.GetErrorMode()
    kernel.SetErrorMode(previous | 0x0001 | 0x0002 | 0x8000)
    try:
        yield
    finally:
        kernel.SetErrorMode(previous)


def inputs(mode):
    fixture = mode if mode.startswith('plugin-') or mode in ('missing-base', 'deleted-base') else 'good'
    if mode == 'quarantine':
        fixture = 'stream-rollback'
    source = fixtures.inputs(fixture)
    if mode == 'actors':
        npc = fixtures.sub(b'NAME', b'g6_actor\0') + fixtures.sub(b'FNAM', b'Authored NPC\0')
        npc += fixtures.sub(b'NPDT', fixtures.le('hBBB3xi', 1, 50, 0, 0, 0))
        npc += fixtures.sub(b'FLAG', fixtures.le('I', 16))
        source['Morrowind.esm'] += fixtures.record(b'NPC_', npc)
    if mode in ('actors', 'duplicate-id'):
        rebuilt = []
        for kind, payload in fixtures.records(source['Morrowind.esm']):
            if kind == b'CELL':
                values = list(fixtures.subs(payload))
                cell = next(raw for tag, raw in values if tag == b'DATA')
                flags, x, y = struct.unpack('<Iii', cell)
                if not flags and (x, y) == (-2, -9) and mode == 'actors':
                    payload += fixtures.reference(700, b'g6_actor')
                if not flags and (x, y) == (-1, -9) and mode == 'duplicate-id':
                    parts = []
                    replaced = False
                    for tag, raw in values:
                        if tag == b'FRMR' and not replaced:
                            raw = fixtures.le('I', 5); replaced = True
                        parts.append(fixtures.sub(tag, raw))
                    if not replaced:
                        raise ValueError('Authored neighbor reference missing')
                    payload = b''.join(parts)
            rebuilt.append(fixtures.record(kind, payload))
        source['Morrowind.esm'] = b''.join(rebuilt)
    return source


def validate_result(case, row):
    retained.process_ok(row)
    if case in POSITIVE:
        if row['exit'] != 0:
            raise ValueError('Native positive case terminated with ' + str(row['exit_hex']))
        report = json.loads(row['stdout'])
        if not isinstance(report, dict) or report.get('status') != 'PASS' or type(report.get('checks')) is not int or report['checks'] != POSITIVE[case]:
            raise ValueError('Native status/assertion inventory mismatch')
    elif case not in NEGATIVE or row['exit'] != 1 or not NEGATIVE[case] or NEGATIVE[case] not in row['stderr']:
        raise ValueError('Wrong native rejection: ' + NEGATIVE.get(case, 'unknown case'))


def run(binary, output):
    results = []; retained.save(output, results)
    for case in (*POSITIVE, *NEGATIVE):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for name, raw in inputs(case).items():
                target = directory / name; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(raw)
            before = retained.snapshot(directory)
            row = {'case': case, 'status': 'RUNNING', 'inputs_before_sha256': before,
                'expected_exit': 0 if case in POSITIVE else 1,
                'expected_checks': POSITIVE.get(case), 'expected_diagnostic': NEGATIVE.get(case)}
            results.append(row); retained.save(output, results)
            with child_fault_capture():
                row.update(retained.capture([binary, directory, REPO / 'files/settings-default.cfg', case], 120))
            retained.save(output, results)
            try:
                validate_result(case, row)
                if before != retained.snapshot(directory):
                    raise ValueError('Authored input changed during genuine engine execution')
            except Exception as error:
                failure = retained.failure(row, output, str(error)); retained.save(output, results)
                raise failure from error
            row['status'] = 'PASS'; retained.save(output, results)
    return results


def world(binary, shaders, output):
    # The original 42 cases remain mandatory. Only two expected diagnostics
    # become the new fail-closed CellStore errors, before the old bridge runs.
    before = fixtures.NEGATIVE
    fixtures.NEGATIVE = dict(before, **{'missing-base': 'G6 missing base', 'deleted-base': 'G6 missing base'})
    try:
        return retained.run(binary, shaders, output)
    finally:
        fixtures.NEGATIVE = before


def render(binary, shaders, output):
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary); fixtures.write(directory, 'good')
        before = retained.snapshot(directory)
        row = {'case': 'render-lifecycle', 'status': 'RUNNING', 'expected_exit': 0,
            'expected_checks': 10, 'inputs_before_sha256': before}
        retained.save(output, [row])
        with child_fault_capture():
            row.update(retained.capture([binary, directory, shaders, REPO / 'files/settings-default.cfg'], 120))
        try:
            retained.process_ok(row)
            if row['exit'] != 0:
                raise ValueError('Native render lifecycle terminated with ' + str(row['exit_hex']))
            report = json.loads(row['stdout'])
            if report.get('status') != 'PASS' or report.get('checks') != 10:
                raise ValueError('Render lifecycle assertion inventory mismatch')
            if retained.snapshot(directory) != before:
                raise ValueError('Authored renderer inputs changed')
        except Exception as error:
            failure = retained.failure(row, output, str(error)); retained.save(output, [row]); raise failure from error
        row['status'] = 'PASS'; retained.save(output, [row]); return [row]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--binary', type=Path)
    group.add_argument('--world-binary', type=Path)
    group.add_argument('--render-binary', type=Path)
    parser.add_argument('--shaders', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.world_binary:
        result = world(args.world_binary.resolve(), args.shaders.resolve(), args.output)
    elif args.render_binary:
        result = render(args.render_binary.resolve(), args.shaders.resolve(), args.output)
    else:
        result = run(args.binary.resolve(), args.output)
    print(json.dumps({'status': 'PASS', 'cases': len(result), 'evidence': str(args.output)}, indent=2))
