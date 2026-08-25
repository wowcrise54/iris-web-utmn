"""
Playwright tests for Minimalist Base Styles.
"""
import pytest
from playwright.sync_api import sync_playwright


@pytest.fixture(scope="session")
def browser():
    """Create a browser instance for testing."""
    with sync_playwright() as p:
        # Launch browser (headless for CI, visible for local debugging)
        browser = p.chromium.launch(headless=True)
        yield browser
        browser.close()


@pytest.fixture(scope="session")
def context(browser):
    """Create a browser context."""
    return browser.new_context(
        viewport={'width': 1280, 'height': 720}
    )


@pytest.fixture(scope="session")
def page(context):
    """Create a page instance."""
    return context.new_page()


BASE_URL = "http://localhost:5000"


class TestMinimalistBaseStyles:
    """Test suite for minimalist base styles."""

    def test_should_load_inter_font_correctly(self, page):
        """Test that Inter font is loaded correctly."""
        page.goto(f"{BASE_URL}/dashboard")
        body_font = page.evaluate("() => getComputedStyle(document.body).fontFamily")
        assert "Inter" in body_font, f"Expected 'Inter' in font family, got: {body_font}"

    def test_should_apply_correct_base_font_size(self, page):
        """Test that base font size is 16px."""
        page.goto(f"{BASE_URL}/dashboard")
        font_size = page.evaluate("() => getComputedStyle(document.body).fontSize")
        assert font_size == "16px", f"Expected '16px', got: {font_size}"

    def test_should_have_correct_line_height_for_body_text(self, page):
        """Test that line height is 24px (1.5 * 16px)."""
        page.goto(f"{BASE_URL}/dashboard")
        line_height = page.evaluate("() => getComputedStyle(document.body).lineHeight")
        assert line_height == "24px", f"Expected '24px', got: {line_height}"

    def test_should_render_headings_with_correct_hierarchy(self, page):
        """Test that h1 headings have correct font size (30px)."""
        page.goto(f"{BASE_URL}/dashboard")
        h1_element = page.query_selector("h1")
        if h1_element:
            h1_size = page.evaluate("() => getComputedStyle(document.querySelector('h1')).fontSize")
            assert h1_size == "30px", f"Expected '30px' for h1, got: {h1_size}"

    def test_should_apply_correct_spacing_between_elements(self, page):
        """Test that paragraphs have correct margin (16px)."""
        page.goto(f"{BASE_URL}/dashboard")
        paragraphs = page.query_selector_all("p")
        if len(paragraphs) >= 2:
            margin = paragraphs[0].evaluate("el => getComputedStyle(el).marginBottom")
            assert margin == "16px", f"Expected '16px' margin, got: {margin}"
