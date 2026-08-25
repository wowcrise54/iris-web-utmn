#!/usr/bin/env python3
"""
Script to create a test alert in DFIR-IRIS via direct SQL insertion.
This bypasses API CSRF protection issues.
"""

import subprocess
import sys

# Configuration
DB_USER = "irisuser"
DB_NAME = "irisdb"

def create_test_alert(title="Test Alert", description="Test alert created via script", source="Script"):
    """Create a test alert directly in the database."""
    
    # SQL query to insert a new alert
    sql = f"""
    INSERT INTO alerts (
        alert_title, 
        alert_description, 
        alert_source, 
        alert_severity_id, 
        alert_status_id, 
        alert_customer_id, 
        alert_owner_id
    ) VALUES (
        '{title}', 
        '{description}', 
        '{source}', 
        1,  -- Medium severity
        2,  -- New status
        1,  -- Default client
        1   -- administrator user
    ) RETURNING alert_id, alert_title;
    """
    
    # Execute via docker
    cmd = [
        "docker", "exec", "iriswebapp_db", "psql", 
        "-U", DB_USER, 
        "-d", DB_NAME, 
        "-c", sql
    ]
    
    print(f"[*] Creating alert: {title}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode == 0:
        print("[+] Alert created successfully!")
        print(result.stdout)
        # Extract alert ID
        import re
        match = re.search(r'(\d+)\s+\|', result.stdout)
        if match:
            alert_id = match.group(1)
            print(f"[+] Alert ID: {alert_id}")
            return alert_id
    else:
        print(f"[!] Error: {result.stderr}")
        return None

if __name__ == "__main__":
    # Create a test alert with default or custom parameters
    title = sys.argv[1] if len(sys.argv) > 1 else "Test Alert - via Python Script"
    desc = sys.argv[2] if len(sys.argv) > 2 else "Automated test alert"
    
    create_test_alert(title, desc, "Python Script")
