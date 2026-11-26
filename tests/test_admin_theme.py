from src.ui import admin_theme as t


def test_twelve_unique_pages_matching_the_menu():
    keys = [p[0] for p in t.ADMIN_PAGES]
    assert len(keys) == len(set(keys)) == 15  # timetable removed; editor, absences, substitutions kept


def test_theme_uses_admin_tokens_and_no_display_font():
    assert "--ad-brand" in t.ADMIN_CSS
    assert "Climate Crisis" not in t.ADMIN_CSS


def test_header_escapes_user_text():
    out = t.header_html("<script>x</script>", "sub", "<img src=x>")
    assert "<script>" not in out and "<img" not in out
    assert "Administration" in out


def test_brand_escapes_caption():
    assert "<b>" not in t.brand_html("<b>bad</b>")
