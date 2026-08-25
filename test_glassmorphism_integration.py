"""
Integration test for Glassmorphism theme in DFIR-IRIS.

Verifies that the glassmorphism theme is properly integrated into the project.

Run with: python test_glassmorphism_integration.py
"""

from pathlib import Path


def test_glassmorphism_css_exists():
    """Test that glassmorphism CSS file exists."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    assert css_file.exists(), "Glassmorphism CSS file should exist"
    
    content = css_file.read_text(encoding='utf-8')
    assert len(content) > 1000, "CSS file should have substantial content"
    print(f"✓ Glassmorphism CSS exists ({len(content)} bytes)")


def test_glassmorphism_included_in_layout():
    """Test that glassmorphism theme is included in default layout."""
    layout_file = Path("source/app/templates/layouts/default.html")
    assert layout_file.exists(), "Default layout should exist"
    
    content = layout_file.read_text(encoding='utf-8')
    assert "glassmorphism-theme.css" in content, \
        "Layout should include glassmorphism-theme.css"
    assert "dark-theme.css" in content, \
        "Layout should include dark-theme.css (dependency)"
    print("✓ Glassmorphism theme included in default layout")


def test_glassmorphism_has_required_features():
    """Test that glassmorphism CSS has all required features."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    # Check for glassmorphism core features
    required_features = [
        "backdrop-filter",
        "blur(12px)",
        "rgba(255, 255, 255, 0.08)",
        "linear-gradient",
        "box-shadow",
        "transition",
        "animation",
    ]
    
    for feature in required_features:
        assert feature in content, f"CSS should include {feature}"
    
    print(f"✓ Glassmorphism CSS has all required features ({len(required_features)} checks)")


def test_glassmorphism_has_all_statuses():
    """Test that all status styles are defined."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    statuses = [
        "status-new", "status-open", "status-closed",
        "status-resolved", "status-pending", "status-critical"
    ]
    
    for status in statuses:
        assert status in content, f"CSS should include {status} styles"
    
    print(f"✓ All {len(statuses)} status styles defined")


def test_glassmorphism_has_animations():
    """Test that glassmorphism CSS includes animations."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    animations = [
        "@keyframes glass-bg-move",
        "@keyframes glass-border-glow",
        "@keyframes glass-badge-pulse",
    ]
    
    for animation in animations:
        assert animation in content, f"CSS should include {animation}"
    
    print(f"✓ All {len(animations)} animations defined")


def test_glassmorphism_has_button_styles():
    """Test that button styles are defined."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    button_styles = [
        ".btn-primary",
        ".btn-secondary",
        ".btn-danger",
        "backdrop-filter: blur(8px)",
    ]
    
    for style in button_styles:
        assert style in content, f"CSS should include {style}"
    
    print(f"✓ Button styles defined ({len(button_styles)} checks)")


def test_glassmorphism_has_navigation_styles():
    """Test that navigation styles are defined."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    nav_styles = [
        ".navbar",
        ".sidebar-menu",
        "backdrop-filter: blur(12px)",
    ]
    
    for style in nav_styles:
        assert style in content, f"CSS should include {style}"
    
    print(f"✓ Navigation styles defined ({len(nav_styles)} checks)")


def test_glassmorphism_has_form_styles():
    """Test that form input styles are defined."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    form_styles = [
        ".form-control",
        "input:focus",
        "border-radius: 8px",
    ]
    
    for style in form_styles:
        assert style in content, f"CSS should include {style}"
    
    print(f"✓ Form styles defined ({len(form_styles)} checks)")


def test_glassmorphism_has_severity_styles():
    """Test that severity indicator styles are defined."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    severities = [
        ".severity-low",
        ".severity-medium",
        ".severity-high",
        ".severity-critical",
    ]
    
    for severity in severities:
        assert severity in content, f"CSS should include {severity}"
    
    print(f"✓ All {len(severities)} severity styles defined")


def test_glassmorphism_has_responsive_styles():
    """Test that responsive styles are defined."""
    css_file = Path("source/app/static/assets/css/glassmorphism-theme.css")
    content = css_file.read_text(encoding='utf-8')
    
    assert "@media" in content, "CSS should include media queries"
    assert "(max-width: 768px)" in content, "CSS should include mobile breakpoint"
    
    print("✓ Responsive styles defined")


def test_documentation_exists():
    """Test that theme documentation exists."""
    doc_file = Path("GLASSMORPHISM_THEME.md")
    assert doc_file.exists(), "Theme documentation should exist"
    
    content = doc_file.read_text(encoding='utf-8')
    assert len(content) > 2000, "Documentation should be comprehensive"
    
    required_sections = [
        "## Обзор",
        "## Особенности",
        "## Установка",
        "## Тестирование",
    ]
    
    for section in required_sections:
        assert section in content, f"Documentation should include {section}"
    
    print(f"✓ Documentation exists ({len(content)} bytes)")


def test_demo_html_exists():
    """Test that demo HTML file exists."""
    demo_file = Path("sketches/003-glassmorphism-modern/index.html")
    assert demo_file.exists(), "Demo HTML should exist"
    
    content = demo_file.read_text(encoding='utf-8')
    assert "Glassmorphism" in content, "Demo should mention Glassmorphism"
    
    print(f"✓ Demo HTML exists ({len(content)} bytes)")


if __name__ == "__main__":
    print("Running Glassmorphism Theme Integration Tests\n")
    print("=" * 60)
    
    tests = [
        test_glassmorphism_css_exists,
        test_glassmorphism_included_in_layout,
        test_glassmorphism_has_required_features,
        test_glassmorphism_has_all_statuses,
        test_glassmorphism_has_animations,
        test_glassmorphism_has_button_styles,
        test_glassmorphism_has_navigation_styles,
        test_glassmorphism_has_form_styles,
        test_glassmorphism_has_severity_styles,
        test_glassmorphism_has_responsive_styles,
        test_documentation_exists,
        test_demo_html_exists,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: Unexpected error: {e}")
            failed += 1
    
    print("=" * 60)
    print(f"\nResults: {passed} passed, {failed} failed")
    
    if failed > 0:
        exit(1)
    else:
        print("\n🎉 All integration tests passed!")
        print("\nGlassmorphism theme is successfully integrated!")
        print("To use: Enable Dark Mode in your DFIR-IRIS profile settings.")
