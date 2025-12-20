from ollama import chat, Client
import os
import json
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()


class OllamaLLM:
    def __init__(self, model_name: str = "ministral-3:3b"):
        self.model_name = model_name
        

    def chat(self, messages: list[dict], temperature: float = 0.0, max_tokens: int = 500):

        response = chat(
            model=self.model_name,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens
            }
        )
        return response



class OllamaCloudLLM:
    def __init__(self, model_name: str = "gpt-oss:20b-cloud"):
        self.model_name = model_name
        
        # Load configuration from environment variables
        api_key = os.getenv('OLLAMA_API_KEY')
        base_url = os.getenv('OLLAMA_BASE_URL', 'https://ollama.com')
        
        if not api_key:
            raise ValueError(
                "OLLAMA_API_KEY not found in environment variables. "
                "Please set it in your .env file or as a system environment variable."
            )
        
        self.client = Client(
            host=base_url, 
            headers={"Authorization": f"Bearer {api_key}"}
        )
    
    def chat(self, messages: list[dict], temperature: float = 0.0, max_tokens: int = 500):
        """Standard chat method returning string."""
        response = self.client.chat(
            model=self.model_name,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens
            },
            format='json'
        )
        return response['message']['content']

    def chat_structured(self, messages: list[dict], schema: type[BaseModel], temperature: float = 0.0, max_tokens: int = 1000):
        """
        Chat method that forces output to match a Pydantic schema 
        and returns the validated Pydantic object.
        """
        # 1. Convert Pydantic model to JSON Schema
        json_schema = schema.model_json_schema()

        # 2. Call Ollama with the 'format' parameter set to the schema
        response = self.client.chat(
            model=self.model_name,
            messages=messages,
            format=json_schema, # <--- This enforces the structure
            options={
                "temperature": temperature,
                "num_predict": max_tokens
            }
        )
        
        content = response['message']['content']

        # 3. Parse JSON and validate with Pydantic
        try:
            # Clean up potential markdown formatting (sometimes models wrap in ```json ... ```)
            if content.strip().startswith("```json"):
                content = content.strip().split("```json")[1].split("```")[0]
            elif content.strip().startswith("```"):
                content = content.strip().split("```")[1].split("```")[0]

            data_dict = json.loads(content)
            return schema.model_validate(data_dict)
            
        except (json.JSONDecodeError, ValidationError) as e:
            print(f"Failed to parse structured output: {content}")
            raise e





llm_model = OllamaLLM()
llm_cloud_model = OllamaCloudLLM()
