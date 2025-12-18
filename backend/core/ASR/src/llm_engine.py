from ollama import Client
from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import logging
import os
from langsmith import traceable
from backend.core.ASR.src.tracing_config import get_trace_metadata, is_tracing_enabled, trace_external_service_connection
import time

load_dotenv()

logger = logging.getLogger("llm")

# 1. Enhanced Output Model
class PostCorrectionOutput(BaseModel):
    corrected_text: str = Field(..., description="The corrected ASR output text")
    original_text: str = Field(..., description="The original input text")
    requires_confirmation: bool = Field(..., description="True if confidence was low or ambiguity exists")
    changes_made: bool = Field(..., description="True if the text was modified")

class LLMEngine:
    @traceable(run_type="tool", name="llm_engine_initialization")
    def __init__(self):
        
        
        initialization_start_time = time.time()
        
        # Collect configuration details for tracing
        self.host = "http://localhost:11434"
        print(self.host)
        self.api_key = str(os.getenv("OLLAMA_API_KEY"))
        print(self.api_key)
        self.correction_model = str(os.getenv("CORRECTION_MODEL"))
        print(self.correction_model)
        
        # Trace Ollama service connection and availability
        ollama_service_check = trace_external_service_connection(
            "ollama",
            self.host,
            expected_model=self.correction_model,
            api_key_configured=bool(self.api_key and self.api_key != "None"),
            initialization_context="llm_engine_init"
        )
        
        if is_tracing_enabled():
            logger.info(f"Ollama service check metadata: {ollama_service_check}")
        
        try:
            # Initialize Ollama client
            self.client = Client(host=self.host, headers={'Authorization': f'Bearer {self.api_key}'})
            client_initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize Ollama client: {e}")
            client_initialized = False
            raise
        
        try:
            # Initialize parser and prompt
            self.parser = JsonOutputParser(pydantic_object=PostCorrectionOutput)
            self.prompt = self._build_prompt()
            parser_initialized = True
        except Exception as e:
            logger.error(f"Failed to initialize parser/prompt: {e}")
            parser_initialized = False
            raise
        
        # Calculate initialization time
        initialization_time = time.time() - initialization_start_time
        
        # Add comprehensive initialization metadata for tracing
        initialization_metadata = get_trace_metadata(
            "llm_engine_init",
            ollama_host=self.host,
            correction_model=self.correction_model,
            api_key_configured=bool(self.api_key and self.api_key != "None"),
            client_initialized=client_initialized,
            parser_initialized=parser_initialized,
            prompt_template_loaded=True,
            ollama_service_available=ollama_service_check.get("service_available", False),
            ollama_connection_time_ms=ollama_service_check.get("response_time_ms", 0),
            initialization_time_seconds=round(initialization_time, 3),
            initialization_timestamp=time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
            engine_status="initialized_successfully"
        )
        
        if is_tracing_enabled():
            logger.info(f"LLMEngine initialization metadata: {initialization_metadata}")

    @traceable(run_type="tool", name="llm_error_handling")
    def _handle_llm_error(self, error: Exception, context: dict, fallback_text: str = "") -> dict:
        """Comprehensive error handling with tracing for LLM operations"""
        error_metadata = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "error_context": context,
            "fallback_strategy": "return_original_text_with_confirmation",
            "error_timestamp": __import__('time').time(),
            "recovery_attempted": True
        }
        
        # Determine specific error handling based on error type
        if "connection" in str(error).lower() or "timeout" in str(error).lower():
            error_metadata.update({
                "error_category": "api_connection",
                "suggested_action": "check_ollama_service_status",
                "retry_recommended": True
            })
        elif "json" in str(error).lower() or "parse" in str(error).lower():
            error_metadata.update({
                "error_category": "response_parsing",
                "suggested_action": "review_llm_response_format",
                "retry_recommended": False
            })
        elif "model" in str(error).lower():
            error_metadata.update({
                "error_category": "model_error",
                "suggested_action": "verify_model_availability",
                "retry_recommended": True
            })
        else:
            error_metadata.update({
                "error_category": "unknown",
                "suggested_action": "review_error_logs",
                "retry_recommended": False
            })
        
        logger.error(f"LLM Error [{error_metadata['error_category']}]: {error}")
        
        # Return fallback response
        return {
            "corrected_text": fallback_text or context.get("original_text", ""),
            "original_text": context.get("original_text", ""),
            "requires_confirmation": True,
            "changes_made": False,
            "error_occurred": True,
            "error_details": error_metadata
        }

    @traceable(run_type='prompt', name="prompt_building")
    def _build_prompt(self):
        """Build prompt template with comprehensive tracing metadata"""
        template_text = """
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
        """
        
        input_vars = ["asr_text", "confidence_score", "policy_instruction"]
        format_instructions = self.parser.get_format_instructions()
        
        # Add comprehensive metadata for tracing
        metadata = {
            "template_type": "Egyptian_Arabic_ASR_Correction",
            "template_length": len(template_text),
            "input_variables": input_vars,
            "input_variable_count": len(input_vars),
            "format_instructions_length": len(format_instructions),
            "specialization": "Egyptian Arabic (Masri)",
            "correction_rules": [
                "preserve_egyptian_dialect",
                "fix_grammar_punctuation",
                "convert_arabic_numerals",
                "maintain_conversational_flow",
                "preserve_english_words",
                "add_punctuation_marks"
            ],
            "output_format": "JSON",
            "pydantic_model": "PostCorrectionOutput"
        }
        
        return PromptTemplate(
            template=template_text,
            input_variables=input_vars,
            partial_variables={"format_instructions": format_instructions}
        )


    @traceable(run_type="llm", name="ollama_api_call")
    def _call_ollama(self, prompt_text: str) -> str:
        # Add comprehensive API call metadata
        start_time = __import__('time').time()
        metadata = {
            "model_name": self.correction_model,
            "host": self.host,
            "prompt_length": len(prompt_text),
            "request_start_time": start_time,
            "stream_enabled": False
        }
        
        messages = [{"role": "user", "content": prompt_text}]
        
        try:
            response = self.client.chat(model=self.correction_model, messages=messages, stream=False)
            response_time = (__import__('time').time() - start_time) * 1000
            
            response_content = response['message']['content']
            metadata.update({
                "response_time_ms": response_time,
                "response_length": len(response_content),
                "api_call_successful": True,
                "response_status": "success"
            })
            
            return response_content
        except Exception as e:
            response_time = (__import__('time').time() - start_time) * 1000
            error_context = {
                "operation": "ollama_api_call",
                "model_name": self.correction_model,
                "host": self.host,
                "prompt_length": len(prompt_text),
                "response_time_ms": response_time
            }
            
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "response_time_ms": response_time,
                "api_call_successful": False,
                "response_status": "error",
                "fallback_response": "{}",
                "error_context": error_context
            }
            metadata.update(error_details)
            
            # Use comprehensive error handling
            self._handle_llm_error(e, error_context, "{}")
            
            logger.error(f"Ollama API Error: {e}")
            return "{}"

    @traceable(run_type="tool", name="llm_response_parsing")
    def _parse_llm_response(self, llm_response: str, raw_text: str) -> dict:
        """Parse LLM response with comprehensive tracing"""
        metadata = {
            "raw_response": llm_response,
            "raw_response_length": len(llm_response),
            "original_text": raw_text,
            "parsing_start_time": __import__('time').time()
        }
        
        try:
            parsed = self.parser.parse(llm_response)
            parsing_time = (__import__('time').time() - metadata["parsing_start_time"]) * 1000
            
            # Extract fields for tracing
            extracted_fields = {
                "corrected_text": parsed.get("corrected_text", ""),
                "requires_confirmation": parsed.get("requires_confirmation", False),
                "changes_made": parsed.get("changes_made", False)
            }
            
            metadata.update({
                "parsing_successful": True,
                "parsing_time_ms": parsing_time,
                "extracted_fields": extracted_fields,
                "field_count": len([k for k, v in extracted_fields.items() if v is not None])
            })
            
            # Ensure original_text is set
            parsed['original_text'] = raw_text
            return parsed
            
        except Exception as e:
            parsing_time = (__import__('time').time() - metadata["parsing_start_time"]) * 1000
            
            error_context = {
                "operation": "llm_response_parsing",
                "raw_response": llm_response,
                "raw_response_length": len(llm_response),
                "original_text": raw_text,
                "parsing_time_ms": parsing_time
            }
            
            error_details = {
                "parsing_successful": False,
                "parsing_time_ms": parsing_time,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "fallback_behavior": "return_original_with_confirmation_flag",
                "error_context": error_context
            }
            metadata.update(error_details)
            
            # Use comprehensive error handling
            error_result = self._handle_llm_error(e, error_context, raw_text)
            
            logger.warning(f"Parsing failed: {e}")
            return error_result

    @traceable(run_type="llm", name="llm_correction")
    def correct_text(self, raw_text: str, confidence: float) -> dict:
        # Add comprehensive metadata for tracing
        metadata = {
            "input_text": raw_text,
            "confidence_score": confidence,
            "input_text_length": len(raw_text.strip()),
            "correction_model": self.correction_model,
            "processing_start_time": __import__('time').time()
        }
        
        if not raw_text.strip():
            metadata.update({
                "policy": "EMPTY_INPUT",
                "changes_made": False,
                "requires_confirmation": False,
                "processing_time_ms": 0
            })
            return {"corrected_text": "", "original_text": "", "requires_confirmation": False}

        # 2. Determine Policy Instruction based on Confidence
        if confidence > 0.9:
            policy = "AUTO: High confidence. Make minimal changes."
        elif confidence > 0.7:
            policy = "SUGGEST: Medium confidence. Standard correction."
        else:
            policy = "REVIEW: Low confidence. Flag for human confirmation."

        metadata["correction_policy"] = policy

        formatted_prompt = self.prompt.format(
            asr_text=raw_text,
            confidence_score=f"{confidence:.2f}",
            policy_instruction=policy
        )
        
        llm_response = self._call_ollama(formatted_prompt)
        
        # Use the new traceable parsing function
        parsed = self._parse_llm_response(llm_response, raw_text)
        
        # Apply confidence-based confirmation logic
        if confidence > 0.8:
            parsed['requires_confirmation'] = True
        
        # Add completion metadata
        processing_time = (__import__('time').time() - metadata["processing_start_time"]) * 1000
        metadata.update({
            "corrected_text": parsed.get("corrected_text", ""),
            "changes_made": parsed.get("changes_made", False),
            "requires_confirmation": parsed.get("requires_confirmation", False),
            "processing_time_ms": processing_time,
            "correction_successful": True
        })
        
        return parsed
        

