"""Minimal recording stand-in for Streamlit so UI functions can run headless."""
import datetime as dt
import types
 
 
class Rerun(Exception):
    pass
 
 
class DotDict(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)
    def __setattr__(self, k, v): self[k] = v
    def __delattr__(self, k): del self[k]
 
 
LOG, CLICKS, VALUES = [], set(), {}
 
 
class Ctx:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name): return getattr(STUB, name)   # c1.button(...), tab.metric(...)
 
 
def _rec(name):
    def f(*a, **k):
        LOG.append((name, a, k)); return None
    return f
 
 
def _val(k, default): return VALUES.get(k.get('key'), default)
 
 
def make():
    m = types.ModuleType('streamlit')
    m.session_state, m.secrets = DotDict(), {}
    m.context = types.SimpleNamespace(headers={}, ip_address=None)
    for n in ('write', 'markdown', 'caption', 'header', 'subheader', 'success', 'error', 'info',
              'warning', 'dataframe', 'metric', 'divider', 'toast', 'space', 'download_button'):
        setattr(m, n, _rec(n))
    m.container = m.expander = m.form = lambda *a, **k: Ctx()
    m.spinner = lambda *a, **k: Ctx()
    m.columns = lambda spec, **k: [Ctx() for _ in range(spec if isinstance(spec, int) else len(spec))]
    m.tabs = lambda labels: [Ctx() for _ in labels]
    m.dialog = lambda *a, **k: (lambda fn: fn)
    def rerun(): raise Rerun()
    m.rerun = rerun
    def button(label, *a, **k):
        LOG.append(('button', (label,), k))
        return k.get('key') in CLICKS or label in CLICKS
    m.button = button
    m.text_input = lambda label, value='', **k: _val(k, value)
    m.text_area = lambda label, value='', **k: _val(k, value)
    m.checkbox = lambda label, value=False, **k: _val(k, value)
    m.radio = lambda label, options, index=0, **k: _val(k, list(options)[index])
    def selectbox(label, options, index=0, **k):
        opts = list(options)
        return _val(k, opts[index] if opts else None)
    m.selectbox = selectbox
    m.number_input = lambda label, min_value=None, max_value=None, value=None, step=None, **k: _val(k, value)
    m.date_input = lambda label, value=None, **k: _val(k, value)
    m.time_input = lambda label, value=None, **k: _val(k, value or dt.time(9, 0))
    m.file_uploader = lambda label, **k: VALUES.get(k.get('key'))
    m.camera_input = lambda label, **k: VALUES.get(k.get('key'))
    return m
 
 
STUB = make()
 
 
def reset():
    LOG.clear(); CLICKS.clear(); VALUES.clear(); STUB.session_state.clear(); STUB.secrets.clear()
 
 
def texts(*names):
    return [str(a[0]) for n, a, k in LOG if n in names and a]
 
 
def run(fn, *a, **k):
    try:
        fn(*a, **k); return False
    except Rerun:
        return True
