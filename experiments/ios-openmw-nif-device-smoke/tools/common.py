"""Read-only reuse of reviewed source audits and packaging helpers."""
import hashlib
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
G0B = ROOT.parent / 'ios-openmw-nif-smoke'
OSG_REVISION = '9b384d5439977784e5cd250ff8ff7966928ddd27'
HOST_COMMIT = '64cad82d891438c5d07ed4904321e4d04901aa0b'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    sys.modules[name] = value
    spec.loader.exec_module(value)
    return value


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def tree(root):
    require(root.is_dir() and not root.is_symlink(), 'Missing/linked resource root')
    result = {}
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(), 'Linked resource entry')
        if path.is_file():
            result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result
