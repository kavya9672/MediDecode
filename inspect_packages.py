import sys, pkgutil
print('sys.path first entries:')
for p in sys.path[:5]:
    print(p)
print('Installed fastapi/starlette modules:')
for m in pkgutil.iter_modules():
    if m.name.startswith('fastapi') or m.name.startswith('starlette'):
        print(m.name, m.module_finder.path)
