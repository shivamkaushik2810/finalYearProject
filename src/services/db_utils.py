def fetch_all(build, page_size=1000, max_rows=500000):
    """Page through a PostgREST query (default cap is 1000 rows).
    `build` must return a NEW query each call and include a unique .order()."""
    rows, start = [], 0
    while True:
        batch = build().range(start, start + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size or len(rows) >= max_rows:
            break
        start += page_size
    return rows
