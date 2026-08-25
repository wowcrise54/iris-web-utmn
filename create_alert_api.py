#!/usr/bin/env python3
"""
Create a test alert via API and verify OpenCTI enrichment
"""

import requests
import re
import json
import time

BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "TestPass123"

def main():
    requests.packages.urllib3.disable_warnings()
    session = requests.Session()
    session.verify = False
    
    print("[*] Step 1: Getting login page...")
    response = session.get(f"{BASE_URL}/login", allow_redirects=True)
    print(f"[*] Login page status: {response.status_code}")
    
    # Extract CSRF token - try multiple patterns
    csrf_patterns = [
        r'id="csrf_token"[^>]*value="([^"]+)"',
        r'name="csrf_token"[^>]*value="([^"]+)"',
        r'value="([^"]+)"[^>]*id="csrf_token"',
        r'"csrf_token"\s*:\s*"([^"]+)"'
    ]
    
    csrf_token = None
    for pattern in csrf_patterns:
        csrf_match = re.search(pattern, response.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
            break
    print(f"[+] Found CSRF token")
    
    # Login
    login_data = {
        "csrf_token": csrf_token,
        "username": USERNAME,
        "password": PASSWORD
    }
    
    print("[*] Step 2: Logging in...")
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    if "dashboard" in response.url.lower() or "alerts" in response.url.lower():
        print("[+] Login successful!")
    else:
        print(f"[!] Login failed. URL: {response.url}")
        print(f"    Response: {response.text[:200]}")
        return
    
    # Get fresh CSRF token from alerts page
    print("[*] Step 3: Getting alerts page for fresh CSRF...")
    response = session.get(f"{BASE_URL}/alerts", allow_redirects=True)
    
    csrf_patterns = [
        r'name="csrf_token" value="([^"]+)"',
        r'"csrf_token"\s*:\s*"([^"]+)"',
        r'csrf_token.*?value="([^"]+)"'
    ]
    
    csrf_token = None
    for pattern in csrf_patterns:
        match = re.search(pattern, response.text)
        if match:
            csrf_token = match.group(1)
            break
    
    if not csrf_token:
        print("[!] Could not find CSRF token on alerts page")
        return
    print(f"[+] Got fresh CSRF token")
    
    # Create alert via API
    print("[*] Step 4: Creating alert via API...")
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf_token,
        "Referer": f"{BASE_URL}/alerts"
    }
    
    alert_data = {
        "alert_title": "API Test Alert - OpenCTI",
        "alert_description": "Alert created via API to test OpenCTI enrichment",
        "alert_source": "API Test",
        "alert_severity_id": 1,
        "alert_status_id": 2,
        "alert_customer_id": 1,
        "alert_iocs": [
            {
                "ioc_value": "9.9.9.9",
                "ioc_type_id": 76,
                "ioc_description": "Quad9 DNS for OpenCTI test"
            }
        ]
    }
    
    response = session.post(
        f"{BASE_URL}/alerts/add",
        json=alert_data,
        headers=headers,
        allow_redirects=True
    )
    
    print(f"[*] Response status: {response.status_code}")
    print(f"[*] Response: {response.text[:500]}")
    
    if response.status_code in [200, 201]:
        result = response.json()
        if result.get("status") == "success":
            alert_id = result.get("data", {}).get("alert_id")
            print(f"[+] Alert created successfully! ID: {alert_id}")
            
            # Wait for enrichment
            print("[*] Waiting 15 seconds for OpenCTI enrichment...")
            time.sleep(15)
            
            # Check IOC enrichment
            print("[*] Checking IOC enrichment...")
            response = session.get(f"{BASE_URL}/api/v2/iocs", headers=headers, allow_redirects=True)
            if response.status_code == 200:
                data = response.json()
                iocs = data.get("data", {}).get("iocs", [])
                for ioc in iocs:
                    if ioc.get("ioc_value") == "9.9.9.9":
                        print(f"[+] Found IOC: {ioc.get('ioc_value')}")
                        print(f"    Enrichment: {ioc.get('ioc_enrichment')}")
                        break
            else:
                print(f"[*] Could not fetch IOCs: {response.status_code}")
        else:
            print(f"[!] Error: {result.get('message')}")
    else:
        print(f"[!] Failed to create alert. Status: {response.status_code}")

if __name__ == "__main__":
    main()
