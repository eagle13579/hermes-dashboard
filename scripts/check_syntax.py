"""Syntax check all Python files in the project."""
import ast, sys, pathlib

fails = []
for p in sorted(pathlib.Path('backend').rglob('*.py')):
    try:
        ast.parse(p.read_text())
        print(f'  OK  {p}')
    except SyntaxError as e:
        print(f'  FAIL {p}: {e}')
        fails.append(str(p))

if fails:
    print(f'\n❌ {len(fails)} file(s) failed syntax check')
    sys.exit(1)
else:
    print(f'\n✅ All Python files pass syntax check')
