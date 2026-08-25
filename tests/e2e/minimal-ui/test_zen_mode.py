"""
Playwright tests for Zen Mode functionality.
"""
import pytest
from playwright.sync_api import expect


BASE_URL = "http://localhost:5000"


class TestZenMode:
    def test_zen_mode_toggle_is_visible(self, page):
        """Zen mode toggle button should be visible in navigation"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        zen_toggle = page.locator(".zen-mode-toggle")
        expect(zen_toggle).to_be_visible()
        expect(zen_toggle).to_have_text("◐")

    def test_zen_mode_hides_sidebars(self, page):
        """Zen mode should hide all sidebars"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        # Enable zen mode
        page.locator(".zen-mode-toggle").click()
        
        # Check sidebars are hidden
        sidebar = page.locator(".sidebar")
        expect(sidebar).to_have_css("display", "none")
        
        quick_sidebar = page.locator(".quick-sidebar")
        expect(quick_sidebar).to_have_css("display", "none")

    def test_zen_mode_maximizes_content_area(self, page):
        """Zen mode should maximize the main content area"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        # Get initial width
        initial_width = page.locator(".main-panel").evaluate(
            "el => getComputedStyle(el).width"
        )
        
        # Enable zen mode
        page.locator(".zen-mode-toggle").click()
        
        # Get zen mode width
        zen_width = page.locator(".main-panel").evaluate(
            "el => getComputedStyle(el).width"
        )
        
        # Zen mode should be wider
        assert float(zen_width.replace("px", "")) > float(initial_width.replace("px", ""))

    def test_zen_mode_persists_across_pages(self, page):
        """Zen mode preference should persist when navigating"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        # Enable zen mode
        page.locator(".zen-mode-toggle").click()
        
        # Navigate to another page
        page.goto(f"{BASE_URL}/alerts")
        
        # Zen mode should still be active
        sidebar = page.locator(".sidebar")
        expect(sidebar).to_have_css("display", "none")

    def test_esc_exits_zen_mode(self, page):
        """Pressing ESC should exit zen mode"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        # Enable zen mode
        page.locator(".zen-mode-toggle").click()
        
        # Press ESC
        page.keyboard.press("Escape")
        
        # Zen mode should be disabled
        sidebar = page.locator(".sidebar")
        expect(sidebar).to_have_css("display", "block")
