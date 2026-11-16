"""Debug only a newly created child; retain Windows faults without a dialog.

Uses Windows Debug/DbgHelp APIs, local symbols and x64 unwind metadata. No
installation, privilege escalation, global error-mode changes or symbol server.
"""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


class ExceptionRecord(C.Structure):
    _fields_ = [('code', W.DWORD), ('flags', W.DWORD), ('record', C.c_void_p),
        ('address', C.c_void_p), ('count', W.DWORD), ('information', C.c_uint64 * 15)]


class ExceptionInfo(C.Structure):
    _fields_ = [('record', ExceptionRecord), ('firstChance', W.DWORD)]


class ProcessDebugInfo(C.Structure):
    _fields_ = [('file', W.HANDLE), ('process', W.HANDLE), ('thread', W.HANDLE),
        ('base', C.c_void_p), ('debugOffset', W.DWORD), ('debugSize', W.DWORD),
        ('tls', C.c_void_p), ('start', C.c_void_p), ('imageName', C.c_void_p), ('unicode', W.WORD)]


class DllInfo(C.Structure):
    _fields_ = [('file', W.HANDLE), ('base', C.c_void_p), ('debugOffset', W.DWORD),
        ('debugSize', W.DWORD), ('imageName', C.c_void_p), ('unicode', W.WORD)]


class EventData(C.Union):
    _fields_ = [('exception', ExceptionInfo), ('process', ProcessDebugInfo),
        ('dll', DllInfo), ('raw', C.c_byte * 160)]


class Event(C.Structure):
    _fields_ = [('code', W.DWORD), ('pid', W.DWORD), ('tid', W.DWORD), ('data', EventData)]


class StartupInfo(C.Structure):
    _fields_ = [('cb', W.DWORD), ('reserved', W.LPWSTR), ('desktop', W.LPWSTR), ('title', W.LPWSTR),
        ('x', W.DWORD), ('y', W.DWORD), ('width', W.DWORD), ('height', W.DWORD),
        ('charsX', W.DWORD), ('charsY', W.DWORD), ('fill', W.DWORD), ('flags', W.DWORD),
        ('show', W.WORD), ('reservedSize', W.WORD), ('reservedBytes', C.c_void_p),
        ('stdin', W.HANDLE), ('stdout', W.HANDLE), ('stderr', W.HANDLE)]


class ProcessInfo(C.Structure):
    _fields_ = [('process', W.HANDLE), ('thread', W.HANDLE), ('pid', W.DWORD), ('tid', W.DWORD)]


class Address(C.Structure):
    _fields_ = [('offset', C.c_uint64), ('segment', W.WORD), ('mode', W.DWORD)]


class StackFrame(C.Structure):
    _fields_ = [('pc', Address), ('returnAddress', Address), ('frame', Address),
        ('stack', Address), ('backing', Address), ('function', C.c_void_p),
        ('parameters', C.c_uint64 * 4), ('far', W.BOOL), ('virtual', W.BOOL),
        ('reserved', C.c_uint64 * 3), ('kdHelpStorage', C.c_byte * 512)]


class Symbol(C.Structure):
    _fields_ = [('sizeOfStruct', W.ULONG), ('typeIndex', W.ULONG), ('reserved', C.c_uint64 * 2),
        ('index', W.ULONG), ('size', W.ULONG), ('modBase', C.c_uint64), ('flags', W.ULONG),
        ('value', C.c_uint64), ('address', C.c_uint64), ('register', W.ULONG),
        ('scope', W.ULONG), ('tag', W.ULONG), ('nameLength', W.ULONG),
        ('maxNameLength', W.ULONG), ('name', C.c_char * 1)]


