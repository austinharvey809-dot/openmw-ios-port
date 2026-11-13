"""Check embedded Bash and Python syntax without installing a YAML/tool dependency.

This checks the workflow's literal run blocks, not the GitHub Actions YAML schema.
"""
import argparse
import ast
from pathlib import Path
import re
import subprocess


def blocks(path):
    lines = path.read_text().splitlines()
    result, index = [], 0
    while index < len(lines):
        line = lines[index]
        if re.match(r'^\s+run: \|$', line):
            indent = len(line) - len(line.lstrip())
            code = []
            index += 1
            while index < len(lines) and (not lines[index].strip() or
                    len(lines[index]) - len(lines[index].lstrip()) > indent):
                code.append(lines[index][indent + 2:])
                index += 1
            result.append('\n'.join(code) + '\n')
        else:
            index += 1
    if not result:
        raise ValueError('No workflow run blocks')
    return result


def check(path, bash):
    values = blocks(path)
    python_blocks = 0
    for index, code in enumerate(values):
        subprocess.run([str(bash), '-n'], input=code, text=True, check=True, capture_output=True)
        for body in re.findall(r"python3 - <<'PY'\n(.*?)\nPY", code, re.S):
            ast.parse(body, filename=str(path) + ':run-' + str(index))
            python_blocks += 1
    return {'bash_run_blocks': len(values), 'embedded_python_blocks': python_blocks,
            'scope': 'Syntax only; GitHub YAML schema and Apple execution separate'}


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--workflow', type=Path, required=True)
    cli.add_argument('--bash', type=Path, default=Path('bash'))
    args = cli.parse_args()
    print(check(args.workflow, args.bash))
