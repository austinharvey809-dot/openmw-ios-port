"""Checked component views. Original engine/dependency files are never edited."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO / 'experiments/ios-openmw-engine-smoke/tools'))
from prepare_engine import function_span


def digest(raw):
    return hashlib.sha256(raw.replace(b'\r\n', b'\n')).hexdigest()


def write_if_changed(path, raw):
    if not path.exists() or path.read_bytes() != raw:
        path.write_bytes(raw)


def replace_once(text, before, after):
    if text.count(before) != 1:
        raise ValueError('Projection anchor mismatch: ' + before)
    return text.replace(before, after)


def includes(text, source):
    def resolve(match):
        target = (REPO / source).parent / match[1]
        name = target.resolve().relative_to(REPO).as_posix()
        if not target.is_file():
            raise ValueError('Missing original include: ' + name)
        return '#include <' + name + '>'
    return re.sub(r'#include "([^"]+)"', resolve, text)


def prepare(output):
    output = output.resolve()
    if output.is_relative_to(REPO) and 'artifacts' not in output.relative_to(REPO).parts:
        raise ValueError('Generated source must be outside repository sources or under artifacts')
    lock = json.loads((ROOT / 'engine-lock.json').read_text())
    original = {}
    for name, expected in lock['sources'].items():
        raw = (REPO / name).read_bytes()
        if digest(raw) != expected:
            raise ValueError('G6 original source mismatch: ' + name)
        original[name] = raw.decode('utf-8-sig').replace('\r\n', '\n')
    output.mkdir(parents=True, exist_ok=True)
    products = {}
    for name, rule in lock['projections'].items():
        text = original[rule['source']]
        mode = rule['mode']
        if mode == 'methods':
            preamble = text[:text.index('namespace ')] if rule.get('original_includes') else rule['includes']
            body = ''
            if rule.get('class_prefix'):
                first, last = rule['class_prefix']
                body += text[text.index(first):text.index(last)]
            for signature in rule['signatures']:
                start, end = function_span(text, signature)
                body += text[start:end] + '\n'
            text = preamble + '\nnamespace ' + rule['namespace'] + ' {\n' + body + '\n}\n'
        elif mode == 'omit':
            for signature in rule['signatures']:
                start, end = function_span(text, signature)
                text = text[:start] + '// Application-frame API intentionally absent from component.\n' + text[end:]
        elif mode == 'strict-cellstore':
            # Preserve genuine decoding and ownership. Raise the exact failures
            # that upstream logs and swallows, so partial cells cannot pass G6.
            for stage in ('listing', 'loading'):
                before = ('Log(Debug::Error) << "An error occurred ' + stage
                    + ' references for cell " << getCell()->getDescription()\n'
                    + '                                  << ": " << e.what();')
                text = replace_once(text, before, before + '\n                throw;')
            for before, after in (
                ('Log(Debug::Error) << "Cell reference " << ref.mRefID << " is not found!";\n            return;',
                 'throw std::runtime_error("G6 missing base: " + ref.mRefID.toDebugString());'),
                ('Log(Debug::Error) << "Error: Ignoring reference " << ref.mRefID << " of unhandled type";\n            return;',
                 'throw std::runtime_error("G6 unhandled live reference type: " + ref.mRefID.toDebugString());'),
                ('Log(Debug::Warning) << "Warning: could not resolve cell reference " << ref.mRefID\n'
                 '                                << " (dropping reference)";',
                 'throw std::runtime_error("G6 unresolved typed base: " + ref.mRefID.toDebugString());')):
                text = replace_once(text, before, after)
        elif mode == 'index':
            text = text.replace('namespace G5', 'namespace G6Store')
            if name.endswith('.hpp'):
                anchor = '    const MWWorld::ESMStore& store() const { return engine; }'
                text = replace_once(text, anchor, anchor
                    + '\nprotected:\n    MWWorld::ESMStore& mutableStore() { return engine; }'
                    + '\n    ESM::ReadersCache& readerCache() { return readers; }\npublic:')
                text = text.replace('    MWWorld::Store<', '    const MWWorld::Store<')
                text = replace_once(text, '    std::vector<ESM::CellRef> references(const ESM::Cell& cell);',
                    '    // G6 renderer references come exclusively from LiveWorld/CellStore.')
        else:
            raise ValueError('Unknown projection mode: ' + mode)
        # Local projected headers must resolve to their companion generated view.
        text = includes(text, rule['source']) if mode != 'index' else text
        write_if_changed(output / name, text.encode('utf-8'))
        products[name] = hashlib.sha256(text.encode()).hexdigest()
    write_if_changed(output / 'projection.json', (json.dumps({
        'schema': 1, 'base': lock['base'], 'originals': lock['sources'],
        'products': products, 'rules': lock['projections'],
    }, indent=2) + '\n').encode('utf-8'))
    return products


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(prepare(parser.parse_args().output), indent=2))
