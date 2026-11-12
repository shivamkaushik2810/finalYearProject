"""Design tokens for SnapClass. Change a colour or radius here and the whole app follows."""

TOKENS = {
    "primary": "#5865F2",
    "primary-dark": "#3C3489",
    "accent": "#EB459E",
    "bg": "#E0E3FF",
    "surface": "#FFFFFF",
    "text": "#1e293b",
    "muted": "#475569",
    "border": "#cbd5e1",
    "good": "#3B6D11",
    "good-bg": "#EAF3DE",
    "avg": "#854F0B",
    "avg-bg": "#FAEEDA",
    "bad": "#A32D2D",
    "bad-bg": "#FCEBEB",
    "radius": "14px",
    "radius-pill": "999px",
}


def css_variables():
    body = ";".join(f"--sc-{k}:{v}" for k, v in TOKENS.items())
    return ":root{" + body + "}"
