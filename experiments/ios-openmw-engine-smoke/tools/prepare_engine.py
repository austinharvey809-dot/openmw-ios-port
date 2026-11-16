"""Build a checked, ESM3-only component view of the genuine engine store.

No upstream file is edited. Two application-only member definitions are absent
from the component, rather than replaced by implementations with weaker behavior.
Calling either excluded API therefore fails at link time.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]


def function_span(text, signature):
    start = text.index(signature)
    if text.count(signature) != 1:
        raise ValueError('Ambiguous upstream signature: ' + signature)
    # These pinned functions contain no braces in string literals or comments.
    begin = text.index('{', start)
    depth = 1
    end = begin + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return start, end


def prepare(output):
    lock = json.loads((ROOT / 'engine-lock.json').read_text())
    sources = {}
    for name, expected in lock['sources'].items():
        raw = (REPO / name).read_bytes()
        # Git working-tree CRLF is immaterial; the source contract is LF UTF-8.
        raw = raw.replace(b'\r\n', b'\n')
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Engine source provenance mismatch: ' + name)
        sources[name] = raw.decode('utf-8')
    output.mkdir(parents=True, exist_ok=True)
    text = sources['apps/openmw/mwworld/esmstore.cpp']
    omitted = []
    for signature in lock['excluded_definitions']:
        start, end = function_span(text, signature)
        omitted.append({'signature': signature, 'sha256': hashlib.sha256(text[start:end].encode()).hexdigest()})
        text = text[:start] + '// Application-only API intentionally not linked in ESM3 component.\n' + text[end:]
    text = text.replace('#include "esmstore.hpp"', '#include <apps/openmw/mwworld/esmstore.hpp>')
    (output / 'esmstore.cpp').write_bytes(text.encode())
    state = sources['components/lua/luastate.cpp']
    helpers = []
    for signature in ('    sol::table makeReadOnly(', '    std::string toString(',
                      '    std::string Internal::formatCastingError(',
                      '    sol::protected_function_result LuaState::throwIfError('):
        start, end = function_span(state, signature)
        helpers.append(state[start:end])
    # serialization.cpp references this independent helper, not LuaState's
    # script scheduler, sandbox or engine-service owner. Preserve its body.
    helper = '#include <components/lua/luastate.hpp>\nnamespace LuaUtil {\n' + '\n'.join(helpers) + '\n}\n'
    (output / 'readonly.cpp').write_bytes(helper.encode())
    (output / 'engine-projection.json').write_text(json.dumps({
        'schema': 1, 'sources': lock['sources'], 'omitted_definitions': omitted,
        'scope': 'genuine ESM3 store; no ESM4 loading or gameplay spell-list service',
    }, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    prepare(parser.parse_args().output)
