#!/usr/bin/env python3
import os
import sys
import requests

def init_vault():
    vault_addr = os.getenv("VAULT_ADDR", "http://localhost:8200")
    vault_token = os.getenv("VAULT_TOKEN", "dev-only-token")
    headers = {"X-Vault-Token": vault_token}
    
    print(f"🔑 Initializing Vault secrets at {vault_addr}...")
    
    # Check status/sys mounts to ensure kv-v2 is enabled
    mounts_url = f"{vault_addr.rstrip('/')}/v1/sys/mounts"
    try:
        resp = requests.get(mounts_url, headers=headers, timeout=5.0)
        resp.raise_for_status()
        mounts = resp.json()
    except Exception as e:
        print(f"❌ Failed to reach Vault: {e}")
        sys.exit(1)
        
    # Enable KV-v2 secrets engine if not present
    if "secret/" not in mounts:
        print("📦 Enabling KV-v2 engine at 'secret/'...")
        enable_url = f"{vault_addr.rstrip('/')}/v1/sys/mounts/secret"
        payload = {"type": "kv", "options": {"version": "2"}}
        try:
            r = requests.post(enable_url, headers=headers, json=payload, timeout=5.0)
            r.raise_for_status()
            print("✅ Secrets engine 'secret/' mounted successfully.")
        except Exception as e:
            print(f"❌ Failed to mount secrets engine: {e}")
            sys.exit(1)
    else:
        print("✅ Secrets engine 'secret/' is already mounted.")

    # Write secrets
    secrets_url = f"{vault_addr.rstrip('/')}/v1/secret/data/logiresilience"
    payload = {
        "data": {
            "NEO4J_PASSWORD": "mca_secure_password_2026",
            "POSTGRES_PASSWORD": "mca_postgres_password_2026",
            "MINIO_SECRET_KEY": "minio_admin_secret_2026",
            "WEATHER_API_KEY": "demo_weather_key",
            "NEWS_API_KEY": "demo_news_key"
        }
    }
    
    try:
        r = requests.post(secrets_url, headers=headers, json=payload, timeout=5.0)
        r.raise_for_status()
        print("✅ Default secrets successfully seeded to secret/data/logiresilience!")
        print("\nSeeded Keys:")
        for k in payload["data"].keys():
            print(f" - {k}")
    except Exception as e:
        print(f"❌ Failed to seed secrets: {e}")
        sys.exit(1)

if __name__ == "__main__":
    init_vault()
