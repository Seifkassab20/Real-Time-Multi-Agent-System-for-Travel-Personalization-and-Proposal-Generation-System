import re
import json
import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import os
load_dotenv()

ENCRYPTION_KEY=os.getenv("CIPHERKEY")
class SecurityManager:
    def __init__(self):
        self.cipher = Fernet(ENCRYPTION_KEY.encode())
        self.pii_patterns = {
            "PHONE": r'\b01[0125][0-9]{8}\b',
            "NAT_ID": r'\b(2|3)[0-9]{13}\b'
        }

    def detect_and_redact(self, text: str) -> tuple[str, bool]:
        """Returns (redacted_text, has_pii)"""
        redacted_text = text
        has_pii = False
        
        for label, pattern in self.pii_patterns.items():
            if re.search(pattern, redacted_text):
                has_pii = True
                redacted_text = re.sub(pattern, f"[{label}_REDACTED]", redacted_text)
        return redacted_text, has_pii

    def secure_store(self, record_id: str, data: dict):
        """Encrypts full payload (including PII) and saves to disk."""
        json_bytes = json.dumps(data).encode('utf-8')
        encrypted_data = self.cipher.encrypt(json_bytes)
        
        os.makedirs("data/encrypted_store", exist_ok=True)
        with open(f"data/encrypted_store/{record_id}.enc", "wb") as f:
            f.write(encrypted_data)

    def secure_retrieve(self, record_id: str) -> dict:
        """Decrypts data for authorized review."""
        path = f"data/encrypted_store/{record_id}.enc"
        if not os.path.exists(path):
            return None
            
        with open(path, "rb") as f:
            encrypted_data = f.read()
            
        decrypted_bytes = self.cipher.decrypt(encrypted_data)
        return json.loads(decrypted_bytes.decode('utf-8'))