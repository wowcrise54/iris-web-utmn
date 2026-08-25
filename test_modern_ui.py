#!/usr/bin/env python3
"""
Playwright tests for DFIR-IRIS Modern UI Enhancements

Install:
    pip install playwright
    playwright install

Run:
    python test_modern_ui.py
"""

import asyncio
from playwright.async_api import async_playwright, Page, expect
import sys
import os

BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "TestPass123"

async def login(page: Page):
    """Login to DFIR-IRIS"""
    print("[*] Navigating to login page...")
    await page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    
    # Fill login form
    await page.fill('input[name="username"]', USERNAME)
    await page.fill('input[name="password"]', PASSWORD)
    
    # Submit form
    await page.click('button[type="submit"]')
    
    # Wait for redirect to dashboard
    await page.wait_for_url("**/dashboard")
    print("[+] Login successful!")

async def test_status_badges(page: Page):
    """Test enhanced status badges"""
    print("\n[*] Testing status badges...")
    
    # Navigate to alerts page
    await page.goto(f"{BASE_URL}/alerts", wait_until="networkidle")
    
    # Check for status badges with modern styling
    status_badges = page.locator('.badge-new, .badge-open, .badge-closed, .badge-status-new, .badge-status-open, .badge-status-closed')
    count = await status_badges.count()
    
    if count > 0:
        print(f"[+] Found {count} status badges")
        
        # Check if badges have modern styling (background gradient)
        for i in range(min(count, 3)):
            badge = status_badges.nth(i)
            background = await badge.evaluate("el => window.getComputedStyle(el).background")
            print(f"    Badge {i+1}: {background[:50]}...")
    else:
        print("[!] No status badges found - may need to create alerts first")

async def test_glassmorphism_cards(page: Page):
    """Test glassmorphism card effects"""
    print("\n[*] Testing glassmorphism cards...")
    
    # Navigate to dashboard
    await page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle")
    
    # Check for cards with modern styling
    cards = page.locator('.card, .card-modern, .alert-card-modern')
    count = await cards.count()
    
    if count > 0:
        print(f"[+] Found {count} cards")
        
        # Check first card for glassmorphism effects
        first_card = cards.first
        backdrop_filter = await first_card.evaluate("el => window.getComputedStyle(el).backdropFilter")
        border_radius = await first_card.evaluate("el => window.getComputedStyle(el).borderRadius")
        
        print(f"    Backdrop filter: {backdrop_filter}")
        print(f"    Border radius: {border_radius}")
        
        if "blur" in backdrop_filter or border_radius != "0px":
            print("[+] Glassmorphism effects detected!")
        else:
            print("[!] Glassmorphism effects not detected")
    else:
        print("[!] No cards found")

async def test_severity_indicators(page: Page):
    """Test severity indicator colors"""
    print("\n[*] Testing severity indicators...")
    
    # Navigate to alerts page
    await page.goto(f"{BASE_URL}/alerts", wait_until="networkidle")
    
    # Check for severity badges
    severity_badges = page.locator('.severity-low, .severity-medium, .severity-high, .severity-critical')
    count = await severity_badges.count()
    
    if count > 0:
        print(f"[+] Found {count} severity indicators")
        
        # Check colors
        for i in range(min(count, 4)):
            badge = severity_badges.nth(i)
            color = await badge.evaluate("el => window.getComputedStyle(el).color")
            background = await badge.evaluate("el => window.getComputedStyle(el).background")
            print(f"    Severity {i+1}: color={color}, bg={background[:30]}...")
    else:
        print("[!] No severity indicators found")

async def test_ioc_badges(page: Page):
    """Test IOC badge styling"""
    print("\n[*] Testing IOC badges...")
    
    # Navigate to a specific alert with IOCs
    await page.goto(f"{BASE_URL}/alerts/2", wait_until="networkidle")
    
    # Check for IOC badges
    ioc_badges = page.locator('.ioc-badge-modern, .ioc-type-ip, .ioc-type-domain, .ioc-type-hash')
    count = await ioc_badges.count()
    
    if count > 0:
        print(f"[+] Found {count} IOC badges")
        
        # Check styling
        for i in range(min(count, 3)):
            badge = ioc_badges.nth(i)
            background = await badge.evaluate("el => window.getComputedStyle(el).background")
            print(f"    IOC {i+1}: {background[:40]}...")
    else:
        print("[!] No IOC badges found - alert may not have IOCs")

async def test_tags(page: Page):
    """Test modern tag styling"""
    print("\n[*] Testing tags...")
    
    # Navigate to alerts page
    await page.goto(f"{BASE_URL}/alerts", wait_until="networkidle")
    
    # Check for tags
    tags = page.locator('.tag-modern, .tag-opencti')
    count = await tags.count()
    
    if count > 0:
        print(f"[+] Found {count} tags")
        
        # Check OpenCTI tags specifically
        opencti_tags = page.locator('.tag-opencti')
        opencti_count = await opencti_tags.count()
        if opencti_count > 0:
            print(f"[+] Found {opencti_count} OpenCTI tags with special styling")
    else:
        print("[!] No tags found")

async def test_buttons(page: Page):
    """Test modern button styling"""
    print("\n[*] Testing buttons...")
    
    # Navigate to alerts page
    await page.goto(f"{BASE_URL}/alerts", wait_until="networkidle")
    
    # Check for modern buttons
    buttons = page.locator('.btn-modern-primary, .btn-modern-secondary, button')
    count = await buttons.count()
    
    if count > 0:
        print(f"[+] Found {count} buttons")
        
        # Check first button styling
        first_button = buttons.first
        background = await first_button.evaluate("el => window.getComputedStyle(el).background")
        border_radius = await first_button.evaluate("el => window.getComputedStyle(el).borderRadius")
        
        print(f"    First button: bg={background[:30]}..., radius={border_radius}")
    else:
        print("[!] No buttons found")

async def run_tests():
    """Run all tests"""
    print("=" * 60)
    print("DFIR-IRIS Modern UI Enhancements - Playwright Tests")
    print("=" * 60)
    
    async with async_playwright() as p:
        # Launch browser
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = await context.new_page()
        
        try:
            # Login first
            await login(page)
            
            # Run all tests
            await test_status_badges(page)
            await test_glassmorphism_cards(page)
            await test_severity_indicators(page)
            await test_ioc_badges(page)
            await test_tags(page)
            await test_buttons(page)
            
            print("\n" + "=" * 60)
            print("All tests completed!")
            print("=" * 60)
            
        except Exception as e:
            print(f"\n[!] Test error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
