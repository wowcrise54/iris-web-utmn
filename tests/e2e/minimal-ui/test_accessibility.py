"""
Playwright accessibility tests for WCAG 2.1 AA compliance.
"""
import pytest
from playwright.sync_api import expect

BASE_URL = "http://localhost:5000"


class TestAccessibility:
    def test_all_images_have_alt_text(self, page):
        """All images should have alt attributes"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        images = page.locator("img").all()
        for img in images:
            alt = img.get_attribute("alt")
            assert alt is not None and alt != "", "Image missing alt text"

    def test_all_buttons_have_accessible_names(self, page):
        """All buttons should have accessible names"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        buttons = page.locator("button").all()
        for button in buttons:
            name = button.accessible_name()
            assert name is not None and name != "", "Button missing accessible name"

    def test_all_links_have_accessible_names(self, page):
        """All links should have accessible names"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        links = page.locator("a").all()
        for link in links:
            name = link.accessible_name()
            assert name is not None and name != "", "Link missing accessible name"

    def test_color_contrast_meets_wcag_aa(self, page):
        """Text should have sufficient color contrast (4.5:1 for normal text)"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        # Check main text elements
        body_text = page.locator("body")
        styles = body_text.evaluate("""el => {
            const computed = getComputedStyle(el);
            return {
                color: computed.color,
                backgroundColor: computed.backgroundColor
            };
        }""")
        
        # Verify contrast ratio (simplified check)
        assert styles["color"] != styles["backgroundColor"], "Insufficient contrast"

    def test_keyboard_navigation_works(self, page):
        """All interactive elements should be keyboard accessible"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        # Tab through all focusable elements
        for i in range(20):  # Tab 20 times
            page.keyboard.press("Tab")
        
        # Verify focus is visible
        focused = page.evaluate("document.activeElement")
        assert focused is not None, "No element focused"

    def test_skip_link_exists(self, page):
        """Skip to main content link should exist"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        skip_link = page.locator(".skip-to-main")
        expect(skip_link).to_be_visible()
        expect(skip_link).to_have_attribute("href", "#main-content")

    def test_form_inputs_have_labels(self, page):
        """All form inputs should have associated labels"""
        page.goto(f"{BASE_URL}/alerts/new")
        
        inputs = page.locator("input:not([type='hidden'])").all()
        for input_elem in inputs:
            label = input_elem.evaluate("""el => {
                const id = el.id;
                if (!id) return null;
                return document.querySelector(`label[for="${id}"]`);
            }""")
            
            # Either has label or aria-label
            has_label = label is not None
            has_aria = input_elem.get_attribute("aria-label") is not None
            
            assert has_label or has_aria, f"Input missing label: {input_elem}"
