#!/usr/bin/env python3
"""
Script to create a test alert in DFIR-IRIS via API - JSON with session only
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
    
    print(f"[*] Session cookies: {session.cookies.get_dict()}")
    
    print("[*] Step 3: Creating test alert via JSON API...")
    
    # Try different approaches
    approaches = [
        {
            "name": "JSON with X-CSRF-Token header",
            "headers": {
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf_token,
                "Referer": f"{BASE_URL}/alerts"
            },
            "data": json.dumps(test_alert)
        },
        {
            "name": "JSON without CSRF header",
            "headers": {
                "Content-Type": "application/json",
                "Referer": f"{BASE_URL}/alerts"
            },
            "data": json.dumps(test_alert)
        },
        {
            "name": "JSON with X-Requested-With",
            "headers": {
                "Content-Type": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{BASE_URL}/alerts"
            },
            "data": json.dumps(test_alert)
        }
    ]
    
    for approach in approaches:
        print(f"\n[*] Trying: {approach['name']}")
        try:
            response = session.post(
                f"{BASE_URL}/alerts/add",
                data=approach["data"],
                headers=approach["headers"],
                allow_redirects=True
            )
            
            print(f"[*] Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                try:
                    result = response.json()
                    if result.get("status") == "success":
                        print(f"[+] SUCCESS! Alert created!")
                        print(f"[*] Response: {json.dumps(result, indent=2)[:500]}")
                        return
                    else:
                        print(f"[!] Error: {result.get('message')}")
                except:
                    print(f"[*] Response: {response.text[:300]}")
            elif response.status_code == 400:
                print(f"[!] Bad request: {response.text[:200]}")
            elif response.status_code == 403:
                print(f"[!] Forbidden - CSRF issue")
            elif response.status_code == 415:
                print(f"[!] Unsupported media type")
            else:
                print(f"[!] Status {response.status_code}: {response.text[:200]}")
                
        except Exception as e:
            print(f"[!] Exception: {e}")
    
    print("\n[!] All approaches failed")

if __name__ == "__main__":
    main()
