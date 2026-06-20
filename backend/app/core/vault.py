import os
import logging
import requests
from typing import Dict, Any

logger = logging.getLogger("logi-resilience")

def fetch_vault_secrets() -> Dict[str, Any]:
    """
    Synchronously fetches application secrets from HashiCorp Vault.
    Returns a dictionary of secrets if successful, or an empty dictionary on fallback.
    """
    vault_addr = os.getenv("VAULT_ADDR", "http://vault:8200")
    vault_token = os.getenv("VAULT_TOKEN", "dev-only-token")
    secret_path = "/v1/secret/data/logiresilience"
    
    url = f"{vault_addr.rstrip('/')}{secret_path}"
    headers = {"X-Vault-Token": vault_token}
    
    logger.info("Connecting to HashiCorp Vault at: %s", url)
    try:
        # Use a short timeout to prevent blocking application boot if Vault is unavailable
        response = requests.get(url, headers=headers, timeout=2.0)
        if response.status_code == 200:
            payload = response.json()
            # Extract nested data from KV-v2 response schema
            secrets = payload.get("data", {}).get("data", {})
            logger.info("Successfully fetched %d secrets from HashiCorp Vault.", len(secrets))
            return secrets
        elif response.status_code == 404:
            logger.warning("Vault path '%s' not found. It might not be seeded yet.", secret_path)
        else:
            logger.warning("Vault returned status code %d: %s", response.status_code, response.text)
    except Exception as exc:
        logger.warning("Could not connect to HashiCorp Vault: %s. Using environment fallbacks.", exc)
        
    return {}
