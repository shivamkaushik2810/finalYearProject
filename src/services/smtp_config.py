"""Central SMTP settings. Uses SMTP_* secrets when present, else Gmail."""
import smtplib
import ssl
import streamlit as st


def _get(key, default=None):
    try:
        value = st.secrets[key]
    except Exception:
        return default
    value = str(value).strip() if value is not None else ""
    return value or default


def get_smtp_settings():
    host = _get("SMTP_HOST")
    if host:
        cfg = {
            "provider": "relay",
            "host": host,
            "port": int(_get("SMTP_PORT", "587")),
            "user": _get("SMTP_USER"),
            "password": _get("SMTP_PASSWORD"),
            "sender": _get("SMTP_FROM"),
        }
        missing = [k for k in ("user", "password", "sender") if not cfg[k]]
        if missing:
            raise RuntimeError(
                "SMTP_HOST is set but these are missing: "
                + ", ".join("SMTP_" + ("FROM" if m == "sender" else m.upper()) for m in missing))
        return cfg
    return {
        "provider": "gmail",
        "host": "smtp.gmail.com",
        "port": 587,
        "user": _get("EMAIL_ADDRESS"),
        "password": _get("EMAIL_PASSWORD"),
        "sender": _get("EMAIL_ADDRESS"),
    }


def open_smtp():
    """Returns (logged-in server, settings). Caller must quit()."""
    cfg = get_smtp_settings()
    if cfg["port"] == 465:
        server = smtplib.SMTP_SSL(cfg["host"], 465, timeout=30,
                                  context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=30)
        server.ehlo()
        server.starttls(context=ssl.create_default_context())
        server.ehlo()
    server.login(cfg["user"], cfg["password"])
    return server, cfg
