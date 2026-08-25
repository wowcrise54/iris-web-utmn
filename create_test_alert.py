#!/usr/bin/env python3
"""
Script to create a test alert in DFIR-IRIS via API
"""

import requests
import json

# Configuration
BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "TestPass123"  # или U3.3%~{9&2UmzoUf

# Test alert data
test_alert = {
    "alert_title": "Test Alert - Created via API",
    "alert_description": "This is a test alert created programmatically via DFIR-IRIS API.",
    "alert_status": 1,  # 1 = New
    "alert_tlp": 1,     # 1 = TLP:WHITE
    "alert_pap": 1,     # 1 = PAP:WHITE
    "alert_source": "API Test Script",
    "alert_tags": [{"tag_id": 1}],  # Optional: add tags
    "alert_iocs": [
        {
            "ioc_value": "192.168.1.100",
            "ioc_type": "ip-addr",
            "ioc_description": "Test IP address",
            "ioc_tlp": 1
        },
        {
            "ioc_value": "malicious-domain.com",
            "ioc_type": "domain",
            "ioc_description": "Test domain",
            "ioc_tlp": 1
        }
    ],
    "alert_assets": [
        {
            "asset_name": "test-server.example.com",
            "asset_type": "fqdn",
            "asset_description": "Test asset created via API",
            "asset_ip": ["192.168.1.100"]
        }
    ]
}

def main():
    # Disable SSL warnings
    requests.packages.urllib3.disable_warnings()
    
    # Step 1: Login and get session cookie
    print(f"[*] Connecting to {BASE_URL}...")
    
    # Try to login
    login_url = f"{BASE_URL}/login"
    alerts_url = f"{BASE_URL}/alerts/add"
    
    # Create a session to persist cookies
    session = requests.Session()
    session.verify = False  # Ignore SSL certificate errors
    
    # First, get the initial page to establish session
    try:
        response = session.get(f"{BASE_URL}/", allow_redirects=True)
        print(f"[*] Got initial page, status: {response.status_code}")
    except Exception as e:
        print(f"[!] Error getting initial page: {e}")
        return
    
    # Note: DFIR-IRIS uses CSRF tokens and session-based auth
    # We need to get the CSRF token first
    try:
        response = session.get(f"{BASE_URL}/login", allow_redirects=True)
        print(f"[*] Login page status: {response.status_code}")
        
        # Extract CSRF token from the page
        import re
        # Try multiple patterns for CSRF token
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
            print("[!] Could not find CSRF token in login page")
            # Debug: print a snippet of the page
            print(f"[*] Page snippet: {response.text[:500]}")
            return
        print(f"[*] Got CSRF token: {csrf_token[:20]}...")
        
    except Exception as e:
        print(f"[!] Error getting login page: {e}")
        return
    
    # Step 2: Login with credentials
    login_data = {
        "csrf_token": csrf_token,
        "username": USERNAME,
        "password": PASSWORD
    }
    
    try:
        response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
        print(f"[*] Login response status: {response.status_code}")
        
        if response.status_code != 200:
            print(f"[!] Login failed with status {response.status_code}")
            return
        
        # Check if we're redirected to dashboard (successful login)
        if "dashboard" in response.url or "Alerts" in response.text:
            print("[+] Login successful!")
        else:
            print("[!] Login may have failed - checking response...")
            # Try alternative: check if we have session cookies
            print(f"[*] Cookies: {session.cookies.get_dict()}")
        
    except Exception as e:
        print(f"[!] Error during login: {e}")
        return
    
    # Step 3: Create the alert
    print("[*] Creating test alert...")
    
    # Get fresh CSRF token after login
    try:
        response = session.get(f"{BASE_URL}/alerts", allow_redirects=True)
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
            print("[!] Could not find CSRF token on alerts page")
            return
        
        print(f"[*] Got fresh CSRF token for alerts: {csrf_token[:20]}...")
        
    except Exception as e:
        print(f"[!] Error getting alerts page: {e}")
        return
    
    # Prepare the API request
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf_token,
        "X-Requested-With": "XMLHttpRequest"
    }
    
    # Also try to get CSRF from cookie
    csrf_cookie = session.cookies.get('csrf_token') or session.cookies.get('csrf')
    if csrf_cookie:
        print(f"[*] CSRF cookie: {csrf_cookie[:20]}...")
    
    try:
        response = session.post(
            f"{BASE_URL}/alerts/add",
            json=test_alert,
            headers=headers,
            allow_redirects=True
        )
        
        print(f"[*] Alert creation response status: {response.status_code}")
        print(f"[*] Response body: {response.text[:500]}")
        
        if response.status_code in [200, 201]:
            result = response.json()
            if result.get("status") == "success":
                alert_id = result.get("data", {}).get("alert_id")
                print(f"[+] Alert created successfully! Alert ID: {alert_id}")
            else:
                print(f"[!] Alert creation returned error: {result.get('message')}")
        else:
            print(f"[!] Failed to create alert. Status: {response.status_code}")
            
    except Exception as e:
        print(f"[!] Error creating alert: {e}")

if __name__ == "__main__":
    main()
