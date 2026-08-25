"""
Playwright tests for Minimalist Navigation and Search.
"""
import pytest
from playwright.sync_api import expect


BASE_URL = "http://localhost:5000"


class TestMinimalistNavigation:
    """Test suite for minimalist navigation and search features."""

    def test_minimal_navigation_has_6_sections(self, page):
        """Navigation should have exactly 6 main sections"""
        page.goto(f"{BASE_URL}/dashboard")
        nav_items = page.locator(".minimal-nav-item").all()
        expect(nav_items).to_have_count(6)
        
        # Verify section names
        expected_sections = ["Dashboard", "Alerts", "Cases", "Customers", "Modules", "Admin"]
        for i, expected in enumerate(expected_sections):
            item_text = nav_items[i].inner_text()
            expect(item_text).to_contain(expected)

    def test_global_search_opens_with_cmd_k(self, page):
        """Cmd+K should open global search modal"""
        page.goto(f"{BASE_URL}/dashboard")
        
        # Press Cmd+K (or Ctrl+K on Windows)
        if page.evaluate("navigator.platform.includes('Mac')"):
            page.keyboard.press("Meta+k")
        else:
            page.keyboard.press("Control+k")
        
        search_modal = page.locator(".search-modal")
        expect(search_modal).to_be_visible()
        
        search_input = search_modal.locator("input[type='text']")
        expect(search_input).to_be_focused()

    def test_keyboard_navigation_with_jk_keys(self, page):
        """j/k keys should navigate through alert list"""
        page.goto(f"{BASE_URL}/alerts")
        
        # Press 'j' to move down
        page.keyboard.press("j")
        first_selected = page.locator(".alert-row.selected").first
        expect(first_selected).to_be_visible()
        
        # Press 'k' to move up
        page.keyboard.press("k")
        previous_selected = page.locator(".alert-row.selected").first
        expect(previous_selected).to_be_visible()

    def test_zen_mode_toggle_exists(self, page):
        """Zen mode toggle button should be in navigation"""
        page.goto(f"{BASE_URL}/dashboard")
        
        zen_toggle = page.locator(".zen-mode-toggle")
        expect(zen_toggle).to_be_visible()
        
        # Click to enable zen mode
        zen_toggle.click()
        
        # Check that sidebars are hidden
        sidebar = page.locator(".sidebar")
        expect(sidebar).to_have_css("display", "none")

    def test_shortcuts_modal_opens_with_slash(self, page):
        """Pressing / should open shortcuts modal"""
        page.goto(f"{BASE_URL}/dashboard")
        
        page.keyboard.press("/")
        
        shortcuts_modal = page.locator(".shortcuts-modal")
        expect(shortcuts_modal).to_be_visible()
        
        # Should list all available shortcuts
        shortcuts_list = shortcuts_modal.locator(".shortcut-item")
        expect(shortcuts_list).to_have_count_at_least(5)
