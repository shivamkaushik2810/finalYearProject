import time
import httpx
import streamlit as st
from supabase import create_client, Client

_url = st.secrets["SUPABASE_URL"]
# Service-role key (server-side only); falls back to the anon key if not configured
_key = st.secrets.get("SUPABASE_SERVICE_KEY") or st.secrets["SUPABASE_KEY"]

_RETRY_ERRORS = (
    httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError,
    httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.PoolTimeout,
)


class _RetryTransport(httpx.BaseTransport):
    """No idle keep-alive connections (stale ones caused 'Server disconnected');
    read-only requests are retried, writes never are (no duplicate inserts)."""

    def __init__(self):
        self._inner = httpx.HTTPTransport(
            retries=2, http2=False,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=0),
        )

    def handle_request(self, request):
        attempts = 3 if request.method in ("GET", "HEAD", "OPTIONS") else 1
        for i in range(attempts):
            try:
                return self._inner.handle_request(request)
            except _RETRY_ERRORS:
                if i == attempts - 1:
                    raise
                time.sleep(0.4 * (i + 1))

    def close(self):
        self._inner.close()


def _build() -> Client:
    client = create_client(_url, _key)
    try:
        old = client.postgrest.session
        client.postgrest.session = httpx.Client(
            base_url=old.base_url,
            headers=old.headers,
            timeout=httpx.Timeout(20.0, connect=10.0),
            follow_redirects=True,
            transport=_RetryTransport(),
        )
        old.close()
    except Exception as e:
        print(f"[supabase] connection hardening not applied: {str(e)[:120]}")
    return client


supabase: Client = _build()
