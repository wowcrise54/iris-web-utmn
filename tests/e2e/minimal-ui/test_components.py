"""
Playwright tests for Minimalist Components (buttons, cards, inputs, tables, badges).
"""
import pytest
from playwright.sync_api import expect


BASE_URL = "http://localhost:5000"


class TestMinimalistComponents:
    """Test suite for minimalist components."""

    def test_primary_button_has_correct_styles(self, page):
        """Primary button should have correct colors, padding, and border radius"""
        page.goto(f"{BASE_URL}/dashboard")
        button = page.locator(".btn-primary").first
        expect(button).to_be_visible()
        
        styles = button.evaluate("el => ({\n  backgroundColor: getComputedStyle(el).backgroundColor,\n  color: getComputedStyle(el).color,\n  padding: getComputedStyle(el).padding,\n  borderRadius: getComputedStyle(el).borderRadius\n})")
        
        assert styles["backgroundColor"] == "rgb(37, 99, 235)"  # primary-600
        assert styles["color"] == "rgb(255, 255, 255)"
        assert "8px" in styles["padding"] and "16px" in styles["padding"]
        assert styles["borderRadius"] == "8px"

    def test_alert_card_has_minimal_design(self, page):
        """Alert card should have subtle shadow, padding, and rounded corners"""
        page.goto(f"{BASE_URL}/alerts")
        card = page.locator(".alert-card").first
        expect(card).to_be_visible()
        
        styles = card.evaluate("el => ({\n  boxShadow: getComputedStyle(el).boxShadow,\n  padding: getComputedStyle(el).padding,\n  borderRadius: getComputedStyle(el).borderRadius\n})")
        
        assert styles["boxShadow"] != "none"
        assert "24px" in styles["padding"]
        assert styles["borderRadius"] == "12px"

    def test_smart_ioc_input_detects_ip_type(self, page):
        """Smart input should detect IP address type"""
        page.goto(f"{BASE_URL}/alerts/new")
        input_field = page.locator(".smart-ioc-input")
        input_field.fill("192.168.1.1")
        
        detected_type = page.locator(".detected-type")
        expect(detected_type).to_be_visible()
        expect(detected_type).to_contain_text("IPv4")

    def test_button_has_hover_effect(self, page):
        """Primary button should change color on hover"""
        page.goto(f"{BASE_URL}/dashboard")
        button = page.locator(".btn-primary").first
        
        button.hover()
        hover_color = button.evaluate("el => getComputedStyle(el).backgroundColor")
        
        assert hover_color != "rgb(37, 99, 235)"  # Should change on hover

    def test_button_has_focus_ring_for_accessibility(self, page):
        """Button should have focus ring when focused"""
        page.goto(f"{BASE_URL}/dashboard")
        button = page.locator(".btn-primary").first
        
        button.focus()
        focus_ring = button.evaluate("el => getComputedStyle(el).boxShadow")
        
        assert "rgba(37, 99, 235, 0.5)" in focus_ring
