"""Admin entry point. The admin page opens only at ?admin=<ADMIN_ROUTE_KEY>.
The key hides the link. It is not authentication: the admin login still needs the password and lockout."""
import hmac

import streamlit as st

SECRET_NAME = "ADMIN_ROUTE_KEY"


def admin_secret():
    try:
        value = st.secrets.get(SECRET_NAME)
    except Exception:
        return None
    value = str(value).strip() if value else ""
    return value or None


def admin_route_allowed(query_params, secret):
    if not secret:
        return False
    supplied = query_params.get("admin")
    if not supplied:
        return False
    return hmac.compare_digest(str(supplied).encode("utf-8"), str(secret).encode("utf-8"))
