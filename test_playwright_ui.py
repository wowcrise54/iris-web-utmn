"""
Simplified Playwright tests for DFIR-IRIS Modern UI variants.

Tests verify that UI components render correctly and have expected visual properties.

Install dependencies:
    pip install playwright
    playwright install

Run tests:
    python test_playwright_ui.py
"""

from pathlib import Path
from playwright.sync_api import sync_playwright


def get_base_url():
    """Get base URL for the sketch files."""
    base_path = Path(__file__).parent / 'sketches'
    return f"file://{base_path.resolve()}/"


def test_calm_editorial_loads():
    """Test that calm editorial design loads without errors."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}001-calm-editorial/index.html")
        title = page.title()
        
        assert "DFIR-IRIS" in title
        assert "Calm Editorial" in title
        
        heading = page.locator("h1")
        heading.wait_for(state="visible")
        assert "DFIR-IRIS" in heading.inner_text()
        
        browser.close()
        print("✓ Calm Editorial design loads correctly")


def test_calm_editorial_status_badges():
    """Test that all status badges are visible in calm editorial design."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}001-calm-editorial/index.html")
        
        statuses = ["New", "Open", "Closed", "Resolved", "Pending", "Critical"]
        for status in statuses:
            badge = page.locator(f".badge:has-text('{status}')").first
            badge.wait_for(state="visible")
            assert badge.is_visible()
        
        browser.close()
        print("✓ All status badges visible in Calm Editorial")


def test_calm_editorial_cards():
    """Test that alert cards render correctly."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}001-calm-editorial/index.html")
        
        cards = page.locator(".card")
        cards.first.wait_for(state="visible")
        card_count = cards.count()
        assert card_count >= 4, "Should have at least 4 alert cards"
        
        first_card = cards.nth(0)
        assert first_card.locator(".card-header").is_visible()
        assert first_card.locator(".card-body").is_visible()
        
        browser.close()
        print(f"✓ Calm Editorial has {card_count} alert cards")


def test_utilitarian_dense_loads():
    """Test that utilitarian dense design loads without errors."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}002-utilitarian-dense/index.html")
        title = page.title()
        
        assert "DFIR-IRIS" in title
        assert "Utilitarian Dense" in title
        
        stats_bar = page.locator(".stats-bar")
        stats_bar.wait_for(state="visible")
        
        browser.close()
        print("✓ Utilitarian Dense design loads correctly")


def test_utilitarian_dense_data_density():
    """Test that utilitarian dense design has high information density."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}002-utilitarian-dense/index.html")
        
        table = page.locator(".data-table")
        table.wait_for(state="visible")
        
        ioc_values = page.locator(".card-data-value")
        ioc_values.first.wait_for(state="visible")
        
        tags = page.locator(".tag")
        tag_count = tags.count()
        assert tag_count >= 5, "Should have many compact tags"
        
        browser.close()
        print(f"✓ Utilitarian Dense has {tag_count} tags (high density)")


def test_utilitarian_dense_dark_theme():
    """Test that utilitarian dense uses dark theme."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}002-utilitarian-dense/index.html")
        
        bg_color = page.evaluate("""() => {
            const body = document.querySelector('body');
            return window.getComputedStyle(body).backgroundColor;
        }""")
        
        assert bg_color != "rgb(255, 255, 255)", "Should not be white background"
        
        browser.close()
        print(f"✓ Utilitarian Dense uses dark theme (bg: {bg_color})")


def test_glassmorphism_loads():
    """Test that glassmorphism design loads without errors."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}003-glassmorphism-modern/index.html")
        title = page.title()
        
        assert "DFIR-IRIS" in title
        assert "Glassmorphism" in title
        
        cards = page.locator(".card")
        cards.first.wait_for(state="visible")
        
        browser.close()
        print("✓ Glassmorphism design loads correctly")


def test_glassmorphism_animations():
    """Test that glassmorphism design has animations."""
    base_url = get_base_url()
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        
        page.goto(f"{base_url}003-glassmorphism-modern/index.html")
        
        critical_badge = page.locator(".badge-critical").first
        critical_badge.wait_for(state="visible")
        
        has_animation = page.evaluate("""() => {
            const badge = document.querySelector('.badge-critical');
            if (!badge) return false;
            const style = window.getComputedStyle(badge);
            return style.animationName !== 'none';
        }""")
        
        assert has_animation, "Critical badge should have animation"
        
        browser.close()
        print("✓ Glassmorphism critical badge has animation")


def test_all_variants_have_severity_indicators():
    """Test that all variants have severity indicators."""
    base_url = get_base_url()
    variants = ["001-calm-editorial", "002-utilitarian-dense", "003-glassmorphism-modern"]
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        
        for variant in variants:
            page = browser.new_page()
            page.goto(f"{base_url}{variant}/index.html")
            
            severities = ["Low", "Medium", "High", "Critical"]
            for severity in severities:
                severity_elem = page.locator(f".severity:has-text('{severity}')").first
                severity_elem.wait_for(state="visible")
            
            page.close()
        
        browser.close()
        print("✓ All variants have severity indicators")


def test_all_variants_have_buttons():
    """Test that all variants have action buttons."""
    base_url = get_base_url()
    variants = ["001-calm-editorial", "002-utilitarian-dense", "003-glassmorphism-modern"]
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        
        for variant in variants:
            page = browser.new_page()
            page.goto(f"{base_url}{variant}/index.html")
            
            buttons = page.locator(".btn")
            buttons.first.wait_for(state="visible")
            button_count = buttons.count()
            assert button_count >= 2, f"{variant} should have at least 2 buttons"
            
            page.close()
        
        browser.close()
        print("✓ All variants have action buttons")


def test_all_variants_responsive():
    """Test that variants adapt to different viewport sizes."""
    base_url = get_base_url()
    variants = ["001-calm-editorial", "002-utilitarian-dense", "003-glassmorphism-modern"]
    
    with sync_playwright() as p:
        browser = p.chromium.launch()
        
        for variant in variants:
            page = browser.new_page()
            
            # Test desktop viewport
            page.set_viewport_size({"width": 1920, "height": 1080})
            page.goto(f"{base_url}{variant}/index.html")
            desktop_cards = page.locator(".card").count()
            
            # Test mobile viewport
            page.set_viewport_size({"width": 375, "height": 667})
            page.goto(f"{base_url}{variant}/index.html")
            mobile_cards = page.locator(".card").count()
            
            assert desktop_cards == mobile_cards, "Card count should be consistent"
            
            page.close()
        
        browser.close()
        print("✓ All variants are responsive")


if __name__ == "__main__":
    print("Running DFIR-IRIS Modern UI Playwright Tests\n")
    print("=" * 50)
    
    tests = [
        test_calm_editorial_loads,
        test_calm_editorial_status_badges,
        test_calm_editorial_cards,
        test_utilitarian_dense_loads,
        test_utilitarian_dense_data_density,
        test_utilitarian_dense_dark_theme,
        test_glassmorphism_loads,
        test_glassmorphism_animations,
        test_all_variants_have_severity_indicators,
        test_all_variants_have_buttons,
        test_all_variants_responsive,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__}: {e}")
            failed += 1
    
    print("=" * 50)
    print(f"\nResults: {passed} passed, {failed} failed")
    
    if failed > 0:
        exit(1)
