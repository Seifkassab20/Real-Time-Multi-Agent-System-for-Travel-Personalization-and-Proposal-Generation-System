import re

class PIIGuard:
    def redact(self, text: str) -> str:
        phone_pattern = r'\b01[0125][0-9]{8}\b'
        return re.sub(phone_pattern, "[PHONE_REDACTED]", text)

    def evaluate_confidence(self, entropy_score: float) -> str:
            """
            Implements the three-tier policy based on Entropy.
            Lower Entropy = Higher Certainty.
            """
            if entropy_score < 0.6:  
                return "auto"
                
            elif entropy_score < 1.5: 
                return "suggest"
            
            else:
                return "review"