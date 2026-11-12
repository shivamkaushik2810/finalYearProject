import streamlit as st


def get_client_ip():
    try:
        xff = st.context.headers.get("X-Forwarded-For")
        if xff:
            return xff.split(",")[0].strip()
        return st.context.ip_address
    except Exception:
        return None


def get_client_location():
    """(lat, lon, accuracy_m) or None. Needs `streamlit-js-eval`; first call may return None until
    the browser answers, so callers should treat None as 'not yet available'."""
    try:
        from streamlit_js_eval import get_geolocation
    except ImportError:
        return None
    loc = get_geolocation()
    if loc and isinstance(loc, dict) and loc.get('coords'):
        c = loc['coords']
        return c.get('latitude'), c.get('longitude'), c.get('accuracy')
    return None
