#!/usr/bin/env python3
"""
Test OpenCTI enrichment on existing alert
"""

import requests
import re
import json
import time

BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "uWn9Q3lK>DJhia.v"
ALERT_ID = 2

def main():
    requests.packages.urllib3.disable_warnings()
    session = requests.Session()
    session.verify = False
    
    print("[*] Step 1: Logging in...")
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
    
    login_data = {
        "csrf_token": csrf_token,
        "username": USERNAME,
        "password": PASSWORD
    }
    
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    if "dashboard" in response.url.lower():
        print("[+] Login successful!")
    else:
        print("[!] Login failed")
        return
    
    print(f"[*] Step 2: Applying OpenCTI recommendation to alert {ALERT_ID}...")
    
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf_token,
        "Referer": f"{BASE_URL}/alerts/{ALERT_ID}"
    }
    
    response = session.post(
        f"{BASE_URL}/alerts/{ALERT_ID}/opencti/recommendation/apply",
        json={},
        headers=headers,
        allow_redirects=True
    )
    
    print(f"[*] Response status: {response.status_code}")
    print(f"[*] Response: {response.text[:500]}")
    
    if response.status_code in [200, 201]:
        result = response.json()
        if result.get("status") == "success":
            print("[+] OpenCTI recommendation applied!")
            
            # Wait and check tags
            print("[*] Waiting for enrichment...")
            time.sleep(3)
            
            # Get alert details
            response = session.get(f"{BASE_URL}/alerts/filter", params={"alert_ids": ALERT_ID}, allow_redirects=True)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    alerts = data.get("data", {}).get("alerts", [])
                    if alerts:
                        alert = alerts[0]
                        tags = alert.get("alert_tags", [])
                        print(f"[*] Alert tags: {tags}")
                        
                        opencti_tags = [t for t in tags if "opencti" in str(t).lower()]
                        if opencti_tags:
                            print(f"[+] OpenCTI enrichment found!")
                            for tag in opencti_tags:
                                print(f"    - {tag}")
                        else:
                            print(f"[*] No OpenCTI tags yet")
        else:
            print(f"[!] Error: {result.get('message')}")
    else:
        print(f"[!] Failed to apply recommendation")

if __name__ == "__main__":
    main()
