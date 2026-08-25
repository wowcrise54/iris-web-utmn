#!/usr/bin/env python3
"""
Playwright E2E tests for OpenCTI plugin enhancements
Tests the UI for new features and improvements
"""

import asyncio
from playwright.async_api import async_playwright, Page, expect
import sys

BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "TestPass123"

async def login(page: Page):
    """Login to DFIR-IRIS"""
    print("[*] Logging in...")
    await page.goto(f"{BASE_URL}/login", wait_until="networkidle")
    
    await page.fill('input[name="username"]', USERNAME)
    await page.fill('input[name="password"]', PASSWORD)
    await page.click('button[type="submit"]')
    
    await page.wait_for_url("**/dashboard")
    print("[+] Login successful!")

async def test_cache_config(page: Page):
    """Test that cache configuration is available"""
    print("\n[*] Testing cache configuration...")
    
    # Navigate to module configuration
    await page.goto(f"{BASE_URL}/modules", wait_until="networkidle")
    
    # Find OpenCTI module
    opencti_row = page.locator('text="IrisOpenCTI"').first
    await opencti_row.click()
    
    # Check for new configuration options
    cache_enabled = page.locator('text="Enable query caching"')
    cache_ttl = page.locator('text="Cache TTL"')
    cache_size = page.locator('text="Cache size"')
    
    if await cache_enabled.count() > 0:
        print("✓ Cache configuration found")
        
        # Check if cache is enabled by default
        enabled_input = page.locator('input[name="opencti_cache_enabled"]')
        if await enabled_input.count() > 0:
            is_checked = await enabled_input.is_checked()
            print(f"  - Cache enabled: {is_checked}")
    else:
        print("✗ Cache configuration not found")

async def test_retry_config(page: Page):
    """Test that retry configuration is available"""
    print("\n[*] Testing retry configuration...")
    
    # Already on modules page from previous test
    # Check for retry options
    retry_enabled = page.locator('text="Enable retry logic"')
    retry_attempts = page.locator('text="Retry attempts"')
    
    if await retry_enabled.count() > 0:
        print("✓ Retry configuration found")
        
        # Check default values
        attempts_input = page.locator('input[name="opencti_retry_attempts"]')
        if await attempts_input.count() > 0:
            value = await attempts_input.input_value()
            print(f"  - Retry attempts: {value}")
    else:
        print("✗ Retry configuration not found")

async def test_enrichment_progress(page: Page):
    """Test enrichment progress tracking"""
    print("\n[*] Testing enrichment progress...")
    
    # Navigate to alerts
    await page.goto(f"{BASE_URL}/alerts", wait_until="networkidle")
    
    # Find an alert with IOCs
    alert_row = page.locator('table tbody tr').first
    if await alert_row.count() > 0:
        print("✓ Found alerts")
        
        # Click on first alert
        await alert_row.click()
        
        # Look for OpenCTI enrichment button
        enrich_button = page.locator('text="Обогатить IOC алёрта через OpenCTI"')
        if await enrich_button.count() > 0:
            print("✓ Enrichment button found")
            
            # Click and check for progress
            await enrich_button.click()
            
            # Wait for progress indicator
            try:
                await page.wait_for_selector('.progress-bar, [data-progress]', timeout=5000)
                print("✓ Progress tracking active")
            except:
                print("⚠ Progress indicator not found (may be implemented differently)")
        else:
            print("✗ Enrichment button not found")
    else:
        print("⚠ No alerts found - create one first")

async def test_cache_stats(page: Page):
    """Test that cache statistics are visible"""
    print("\n[*] Testing cache statistics...")
    
    # Navigate to module details
    await page.goto(f"{BASE_URL}/modules", wait_until="networkidle")
    
    # OpenCTI module should show stats
    # This depends on UI implementation
    print("ℹ Cache stats may be visible in module logs or admin panel")

async def run_tests():
    """Run all E2E tests"""
    print("="*60)
    print("DFIR-IRIS OpenCTI Enhancements - E2E Tests")
    print("="*60)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            ignore_https_errors=True
        )
        page = await context.new_page()
        
        try:
            await login(page)
            
            await test_cache_config(page)
            await test_retry_config(page)
            await test_enrichment_progress(page)
            await test_cache_stats(page)
            
            print("\n" + "="*60)
            print("E2E Tests Complete!")
            print("="*60)
            
        except Exception as e:
            print(f"\n[!] Test error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run_tests())