def debug(command, output, timeout=40):
    if os.name != 'nt' or C.sizeof(C.c_void_p) != 8:
        raise RuntimeError('Windows x64 debugger required')
    kernel = C.WinDLL('kernel32', use_last_error=True)
    help = C.WinDLL('dbghelp', use_last_error=True)
    def bind(lib, name, result, *arguments):
        function = getattr(lib, name); function.restype = result; function.argtypes = list(arguments)
        return function
    create = bind(kernel, 'CreateProcessW', W.BOOL, W.LPCWSTR, W.LPWSTR, C.c_void_p, C.c_void_p,
        W.BOOL, W.DWORD, C.c_void_p, W.LPCWSTR, C.POINTER(StartupInfo), C.POINTER(ProcessInfo))
    wait = bind(kernel, 'WaitForDebugEvent', W.BOOL, C.POINTER(Event), W.DWORD)
    resume = bind(kernel, 'ContinueDebugEvent', W.BOOL, W.DWORD, W.DWORD, W.DWORD)
    close = bind(kernel, 'CloseHandle', W.BOOL, W.HANDLE)
    terminate = bind(kernel, 'TerminateProcess', W.BOOL, W.HANDLE, W.UINT)
    openThread = bind(kernel, 'OpenThread', W.HANDLE, W.DWORD, W.BOOL, W.DWORD)
    context = bind(kernel, 'GetThreadContext', W.BOOL, W.HANDLE, C.c_void_p)
    fileName = bind(kernel, 'GetFinalPathNameByHandleW', W.DWORD, W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD)
    initialize = bind(help, 'SymInitializeW', W.BOOL, W.HANDLE, W.LPCWSTR, W.BOOL)
    cleanup = bind(help, 'SymCleanup', W.BOOL, W.HANDLE)
    options = bind(help, 'SymSetOptions', W.DWORD, W.DWORD)
    lookup = bind(help, 'SymFromAddr', W.BOOL, W.HANDLE, C.c_uint64, C.POINTER(C.c_uint64), C.c_void_p)
    walk = bind(help, 'StackWalk64', W.BOOL, W.DWORD, W.HANDLE, W.HANDLE,
        C.POINTER(StackFrame), C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p)
    help.SymFunctionTableAccess64.restype = C.c_void_p
    help.SymGetModuleBase64.restype = C.c_uint64
    assert C.sizeof(ExceptionRecord) == 152 and C.sizeof(Event) == 176 and C.sizeof(Address) == 16
    binary = Path(command[0]).resolve()
    report = {'schema': 1, 'binary': str(binary), 'binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
        'command': [str(x) for x in command], 'modules': [], 'exceptions': [], 'stack': [],
        'symbol_policy': 'Local PE/PDB symbols only; no symbol server', 'status': 'RUNNING'}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    save()
    startup = StartupInfo(); startup.cb = C.sizeof(startup); process = ProcessInfo()
    arguments = C.create_unicode_buffer(subprocess.list2cmdline([str(x) for x in command]))
    # DEBUG_ONLY_THIS_PROCESS | CREATE_NO_WINDOW. No existing process is attached.
    if not create(str(binary), arguments, None, None, False, 0x08000002, None, str(Path.cwd()),
            C.byref(startup), C.byref(process)):
        raise C.WinError(C.get_last_error())
    handles = {process.process, process.thread}; symbols = False; done = False
    deadline = time.monotonic() + timeout
    try:
        while time.monotonic() < deadline and not done:
            event = Event()
            if not wait(C.byref(event), 500):
                if C.get_last_error() == 121: continue
                raise C.WinError(C.get_last_error())
            action = 0x00010002  # DBG_CONTINUE for non-exception events.
            if event.code in (3, 6):
                info = event.data.process if event.code == 3 else event.data.dll
                name = C.create_unicode_buffer(32768)
                path = name.value if not info.file else ''
                if info.file:
                    if fileName(info.file, name, len(name), 0): path = name.value
                    close(info.file)
                report['modules'].append({'base': hex(info.base or 0), 'path': path or str(binary) if event.code == 3 else path})
                if event.code == 3: handles.update((info.process, info.thread))
            elif event.code == 1:
                fault = event.data.exception.record
                report['exceptions'].append({'code': hex(fault.code), 'address': hex(fault.address or 0),
                    'first_chance': bool(event.data.exception.firstChance),
                    'information': [hex(x) for x in fault.information[:fault.count]]})
                action = 0x00010002 if fault.code == 0x80000003 else 0x80010001
                if fault.code in (0xc0000005, 0xc000001d, 0xc00000fd):
                    thread = openThread(0x0048, False, event.tid)
                    if not thread: raise C.WinError(C.get_last_error())
                    handles.add(thread)
                    storage = C.create_string_buffer(1248)
                    aligned = (C.addressof(storage) + 15) & ~15
                    C.c_uint32.from_address(aligned + 48).value = 0x10001f
                    if not context(thread, aligned): raise C.WinError(C.get_last_error())
                    registers = {name: C.c_uint64.from_address(aligned + offset).value
                        for name, offset in [('rip', 248), ('rsp', 152), ('rbp', 160), ('rcx', 128), ('rdx', 136)]}
                    report['registers'] = {name: hex(value) for name, value in registers.items()}
                    options(0x00000216)
                    symbols = bool(initialize(process.process, str(binary.parent), True))
                    report['symbols_initialized'] = symbols
                    frame = StackFrame()
                    frame.pc.offset = registers['rip']; frame.pc.mode = 3
                    frame.stack.offset = registers['rsp']; frame.stack.mode = 3
                    frame.frame.offset = registers['rbp']; frame.frame.mode = 3
                    for _ in range(64):
                        address = frame.pc.offset
                        if not address: break
                        row = {'address': hex(address)}
                        module = max((m for m in report['modules'] if int(m['base'], 16) <= address),
                            key=lambda m: int(m['base'], 16), default=None)
                        if module: row.update(module=module['path'], rva=hex(address - int(module['base'], 16)))
                        buffer = C.create_string_buffer(C.sizeof(Symbol) + 4096)
                        symbol = Symbol.from_buffer(buffer); symbol.sizeOfStruct = C.sizeof(Symbol); symbol.maxNameLength = 4096
                        displacement = C.c_uint64()
                        if symbols and lookup(process.process, address, C.byref(displacement), buffer):
                            row['symbol'] = C.string_at(C.addressof(buffer) + Symbol.name.offset, symbol.nameLength).decode(errors='replace')
                            row['symbol_displacement'] = hex(displacement.value)
                        if not report['stack'] or report['stack'][-1]['address'] != row['address']:
                            report['stack'].append(row)
                        if not walk(0x8664, process.process, thread, C.byref(frame), aligned, None,
                                C.cast(help.SymFunctionTableAccess64, C.c_void_p),
                                C.cast(help.SymGetModuleBase64, C.c_void_p), None): break
                    report['status'] = 'NATIVE_FAULT'; save()
                    terminate(process.process, fault.code); done = True
            elif event.code == 5:
                report['status'] = 'EXITED'; report['exit'] = C.c_uint32.from_buffer(event.data.raw).value; done = True
            if not resume(event.pid, event.tid, action) and not done:
                raise C.WinError(C.get_last_error())
        if not done:
            report['status'] = 'TIMEOUT'; terminate(process.process, 124)
        save()
    finally:
        if symbols: cleanup(process.process)
        if not done: terminate(process.process, 125)
        for handle in handles:
            if handle: close(handle)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    result = debug(args.command, args.output)
    print(json.dumps({'status': result['status'], 'stack': result['stack'], 'evidence': str(args.output)}, indent=2))
