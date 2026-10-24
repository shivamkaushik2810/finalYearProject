from src.services.email_rules import emails_conflict, canonical_email, is_valid_email


def test_identical_emails_conflict():
    assert emails_conflict("a@x.com", "a@x.com")


def test_case_and_spaces_ignored():
    assert emails_conflict(" A@X.com ", "a@x.com")


def test_gmail_dot_and_plus_tricks_conflict():
    assert emails_conflict("shivam.k@gmail.com", "shivamk+parent@gmail.com")
    assert emails_conflict("a.b@gmail.com", "ab@googlemail.com")


def test_different_emails_ok():
    assert not emails_conflict("student@gmail.com", "parent@gmail.com")


def test_empty_values_never_conflict():
    assert not emails_conflict("", "")
    assert not emails_conflict(None, "a@x.com")
    assert not emails_conflict("a@x.com", None)


def test_non_gmail_dots_are_significant():
    assert not emails_conflict("a.b@college.edu", "ab@college.edu")


def test_canonical_handles_garbage():
    assert canonical_email("not-an-email") == "not-an-email"


def test_is_valid_email():
    assert is_valid_email("a@b.co")
    assert not is_valid_email("a@b")
    assert not is_valid_email("")
    assert not is_valid_email(None)
