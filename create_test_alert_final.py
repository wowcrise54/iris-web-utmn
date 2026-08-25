#!/usr/bin/env python3
"""
Script to create a test alert in DFIR-IRIS via API - Final attempt with form data
"""

import requests
import re
from urllib.parse import urlencode

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
    
    print("[*] Step 3: Creating test alert...")
    
    # Prepare form data for alert creation
    # Using form-encoded data instead of JSON
    alert_data = {
        "csrf_token": csrf_token,
        "alert_title": "Test Alert - Created via API Script",
        "alert_description": "This is a test alert created programmatically via DFIR-IRIS API.",
        "alert_status": "1",
        "alert_tlp": "1",
        "alert_pap": "1",
        "alert_source": "API Test Script",
        "alert_iocs": '[{"ioc_value":"192.168.1.100","ioc_type":"ip-addr","ioc_description":"Test IP","ioc_tlp":1}]',
        "alert_assets": '[{"asset_name":"test-server.example.com","asset_type":"fqdn","asset_description":"Test asset","asset_ip":["192.168.1.100"]}]'
    }
    
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{BASE_URL}/alerts",
        "User-Agent": "Mozilla/5.0"
    }
    
    print(f"[*] Sending POST to {BASE_URL}/alerts/add")
    
    response = session.post(
        f"{BASE_URL}/alerts/add",
        data=alert_data,
        headers=headers,
        allow_redirects=True
    )
    
    print(f"[*] Response status: {response.status_code}")
    print(f"[*] Response URL: {response.url}")
    
    if response.status_code in [200, 302, 303]:
        if "error" not in response.text.lower() or "alert" in response.text.lower():
            print("[+] Alert may have been created!")
            # Try to find alert ID in response
            alert_id_match = re.search(r'alert_id["\s:=]+(\d+)', response.text)
            if alert_id_match:
                print(f"[+] Alert ID: {alert_id_match.group(1)}")
            print(f"[*] Response preview: {response.text[:500]}")
        else:
            print(f"[!] Response: {response.text[:500]}")
    else:
        print(f"[!] Failed. Status: {response.status_code}")
        print(f"[*] Response: {response.text[:500]}")

if __name__ == "__main__":
    main()
