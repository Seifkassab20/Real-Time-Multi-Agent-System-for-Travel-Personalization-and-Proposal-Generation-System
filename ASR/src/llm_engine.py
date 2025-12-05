# src/llm_engine.py
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
        self.host = str(os.getenv("OLLAMA_HOST"))
        self.api_key = str(os.getenv("OLLAMA_API_KEY"))
        self.model_name = str(os.getenv("CORRECTION_MODEL"))
        
        self.client = Client(host=self.host, headers={'Authorization': f'Bearer {self.api_key}'})
        self.parser = JsonOutputParser(pydantic_object=PostCorrectionOutput)
        self.prompt = self._build_prompt()

    def _build_prompt(self):
        # We add {confidence_context} to the template
        return PromptTemplate(
            template="""
            You are an ASR post-correction model specialized in **Egyptian Arabic (Masri)**.
            
            Input Metadata:
            - ASR Confidence Score: {confidence_score} (Scale 0.0 to 10.0)
            - Policy: {policy_instruction}

            Task:
            - Correct the text preserving meaning and dialect.
            - Fix grammar, punctuation, spacing, and word boundaries.
            - Keep Egyptian expressions (e.g., "عايز", "كده").
            - Do NOT convert to MSA.
            - Output should be  only and specefically in Arabic
            - Transcribe any arabic number into english numeral
            - Output should maintain consistancy of the conversational chat between the agent and customer
            
            
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
            response = self.client.chat(model=self.model_name, messages=messages, stream=False)
            return response['message']['content']
        except Exception as e:
            logger.error(f"Ollama API Error: {e}")
            return "{}"

    def correct_text(self, raw_text: str, confidence: float) -> dict:
        if not raw_text.strip():
            return {"corrected_text": "", "original_text": "", "requires_confirmation": False}

        # 2. Determine Policy Instruction based on Confidence
        if confidence < 1.0:
            policy = "AUTO: High confidence. Make minimal changes."
        elif confidence < 2.5:
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