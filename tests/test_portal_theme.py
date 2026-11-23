from pathlib import Path

from src.ui import portal_theme


def test_theme_is_the_shared_professional_palette():
    from src.ui.teacher_theme import TEACHER_CSS
    assert "--sc-primary:#4F46E5" in TEACHER_CSS
    assert "Climate Crisis" not in TEACHER_CSS
    assert callable(portal_theme.inject_portal_theme)


def test_student_screen_applies_theme_after_base_layout():
    src = Path("src/screens/student_screen.py").read_text(encoding="utf-8")
    assert "inject_portal_theme()" in src
    assert src.index("style_base_layout()") < src.index("inject_portal_theme()")


def test_parent_screen_applies_theme_after_base_layout():
    src = Path("src/screens/parent_screen.py").read_text(encoding="utf-8")
    assert "inject_portal_theme()" in src
    assert src.index("style_base_layout()") < src.index("inject_portal_theme()")
