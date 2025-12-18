import sys
import os
from dotenv import load_dotenv
load_dotenv()
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(current_dir))))
if project_root not in sys.path:
    sys.path.append(project_root)

sys.path.append(os.path.join(current_dir, "../../../"))

from backend.core.llm import OllamaCloudLLM
from backend.core.profile_agent.prompt import profile_agent_prompt
from backend.core.profile_agent.models import CustomerProfile, profile_agent_response


llm = OllamaCloudLLM()

messages = [
    {"role": "user", "content": "Hello, how are you?"}
]


response = llm.chat_structured(messages, profile_agent_response)
print(response)


