"""In-memory stand-in for the supabase-py client (PostgREST semantics incl. 1000-row default cap)."""
import copy, itertools, re, sys, types
 
DEFAULT_CAP = 1000
PK = {'eligibility_settings': ('subject_id',), 'subject_geofence': ('subject_id',),
      'condonation_decisions': ('subject_id', 'student_id')}
UNIQUE = {'alert_log': ('student_id', 'kind', 'channel', 'period_key')}
DEFAULTS = {'leave_requests': {'status': 'pending'}, 'subject_slots': {'grace_minutes': 10}}
# only tables with a real foreign key may be embedded (leave_requests deliberately has none)
REL = {('subject_students', 'students'): 'student_id', ('subject_students', 'subjects'): 'subject_id'}
 
 
class APIError(Exception):
    def __init__(self, message, code=None):
        super().__init__(message); self.message, self.code = message, code
 
 
class Resp:
    def __init__(self, data): self.data = data
 
 
class Q:
    def __init__(self, db, table):
        self.db, self.t = db, table
        self.op, self.payload, self.cols = 'select', None, '*'
        self.f, self.orders, self.lim, self.rng = [], [], None, None
 
    def select(self, cols='*'): self.op, self.cols = 'select', cols; return self
    def insert(self, rows): self.op, self.payload = 'insert', rows; return self
    def update(self, vals): self.op, self.payload = 'update', vals; return self
    def upsert(self, vals): self.op, self.payload = 'upsert', vals; return self
    def delete(self): self.op = 'delete'; return self
    def eq(self, c, v): self.f.append((c, 'eq', v)); return self
    def in_(self, c, v): self.f.append((c, 'in', list(v))); return self
    def lte(self, c, v): self.f.append((c, 'lte', v)); return self
    def gte(self, c, v): self.f.append((c, 'gte', v)); return self
    def order(self, c, desc=False): self.orders.append((c, desc)); return self
    def limit(self, n): self.lim = n; return self
    def range(self, a, b): self.rng = (a, b); return self
 
    def _match(self, row):
        for c, op, v in self.f:
            x = row.get(c)
            if op == 'eq' and not (x == v or (x is not None and v is not None and str(x) == str(v) and isinstance(v, str))): return False
            if op == 'in' and str(x) not in [str(i) for i in v]: return False
            if op == 'lte' and not (x is not None and str(x) <= str(v)): return False
            if op == 'gte' and not (x is not None and str(x) >= str(v)): return False
        return True
 
    def _rows(self):
        if self.t == 'student_subject_attendance':   # the SQL view
            agg = {}
            for l in self.db.tables.get('attendance_logs', []):
                k = (l['student_id'], l['subject_id'])
                a = agg.setdefault(k, {'pair_key': f"{k[0]}:{k[1]}", 'student_id': k[0], 'subject_id': k[1],
                                       'total_classes': 0, 'present_classes': 0})
                if l.get('is_present') or not l.get('is_excused'): a['total_classes'] += 1
                if l.get('is_present'): a['present_classes'] += 1
            return list(agg.values())
        return self.db.tables.setdefault(self.t, [])
 
    def execute(self):
        rows = self._rows()
        if self.op == 'select':
            out = [copy.deepcopy(r) for r in rows if self._match(r)]
            for c, desc in reversed(self.orders):
                out.sort(key=lambda r: (r.get(c) is None, r.get(c)), reverse=desc)
            if self.rng: out = out[self.rng[0]:self.rng[1] + 1]
            elif self.lim is not None: out = out[:self.lim]
            else: out = out[:DEFAULT_CAP]
            for rel in re.findall(r'(\w+)\(', self.cols):
                key = REL.get((self.t, rel))
                if not key:
                    raise APIError(f"Could not find a relationship between '{self.t}' and '{rel}'", 'PGRST200')
                if key:
                    for r in out:
                        tgt = [x for x in self.db.tables.get(rel, []) if str(x.get(key)) == str(r.get(key))]
                        r[rel] = copy.deepcopy(tgt[0]) if tgt else None
            return Resp(out)
        if self.op == 'insert':
            new = []
            for item in (self.payload if isinstance(self.payload, list) else [self.payload]):
                item = {**DEFAULTS.get(self.t, {}), **item}
                u = UNIQUE.get(self.t)
                if u and any(all(x.get(k) == item.get(k) for k in u) for x in rows):
                    raise APIError('duplicate key value violates unique constraint', '23505')
                if 'id' not in item and self.t not in ('students', 'subjects'):
                    item['id'] = self.db.next_id()
                rows.append(item); new.append(copy.deepcopy(item))
            return Resp(new)
        if self.op == 'upsert':
            item, pk = dict(self.payload), PK[self.t]
            for x in rows:
                if all(str(x.get(k)) == str(item.get(k)) for k in pk):
                    x.update(item); return Resp([copy.deepcopy(x)])
            rows.append(item); return Resp([copy.deepcopy(item)])
        if self.op == 'update':
            hit = [r for r in rows if self._match(r)]
            for r in hit: r.update(self.payload)
            return Resp([copy.deepcopy(r) for r in hit])
        if self.op == 'delete':
            hit = [r for r in rows if self._match(r)]
            for r in hit: rows.remove(r)
            return Resp(hit)
 
 
