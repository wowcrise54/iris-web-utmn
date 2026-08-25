import pytest
from playwright.sync_api import expect


BASE_URL = "http://localhost:5000"


class TestPerformance:
    """Test suite for performance optimization."""
    
    def test_dashboard_loads_under_1_second(self, page):
        """Dashboard should load in under 1 second"""
        page.goto(f"{BASE_URL}/dashboard")
        
        # Get navigation timing
        timing = page.evaluate("() => performance.timing")
        load_time = timing.domContentLoadedEventEnd - timing.navigationStart
        
        assert load_time < 1000, f"Dashboard took {load_time}ms to load"

    def test_css_bundle_under_50kb(self, page):
        """Minimalist CSS bundle should be under 50KB"""
        response = page.goto(f"{BASE_URL}/static/assets/css/minimalist-base.css")
        size = len(response.body())
        
        assert size < 50000, f"CSS bundle is {size} bytes, should be under 50KB"

    def test_js_bundle_under_100kb(self, page):
        """Minimalist JS bundle should be under 100KB"""
        response = page.goto(f"{BASE_URL}/static/assets/js/minimalist-bundle.js")
        size = len(response.body())
        
        assert size < 100000, f"JS bundle is {size} bytes, should be under 100KB"

    def test_first_contentful_paint_under_1_second(self, page):
        """First Contentful Paint should be under 1 second"""
        page.goto("/dashboard")
        
        fcp = page.evaluate("""() => {
            return new Promise((resolve) => {
                new PerformanceObserver((list) => {
                    const entries = list.getEntries();
                    const fcp = entries.find(e => e.name === 'first-contentful-paint');
                    resolve(fcp ? fcp.startTime : 0);
                }).observe({type: 'paint', buffered: true});
            });
        }""")
        
        assert fcp < 1000, f"FCP took {fcp}ms, should be under 1s"

    def test_no_console_errors(self, page):
        """Page should not have console errors"""
        errors = []
        
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto("/dashboard")
        
        assert len(errors) == 0, f"Found {len(errors)} console errors: {errors}"
