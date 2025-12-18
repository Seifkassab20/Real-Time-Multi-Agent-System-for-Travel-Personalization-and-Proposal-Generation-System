from ollama import chat

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


llm_model = OllamaLLM()



