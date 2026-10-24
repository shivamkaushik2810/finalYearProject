import re

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
_GMAIL_DOMAINS = {"gmail.com", "googlemail.com"}


def is_valid_email(email):
    return bool(email) and bool(_EMAIL_RE.match(email.strip()))


def canonical_email(email):
    """Normalise so trivial variants of one mailbox compare equal.
    Gmail ignores dots and +tags: a.b+x@gmail.com == ab@gmail.com."""
    if not email:
        return ""
    e = email.strip().lower()
    if "@" not in e:
        return e
    local, domain = e.rsplit("@", 1)
    local = local.split("+", 1)[0]
    if domain in _GMAIL_DOMAINS:
        local = local.replace(".", "")
        domain = "gmail.com"
    return f"{local}@{domain}"


def emails_conflict(student_email, parent_email):
    """True when both are filled and point at the same mailbox."""
    a = canonical_email(student_email)
    b = canonical_email(parent_email)
    return bool(a) and bool(b) and a == b
