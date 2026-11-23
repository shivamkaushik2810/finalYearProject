from pathlib import Path

from src.ui import teacher_theme as t


def test_brand_escapes_and_names_portal():
    out = t.teacher_brand_html()
    assert "Teacher portal" in out and "SnapClass" in out


def test_css_has_teacher_tokens_and_no_display_font():
    assert "--sc-primary:#4F46E5" in t.TEACHER_CSS
    assert "Climate Crisis" not in t.TEACHER_CSS


def test_screen_uses_sidebar_and_keeps_state_key():
    src = Path("src/screens/teacher_screen.py").read_text(encoding="utf-8")
    assert "with st.sidebar:" in src
    assert 'key="current_teacher_tab"' in src
    assert "inject_teacher_theme()" in src
