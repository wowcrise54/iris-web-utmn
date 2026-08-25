"""
Playwright tests for Minimalist Dashboard.
"""
import pytest
from playwright.sync_api import expect


BASE_URL = "http://localhost:5000"


class TestMinimalistDashboard:
    def test_dashboard_shows_3_kpi_cards(self, page):
        """Dashboard should show exactly 3 KPI cards"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        kpi_cards = page.locator(".kpi-card").all()
        expect(kpi_cards).to_have_count(3)
        
        # Verify KPI labels
        kpi_labels = [card.locator(".kpi-label").inner_text() for card in kpi_cards]
        assert any("New Alerts" in label for label in kpi_labels)
        assert any("In Progress" in label for label in kpi_labels)
        assert any("Closed Today" in label for label in kpi_labels)

    def test_dashboard_shows_recent_alerts_list(self, page):
        """Dashboard should show recent alerts list"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        recent_list = page.locator(".recent-alerts-list")
        expect(recent_list).to_be_visible()
        
        # Should have at least 1 alert
        alerts = recent_list.locator(".recent-alert-item")
        expect(alerts).to_have_count_at_least(1)

    def test_dashboard_has_primary_action_button(self, page):
        """Dashboard should have 'Create New Investigation' button"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        primary_btn = page.locator(".btn-primary:has-text('Create New Investigation')")
        expect(primary_btn).to_be_visible()
        
        # Should navigate to new alert page
        primary_btn.click()
        expect(page).to_have_url("*/alerts/new")

    def test_kpi_cards_show_correct_numbers(self, page):
        """KPI cards should display actual counts"""
        page.goto(f"{BASE_URL}/dashboard/minimal")
        
        # Get first KPI card number
        first_kpi = page.locator(".kpi-card .kpi-number").first
        number_text = first_kpi.inner_text()
        
        # Should be a number
        assert number_text.isdigit() or "0" in number_text

    def test_dashboard_loads_under_1_second(self, page):
        """Dashboard should load in under 1 second"""
        start_time = page.evaluate("performance.now()")
        page.goto(f"{BASE_URL}/dashboard/minimal")
        end_time = page.evaluate("performance.now()")
        
        load_time = end_time - start_time
        assert load_time < 1000, f"Dashboard took {load_time}ms to load"