class Storage:
    def __init__(self): self.files = {}
    def from_(self, bucket): return Bucket(self, bucket)
 
class Bucket:
    def __init__(self, s, b): self.s, self.b = s, b
    def upload(self, path, data, opts=None): self.s.files[(self.b, path)] = (data, opts)
    def create_signed_url(self, path, secs): return {'signedURL': f'https://signed/{self.b}/{path}?t={secs}'}
 
 
class FakeSupabase:
    def __init__(self):
        self.tables, self.storage, self._ids = {}, Storage(), itertools.count(1)
        self.rpc_calls = []
    def next_id(self): return next(self._ids)
    def table(self, name): return Q(self, name)
    def rpc(self, name, params):
        db = self
        class R:
            def execute(_):
                db.rpc_calls.append((name, params))
                # Python mirror of the SQL function's rules (the SQL itself is NOT executed here)
                if len(params['p_reason'].strip()) < 5: raise APIError('Reason must be at least 5 characters')
                log = next((l for l in db.tables['attendance_logs'] if str(l['id']) == params['p_log_id']), None)
                sub = next((s for s in db.tables['subjects'] if log and s['subject_id'] == log['subject_id']), None)
                if not log or not sub or str(sub['teacher_id']) != params['p_teacher_id']:
                    raise APIError('Record not found or not your subject')
                if bool(log['is_present']) == params['p_new_present']: raise APIError('No change: status already set')
                old = bool(log['is_present']); log['is_present'] = params['p_new_present']
                if params['p_new_present']: log['is_excused'] = False
                db.tables.setdefault('attendance_audit_log', []).append({
                    'id': db.next_id(), 'log_id': params['p_log_id'], 'student_id': str(log['student_id']),
                    'subject_id': str(log['subject_id']), 'changed_by': params['p_teacher_id'],
                    'old_value': old, 'new_value': params['p_new_present'], 'reason': params['p_reason'].strip(),
                    'changed_at': '2026-11-02T10:00:00Z'})
                return Resp({'ok': True})
        return R()
 
 
def install(fake):
    """Register stubs so `from src.database.config import supabase` etc. resolve to the fake."""
    from tests import ui_stub
    st = ui_stub.STUB
    sys.modules['streamlit'] = st
    cfg = types.ModuleType('src.database.config'); cfg.supabase = fake
    sys.modules['src.database.config'] = cfg
    sent = []
    em = types.ModuleType('src.services.email_service')
    em._send = lambda to, subject, html, plain: sent.append((to, subject, html, plain))
    sys.modules['src.services.email_service'] = em
    return st, sent, em
