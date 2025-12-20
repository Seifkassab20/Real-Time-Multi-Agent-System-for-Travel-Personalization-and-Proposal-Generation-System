import sys
import os
import json
from dotenv import load_dotenv
load_dotenv()
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
if project_root not in sys.path:
    sys.path.append(project_root)

sys.path.append(os.path.join(current_dir, "../../../"))

from backend.core.llm import OllamaCloudLLM
from backend.core.profile_agent.prompt import profile_agent_prompt
from backend.core.profile_agent.models import profile_agent_response


messages = [
    {"role": "system", "content": profile_agent_prompt}
]


class ProfileAgent:
    def __init__(self):
        self.llm = OllamaCloudLLM()
        self.system_prompt = profile_agent_prompt


    async def invoke(self, user_schema: dict) -> dict:

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": f"Start generating the questions from this schema:\n'{user_schema}'"}
        ]

        try:
            # Call the Ollama LLM
            response = self.llm.chatchat_structured(messages, profile_agent_response,temperature=0.0, max_tokens=500)

            # Debug the response structure
            print("DEBUG - Response:", response)
                
            try:
                return response.model_dump_json()
                
            except json.JSONDecodeError:
                print("DEBUG - Failed to parse response as JSON")
                return {}

            
        except Exception as e:
            print(f"Error in profile questions generation: {e}")
            return {}



