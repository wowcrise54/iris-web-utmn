#!/usr/bin/env python3
"""
Create a test alert with IOC that will be enriched by OpenCTI
"""

import requests
import re
import json

BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "uWn9Q3lK>DJhia.v"

# Test IOC - IP address that might be in OpenCTI
test_ip = "185.220.101.1"  # Known Tor exit node (often in threat feeds)

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
        print(f"[*] Page snippet: {response.text[:300]}")
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
    
    if "dashboard" in response.url.lower():
        print("[+] Login successful!")
    else:
        print("[!] Login may have failed")
        return
    
    print("[*] Step 3: Creating test alert with IOC...")
    
    # Get fresh CSRF token
    response = session.get(f"{BASE_URL}/alerts", allow_redirects=True)
    csrf_match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    if csrf_match:
        csrf_token = csrf_match.group(1)
    
    # Create alert with IOC
    alert_data = {
        "alert_title": "Test Alert - OpenCTI Enrichment",
        "alert_description": f"Test alert with IP {test_ip} to verify OpenCTI enrichment",
        "alert_status": 1,  # New
        "alert_tlp": 1,     # TLP:WHITE
        "alert_pap": 1,     # PAP:WHITE
        "alert_source": "API Test Script",
        "alert_iocs": [
            {
                "ioc_value": test_ip,
                "ioc_type": "ip-addr",
                "ioc_description": f"Test IP for OpenCTI enrichment - {test_ip}",
                "ioc_tlp": 1
            }
        ],
        "alert_assets": [
            {
                "asset_name": test_ip,
                "asset_type": "ip-addr",
                "asset_description": "Test asset from API",
                "asset_ip": [test_ip]
            }
        ]
    }
    
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf_token,
        "Referer": f"{BASE_URL}/alerts"
    }
    
    response = session.post(
        f"{BASE_URL}/alerts/add",
        json=alert_data,
        headers=headers,
        allow_redirects=True
    )
    
    print(f"[*] Response status: {response.status_code}")
    
    if response.status_code in [200, 201]:
        try:
            result = response.json()
            if result.get("status") == "success":
                alert_id = result.get("data", {}).get("alert_id")
                print(f"[+] Alert created successfully! Alert ID: {alert_id}")
                
                # Wait a bit for OpenCTI enrichment
                print(f"[*] Waiting for OpenCTI enrichment...")
                import time
                time.sleep(5)
                
                # Check if enrichment happened
                print(f"[*] Checking alert details...")
                response = session.get(f"{BASE_URL}/alerts/{alert_id}", allow_redirects=True)
                
                # Try to get alert via API
                response = session.get(
                    f"{BASE_URL}/alerts/filter",
                    params={"alert_ids": alert_id},
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == "success":
                        alerts = data.get("data", {}).get("alerts", [])
                        if alerts:
                            alert = alerts[0]
                            tags = alert.get("alert_tags", [])
                            print(f"[*] Alert tags: {tags}")
                            
                            # Check for OpenCTI tags
                            opencti_tags = [t for t in tags if "opencti" in str(t).lower()]
                            if opencti_tags:
                                print(f"[+] OpenCTI enrichment found!")
                                print(f"    Tags: {opencti_tags}")
                            else:
                                print(f"[*] No OpenCTI tags yet (may take time)")
                
                return alert_id
            else:
                print(f"[!] Error: {result.get('message')}")
        except Exception as e:
            print(f"[!] Error parsing response: {e}")
            print(f"[*] Response: {response.text[:500]}")
    else:
        print(f"[!] Failed. Status: {response.status_code}")
        print(f"[*] Response: {response.text[:500]}")

if __name__ == "__main__":
    main()
