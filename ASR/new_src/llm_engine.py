from ollama import Client
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import logging
import os

load_dotenv()

logger = logging.getLogger("llm")

# 1. Enhanced Output Model
class PostCorrectionOutput(BaseModel):
    corrected_text: str = Field(..., description="The corrected ASR output text")
    original_text: str = Field(..., description="The original input text")
    requires_confirmation: bool = Field(..., description="True if confidence was low or ambiguity exists")
    changes_made: bool = Field(..., description="True if the text was modified")

class LLMEngine:
    def __init__(self):
        self.host = "http://localhost:11434"
        print(self.host)
        self.api_key = str(os.getenv("OLLAMA_API_KEY"))
        print(self.api_key)
        self.correction_model = str(os.getenv("CORRECTION_MODEL"))
        print(self.correction_model)
        
        self.client = Client(host=self.host, headers={'Authorization': f'Bearer {self.api_key}'})
        self.parser = JsonOutputParser(pydantic_object=PostCorrectionOutput)
        self.prompt = self._build_prompt()

    def _build_prompt(self):
        return PromptTemplate(
        template="""
        You are an ASR post-correction model specialized in **Egyptian Arabic (Masri)**.

        Input Metadata:
        - ASR Confidence Score: {confidence_score} (Scale 0.0 to 10.0)
        - Policy: {policy_instruction}

        Task:
        - Correct the text while preserving the meaning **and the Egyptian dialect**.
        - Fix grammar, punctuation, spacing, and word boundaries.
        - Keep all Egyptian colloquial expressions (e.g., "عايز", "كده", "ماشي").
        - Do **NOT** convert anything to Modern Standard Arabic (MSA).
        - Convert any Arabic numerals (e.g., "٢٥") into English digits ("25").
        - Maintain a consistent conversational flow between the **agent** and the **customer**.
        - If the conversation contains English words, keep them unchanged (e.g., "airport pickup", "dinner cruise").
        - Do not rewrite, summarize, or add new information; only correct what is there.
        -Convert all arabic numerals to english numerals.
        - If sentence flow is broken, fix it while preserving meaning.
        - IF no full stop is present, add one at the end of each sentence.
        - IF no question mark is present, add one at the end of each question.
        - IF no exclamation mark is present, add one at the end of each exclamation.

        ASR text:
        \"\"\"{asr_text}\"\"\"

        Return ONLY a JSON object:
        {format_instructions}
        """,
                input_variables=["asr_text", "confidence_score", "policy_instruction"],
                partial_variables={"format_instructions": self.parser.get_format_instructions()}
            )


    def _call_ollama(self, prompt_text: str) -> str:
        messages = [{"role": "user", "content": prompt_text}]
        try:
            response = self.client.chat(model=self.correction_model, messages=messages, stream=False)
            return response['message']['content']
        except Exception as e:
            logger.error(f"Ollama API Error: {e}")
            return "{}"

    def correct_text(self, raw_text: str, confidence: float) -> dict:
        if not raw_text.strip():
            return {"corrected_text": "", "original_text": "", "requires_confirmation": False}

        # 2. Determine Policy Instruction based on Confidence
        if confidence > 0.9:
            policy = "AUTO: High confidence. Make minimal changes."
        elif confidence > 0.7:
            policy = "SUGGEST: Medium confidence. Standard correction."
        else:
            policy = "REVIEW: Low confidence. Flag for human confirmation."


        formatted_prompt = self.prompt.format(
            asr_text=raw_text,
            confidence_score=f"{confidence:.2f}",
            policy_instruction=policy
        )
        
        llm_response = self._call_ollama(formatted_prompt)
        
        try:
            parsed = self.parser.parse(llm_response)
            parsed['original_text'] = raw_text 
            if confidence > 0.8:
                parsed['requires_confirmation'] = True
            return parsed
        except Exception as e:
            logger.warning(f"Parsing failed: {e}")
            return {
                "corrected_text": raw_text,
                "original_text": raw_text,
                "requires_confirmation": True, 
                "changes_made": False
            }
        

engine=LLMEngine()
result = engine.correct_text("Hello, world!", 0.9)
print(result)
