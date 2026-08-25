#!/usr/bin/env python3
"""
Test OpenCTI enrichment on alert #3
"""

import requests
import re
import json
import time

BASE_URL = "https://localhost"
USERNAME = "administrator"
PASSWORD = "TestPass123"
ALERT_ID = 3

def main():
    requests.packages.urllib3.disable_warnings()
    session = requests.Session()
    session.verify = False
    
    print("[*] Step 1: Logging in...")
    response = session.get(f"{BASE_URL}/login", allow_redirects=True)
    
    # Try multiple CSRF patterns
    csrf_patterns = [
        r'name="csrf_token" value="([^"]+)"',
        r'id="csrf_token"[^>]*value="([^"]+)"',
        r'csrf_token.*?value="([^"]+)"',
        r'"csrf_token"\s*:\s*"([^"]+)"'
    ]
    
    csrf_token = None
    for pattern in csrf_patterns:
        csrf_match = re.search(pattern, response.text)
        if csrf_match:
            csrf_token = csrf_match.group(1)
            break
    
    if not csrf_token:
        print("[!] Could not find CSRF token on login page")
        # Try to get it from a different page
        response = session.get(f"{BASE_URL}/alerts", allow_redirects=True)
        for pattern in csrf_patterns:
            csrf_match = re.search(pattern, response.text)
            if csrf_match:
                csrf_token = csrf_match.group(1)
                break
    
    if not csrf_token:
        print("[!] Still could not find CSRF token")
        return
    
    print(f"[+] Found CSRF token: {csrf_token[:20]}...")
    
    login_data = {
        "csrf_token": csrf_token,
        "username": USERNAME,
        "password": PASSWORD
    }
    
    response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=True)
    if "dashboard" in response.url.lower() or "alerts" in response.url.lower():
        print("[+] Login successful!")
    else:
        print(f"[!] Login failed. URL: {response.url}")
        return
    
    print(f"[*] Step 2: Applying OpenCTI recommendation to alert {ALERT_ID}...")
    
    headers = {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrf_token,
        "Referer": f"{BASE_URL}/alerts"
    }
    
    # Try the hook endpoint
    response = session.post(
        f"{BASE_URL}/dim/hooks/call",
        json={
            "hook_name": "on_manual_trigger_alert",
            "module_name": "iris_opencti_module",
            "type": "alert",
            "targets": [ALERT_ID]
        },
        headers=headers,
        allow_redirects=True
    )
    
    print(f"[*] Response status: {response.status_code}")
    print(f"[*] Response: {response.text[:500]}")
    
    if response.status_code in [200, 201]:
        result = response.json()
        if result.get("status") == "success":
            print("[+] OpenCTI enrichment triggered successfully!")
            print(f"    Task queued: {result.get('data', {}).get('task_id', 'N/A')}")
            
            # Wait for enrichment to complete
            print("[*] Waiting 10 seconds for enrichment to complete...")
            time.sleep(10)
            
            # Check the IOC enrichment status
            print("[*] Checking IOC enrichment status...")
            response = session.get(f"{BASE_URL}/api/v2/iocs/{2}", headers=headers, allow_redirects=True)
            if response.status_code == 200:
                ioc_data = response.json()
                print(f"[*] IOC data: {json.dumps(ioc_data.get('data', {}), indent=2)}")
            else:
                print(f"[*] Could not fetch IOC data: {response.status_code}")
            
            # Check alert tags
            print("[*] Checking alert tags...")
            response = session.get(f"{BASE_URL}/alerts/filter", params={"alert_ids": ALERT_ID}, headers=headers, allow_redirects=True)
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
                            print(f"[*] No OpenCTI tags found yet")
        else:
            print(f"[!] Error: {result.get('message')}")
    else:
        print(f"[!] Failed to apply recommendation. Status: {response.status_code}")

if __name__ == "__main__":
    main()
