import json
import os
from typing import Optional, Dict, List
from datetime import datetime

class KeyManager:
    def __init__(self, key_file_path: str = "keys.json"):
        self.key_file_path = key_file_path
        self._load_keys()

    def _load_keys(self):
        if not os.path.exists(self.key_file_path):
            raise FileNotFoundError(f"Key file not found at {self.key_file_path}")
        with open(self.key_file_path, 'r') as f:
            self.data = json.load(f)

    def _save_keys(self):
        with open(self.key_file_path, 'w') as f:
            json.dump(self.data, f, indent=4)

    def get_key(self, host: str, model: str) -> Optional[str]:
        """
        Retrieves an available API key for the specified host and model.
        If all are unavailable, recycles the oldest used key after a safety delay.
        """
        import time
        
        self._load_keys() # Reload to get latest state
        
        # 1. Try to find an available key
        for service in self.data.get("services", []):
            if service.get("host") == host and service.get("model") == model:
                # First pass: Check available
                for key_entry in service.get("keys", []):
                    if key_entry.get("is_available"):
                        key_entry["last_used"] = datetime.now().isoformat()
                        self._save_keys()
                        return key_entry.get("api_key")
                
                # 2. If no available key, find the oldest used key to recycle
                all_keys = service.get("keys", [])
                if not all_keys:
                    return None
                
                # Sort by last_used (empty string means never used, so effectively oldest)
                # We interpret empty string as "min date"
                def parse_date(d_str):
                    if not d_str:
                        return datetime.min
                    try:
                        return datetime.fromisoformat(d_str)
                    except ValueError:
                        return datetime.min

                # Find oldest
                oldest_key_entry = min(all_keys, key=lambda k: parse_date(k.get("last_used")))
                
                # Check time delta
                last_used_dt = parse_date(oldest_key_entry.get("last_used"))
                now = datetime.now()
                
                # If never used, no wait needed. If used, check delta.
                if last_used_dt != datetime.min:
                    elapsed = (now - last_used_dt).total_seconds()
                    # Safe buffer for RPM (e.g. 60s + 5s buffer)
                    wait_needed = 65 - elapsed
                    
                    if wait_needed > 0:
                        print(f"All keys for {host}/{model} are cooling down. Need {wait_needed:.1f}s. Skipping to next service.")
                        return None

                # Revive and return
                oldest_key_entry["is_available"] = True
                oldest_key_entry["last_used"] = datetime.now().isoformat()
                self._save_keys()
                print(f"Recycling key {oldest_key_entry.get('api_key')[:10]}...")
                return oldest_key_entry.get("api_key")

        return None

    def mark_key_limit_reached(self, host: str, model: str, api_key: str):
        """
        Marks a specific key as unavailable (limit reached) and rotates to the next.
        """
        self._load_keys()
        for service in self.data.get("services", []):
            if service.get("host") == host and service.get("model") == model:
                for key_entry in service.get("keys", []):
                    if key_entry.get("api_key") == api_key:
                        key_entry["is_available"] = False
                        print(f"Key {api_key[:10]}... marked as unavailable for {host}/{model}")
                        self._save_keys()
                        return

        print(f"Key {api_key[:10]}... not found for {host}/{model}")

    def reset_keys(self, host: str, model: str):
        """
        Resets all keys for a service to available.
        """
        self._load_keys()
        for service in self.data.get("services", []):
            if service.get("host") == host and service.get("model") == model:
                for key_entry in service.get("keys", []):
                    key_entry["is_available"] = True
        self._save_keys()

