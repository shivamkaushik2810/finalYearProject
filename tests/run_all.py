import importlib, sys, traceback
sys.path.insert(0, '.')
fails = n = 0
for modname in ('tests.test_batch2', 'tests.test_services', 'tests.test_ui'):
    m = importlib.import_module(modname)
    for name in sorted(dir(m)):
        if name.startswith('test_'):
            n += 1
            try:
                getattr(m, name)(); print('PASS', modname.split('.')[-1], name)
            except Exception:
                fails += 1; print('FAIL', modname.split('.')[-1], name); traceback.print_exc()
print(f'\n{n} tests, {fails} failed')
sys.exit(1 if fails else 0)
