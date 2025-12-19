import json
import re
from backend.core.llm import llm_model
from backend.core.extraction_agent.models import TranscriptSegment , Agent_output
from datetime import date

today = date.today().isoformat()
class ExtractionAgent:

    def __init__(self):
        self.llm = llm_model
        self.system_prompt = f"""
        You are a travel information extraction agent. Extract travel details from customer text and return ONLY valid JSON.
        Today's date is {date.today().isoformat()}

        Extract these fields ONLY if explicitly mentioned:

        - budget: number
        - adults: number
        - children: number
        - children_age: list of numbers
        - rooms: number
        - city: "Cairo" or "Giza" only
        - check_in: string in YYYY-MM-DD format
        - check_out: string in YYYY-MM-DD format
        - activities: list of strings (ENGLISH ONLY)
        - preferences: list of strings (ENGLISH ONLY)
        - keywords: list of strings (ENGLISH ONLY)
        ========================
        LANGUAGE RULES (STRICT)
        ========================

        - activities MUST be written in ENGLISH only
        - preferences MUST be written in ENGLISH only
        - keywords MUST be written in ENGLISH only
        - If the user speaks Arabic or mixed language, TRANSLATE these fields to English
        - Do NOT output Arabic text in these fields

        ========================
        ACTIVITIES RULES (CRITICAL)
        ========================

        - Convert all activity mentions into full, natural English sentences
        - Each activity must be a complete sentence
        - Activities must be specific and related to Egyptian tourism only
        - Include location and intent when possible
        - Avoid vague phrases

        Example:
        Input: "عايز اشوف الاهرامات"
        Output activity:
        - "Visit and explore the Great Pyramids of Giza."

        ========================
        DATE & TIME REASONING (CRITICAL)
        ========================

        TODAY_DATE is provided below and MUST be used for all calculations.

        TODAY_DATE: {today}

        Rules:
        1. If no date or duration is mentioned, return empty date fields

        2. If the user mentions explicit dates:
        - Convert them to YYYY-MM-DD format
        - Use the correct year relative to TODAY_DATE

        3. If the user mentions RELATIVE dates:
        - "next week", "next month", "tomorrow", etc.
        - Calculate the exact date using TODAY_DATE

        4. If the user mentions STAY DURATION verbally:
        - Examples: "a week", "7 days", "15 days", "a month"
        - If a start date is mentioned:
            - check_out = check_in + duration
        - If no start date is mentioned:
            - check_in = TODAY_DATE (or calculated relative start)
            - check_out = check_in + duration

        5. Duration conversions:
        - "a week" = 7 days
        - "two weeks" = 14 days
        - "15 days" = 15 days
        - "a month" = 30 days



        ========================
        CITY RULES
        ========================

        - city MUST be exactly one of: "Cairo", "Giza"
        - Ignore any other locations

        ========================
        OUTPUT CONSTRAINTS
        ========================

        - Output MUST be valid JSON only
        - Use double quotes only
        - No markdown
        - No comments
        - No trailing commas
        - Omit fields that are not mentioned
        - If no travel-related information exists, return 

        ========================
        FINAL RULE
        ========================

        Precision is more important than completeness.
        Never hallucinate information.
                """
    
    async def invoke(self, segment: TranscriptSegment) -> dict:

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Extract travel information from this text: '{segment.text}'"}
        ]

        try:
            # Call the Ollama LLM
            response = self.llm.chat(messages, temperature=0.0, max_tokens=500)
            
            # Extract the content from the response
            content = response['message']['content'].strip()          
            try:
                result = json.loads(content)
                validated = Agent_output(**result)
                return validated.model_dump(exclude_none=True)
                
            except json.JSONDecodeError as e:
                print(f"DEBUG - JSON Parse Error: {e}")
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    json_str = json_match.group()
                    print(f"DEBUG - Extracted JSON: {json_str}") 
                    result = json.loads(json_str)
                    validated = Agent_output(**result)
                    return validated.model_dump(exclude_none=True)
                else:
                    print("DEBUG - No JSON found in response") 
                    return {}
            
        except Exception as e:
            print(f"Error in extraction: {e}")
            return {}


