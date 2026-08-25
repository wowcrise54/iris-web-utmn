"""
Playwright tests for Smart IOC Input.
"""
import pytest
from playwright.sync_api import expect


BASE_URL = "http://localhost:5000"


class TestSmartIOCInput:
    """Test suite for smart IOC input auto-detection."""

    def test_detects_ipv4_address(self, page):
        """Smart input should detect IPv4 addresses"""
        page.goto(f"{BASE_URL}/alerts/new")
        
        input_field = page.locator(".smart-ioc-input")
        input_field.fill("192.168.1.1")
        
        detected_type = page.locator(".detected-type")
        expect(detected_type).to_be_visible()
        expect(detected_type).to_contain_text("IPv4 Address")

    def test_detects_domain(self, page):
        """Smart input should detect domains"""
        page.goto(f"{BASE_URL}/alerts/new")
        
        input_field = page.locator(".smart-ioc-input")
        input_field.fill("malicious-example.com")
        
        detected_type = page.locator(".detected-type")
        expect(detected_type).to_be_visible()
        expect(detected_type).to_contain_text("Domain")

    def test_detects_sha256_hash(self, page):
        """Smart input should detect SHA256 hashes"""
        page.goto(f"{BASE_URL}/alerts/new")
        
        input_field = page.locator(".smart-ioc-input")
        input_field.fill("a" * 64)  # Valid 64-char SHA256 hash
        
        detected_type = page.locator(".detected-type")
        expect(detected_type).to_be_visible()
        expect(detected_type).to_contain_text("SHA256")

    def test_detects_url(self, page):
        """Smart input should detect URLs"""
        page.goto(f"{BASE_URL}/alerts/new")
        
        input_field = page.locator(".smart-ioc-input")
        input_field.fill("https://evil.com/malware.exe")
        
        detected_type = page.locator(".detected-type")
        expect(detected_type).to_be_visible()
        expect(detected_type).to_contain_text("URL")

    def test_shows_error_for_invalid_input(self, page):
        """Smart input should show error for unrecognized patterns"""
        page.goto(f"{BASE_URL}/alerts/new")
        
        input_field = page.locator(".smart-ioc-input")
        input_field.fill("not a valid ioc")
        
        error_message = page.locator(".input-error")
        expect(error_message).to_be_visible()
        expect(error_message).to_contain_text("Unrecognized IOC type")
