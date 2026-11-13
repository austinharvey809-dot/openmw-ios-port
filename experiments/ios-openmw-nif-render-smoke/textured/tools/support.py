"""Load immutable G1B validators privately; extend their inputs without editing them."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[2]
DEVICE = ROOT.parent / 'device'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    sys.modules[name] = result
    spec.loader.exec_module(result)
    return result


base = load('_g1c_g1b_provenance', DEVICE / 'tools/provenance.py')
saved = sys.modules.get('provenance')
try:
    sys.modules['provenance'] = base
    package = load('_g1c_g1b_package', DEVICE / 'tools/package_device.py')
finally:
    if saved is None:
        del sys.modules['provenance']
    else:
        sys.modules['provenance'] = saved
require, sha, host = base.require, base.sha, base.host
