#!/usr/bin/env python3
"""
Script to create a test alert in DFIR-IRIS via API - JSON approach with session
"""

import requests
import re
import json

# Configuration
BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "TestPass123"

# Test alert data
test_alert = {
    "alert_title": "Test Alert - Created via API",
    "alert_description": "This is a test alert created programmatically via DFIR-IRIS API.",
    "alert_status": 1,
    "alert_tlp": 1,
    "alert_pap": 1,
    "alert_source": "API Test Script",
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
    requests.packages.urllib3.disable_warnings()
    
    session = requests.Session()
    session.verify = False
    
    print("[*] Step 1: Getting login page and CSRF token...")
    response = session.get(f"{BASE_URL}/login", allow_redirects=True)
    
    # Extract CSRF token
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
    
    # Check cookies
    print(f"[*] Session cookies: {list(session.cookies.keys())}")
    
    print("[*] Step 3: Creating test alert via API...")
    
    # Get fresh CSRF token from alerts page
    print("[*] Getting fresh CSRF token from alerts page...")
    response = session.get(f"{BASE_URL}/alerts", allow_redirects=True)
    
    csrf_token_alerts = None
    for pattern in csrf_patterns:
        csrf_match = re.search(pattern, response.text)
        if csrf_match:
            csrf_token_alerts = csrf_match.group(1)
            break
    
    if csrf_token_alerts:
        print(f"[+] Got fresh CSRF token from alerts page")
    else:
        print("[!] Could not get CSRF token from alerts page, using login token")
        csrf_token_alerts = csrf_token
    
    # Try to create alert using JSON with session cookies and CSRF header
    headers = {
        "Content-Type": "application/json",
        "Referer": f"{BASE_URL}/alerts",
        "User-Agent": "Mozilla/5.0",
        "X-CSRF-Token": csrf_token_alerts
    }
    
    # Try different endpoints
    endpoints = [
        f"{BASE_URL}/alerts/add",
        f"{BASE_URL}/api/v2/alerts",
        f"{BASE_URL}/api/alerts"
    ]
    
    for endpoint in endpoints:
        print(f"[*] Trying endpoint: {endpoint}")
        try:
            response = session.post(
                endpoint,
                json=test_alert,
                headers=headers,
                allow_redirects=True
            )
            
            print(f"[*] Response status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                try:
                    result = response.json()
                    print(f"[*] Response: {json.dumps(result, indent=2)[:500]}")
                    
                    if result.get("status") == "success":
                        print("[+] Alert created successfully!")
                        return
                    else:
                        print(f"[!] API returned error: {result.get('message')}")
                except:
                    print(f"[*] Response: {response.text[:300]}")
                    print("[+] Possible success (non-JSON response)")
                    return
            elif response.status_code == 400:
                print(f"[!] Bad request - {response.text[:200]}")
            elif response.status_code == 401:
                print(f"[!] Unauthorized - session may have expired")
            elif response.status_code == 403:
                print(f"[!] Forbidden - may need CSRF token")
            elif response.status_code == 404:
                print(f"[!] Endpoint not found, trying next...")
                continue
            else:
                print(f"[!] Unexpected status: {response.status_code}")
                print(f"[*] Response: {response.text[:300]}")
                
        except Exception as e:
            print(f"[!] Error: {e}")
    
    print("[!] All endpoints failed")

if __name__ == "__main__":
    main()
