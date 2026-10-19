"""Tiny in-memory stand-in for the Supabase client, so the data layer and UI can be tested without a database."""
import copy


class _Res:
    def __init__(self, data, count=None):
        self.data, self.count = data, count


class _Rpc:
    def __init__(self, db, name, params):
        self.db, self.name, self.params = db, name, params

    def execute(self):
        self.db.rpc_calls.append((self.name, self.params))
        if self.name not in self.db.rpcs:
            raise Exception(f"function {self.name} not found")
        return _Res(self.db.rpcs[self.name](self.params))


class _Query:
    def __init__(self, db, name):
        self.db, self.name = db, name
        self.op, self.payload = "select", None
        self.filters, self.orders = [], []
        self.lo = self.hi = self.lim = None

    def select(self, cols="*", count=None):
        self.op = "select"
        return self

    def insert(self, rows):
        self.op, self.payload = "insert", rows
        return self

    def update(self, values):
        self.op, self.payload = "update", values
        return self

    def delete(self):
        self.op = "delete"
        return self

    def eq(self, k, v):
        self.filters.append(lambda r: r.get(k) == v)
        return self

    def neq(self, k, v):
        self.filters.append(lambda r: r.get(k) != v)
        return self

    def in_(self, k, vals):
        vals = list(vals)
        self.filters.append(lambda r: r.get(k) in vals)
        return self

    def gte(self, k, v):
        self.filters.append(lambda r: r.get(k) is not None and str(r.get(k)) >= str(v))
        return self

    def lt(self, k, v):
        self.filters.append(lambda r: r.get(k) is not None and str(r.get(k)) < str(v))
        return self

    def lte(self, k, v):
        self.filters.append(lambda r: r.get(k) is not None and str(r.get(k)) <= str(v))
        return self

    def ilike(self, k, pattern):
        pat = str(pattern).replace("%", "").lower()
        self.filters.append(lambda r: str(r.get(k) or "").lower() == pat)
        return self

    def order(self, col, desc=False):
        self.orders.append((col, desc))
        return self

    def limit(self, n):
        self.lim = n
        return self

    def range(self, a, b):
        self.lo, self.hi = a, b
        return self

    def execute(self):
        self.db.calls.append((self.name, self.op))
        if self.name in self.db.fail_tables:
            raise RuntimeError(f"simulated failure on {self.name}")
        rows = self.db.tables.setdefault(self.name, [])
        if self.op == "insert":
            new = self.payload if isinstance(self.payload, list) else [self.payload]
            rows.extend(copy.deepcopy(new))
            return _Res(copy.deepcopy(new))
        matched = [r for r in rows if all(f(r) for f in self.filters)]
        if self.op == "update":
            for r in matched:
                r.update(self.payload)
            return _Res(copy.deepcopy(matched))
        if self.op == "delete":
            rows[:] = [r for r in rows if r not in matched]
            return _Res([])
        for col, desc in reversed(self.orders):
            matched.sort(key=lambda r: (r.get(col) is None, str(r.get(col))), reverse=desc)
        if self.lo is not None:
            matched = matched[self.lo:self.hi + 1]
        if self.lim is not None:
            matched = matched[:self.lim]
        return _Res(copy.deepcopy(matched))


class FakeSupabase:
    def __init__(self):
        self.reset()

    def reset(self):
        self.tables, self.rpcs = {}, {}
        self.calls, self.rpc_calls = [], []
        self.fail_tables = set()

    def table(self, name):
        return _Query(self, name)

    def rpc(self, name, params=None):
        return _Rpc(self, name, params or {})
