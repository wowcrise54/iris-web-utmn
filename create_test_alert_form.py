#!/usr/bin/env python3
"""
Script to create a test alert in DFIR-IRIS via API - Form submission approach
"""

import requests
import re

# Configuration
BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "TestPass123"

def main():
    requests.packages.urllib3.disable_warnings()
    
    session = requests.Session()
    session.verify = False
    
    print("[*] Step 1: Getting login page and CSRF token...")
    response = session.get(f"{BASE_URL}/login", allow_redirects=True)
    
    # Extract CSRF token - try multiple patterns
    csrf_patterns = [
        r'name="csrf_token" value="([^"]+)"',
        r'id="csrf_token"[^>]*value="([^"]+)"',
        r'csrf_token.*?value="([^"]+)"'
    ]
    
    csrf_token = None
    for pattern in csrf_patterns:
        csrf_match = re.search(pattern, response.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
            break
    
    if not csrf_token:
        print("[!] Could not find CSRF token")
        print(f"[*] Page snippet: {response.text[:500]}")
        return
    print(f"[+] Got CSRF token")
    
    print("[*] Step 2: Logging in...")
    login_data = {
        "csrf_token": csrf_token,
        "username": USERNAME,
        "password": PASSWORD
    }
    
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    print(f"[*] Login status: {response.status_code}")
    
    if "dashboard" in response.url.lower() or "administrator" in response.text:
        print("[+] Login successful!")
    else:
        print("[!] Login may have failed")
        return
    
    print("[*] Step 3: Getting alerts page for fresh CSRF token...")
    response = session.get(f"{BASE_URL}/alerts", allow_redirects=True)
    
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    if not csrf_match:
        print("[!] Could not find CSRF token on alerts page")
        return
    csrf_token = csrf_match.group(1)
    print(f"[+] Got fresh CSRF token")
    
    print("[*] Step 4: Creating test alert...")
    
    # Prepare form data for alert creation
    # Based on the schema, we need to send form data, not JSON
    alert_data = {
        "csrf_token": csrf_token,
        "alert_title": "Test Alert - Created via API Script",
        "alert_description": "This is a test alert created programmatically via DFIR-IRIS API using form submission.",
        "alert_status": "1",  # New
        "alert_tlp": "1",     # TLP:WHITE
        "alert_pap": "1",     # PAP:WHITE
        "alert_source": "API Test Script",
        # Note: IOCs and assets may need to be added separately or in a different format
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{BASE_URL}/alerts"
    }
    
    response = session.post(
        f"{BASE_URL}/alerts/add",
        data=alert_data,
        headers=headers,
        allow_redirects=True
    )
    
    print(f"[*] Response status: {response.status_code}")
    print(f"[*] Response URL: {response.url}")
    
    # Check response
    if response.status_code in [200, 302, 303]:
        if "error" not in response.text.lower() or "alert" in response.text.lower():
            print("[+] Alert may have been created successfully!")
            print(f"[*] Response preview: {response.text[:300]}")
        else:
            print(f"[!] Response: {response.text[:500]}")
    else:
        print(f"[!] Failed. Status: {response.status_code}")
        print(f"[*] Response: {response.text[:500]}")

if __name__ == "__main__":
    main()
