import json
import time
import uuid
import re
from datetime import datetime
import asyncio
import redis.asyncio as redis
from pydantic import BaseModel
from backend.core.llm import llm_model
from backend.core.extraction_agent.models import TranscriptSegment, RawExtraction, TravelPlan
from backend.core.extraction_agent.Config import Config
from backend.core.tracing_config import setup_tracing, get_trace_metadata, is_tracing_enabled
from langsmith import traceable


# --- System prompt for extraction ---


class ExtractionAgent:
    def __init__(self):
        self.agent_id = f"extractor_{uuid.uuid4().hex[:6]}"
        self.client = llm_model
        self.redis = None
        self.config = Config()
        
        # Initialize tracing configuration
        self.tracing_enabled = setup_tracing()
        if self.tracing_enabled:
            print(f"[{self.agent_id}] LangSmith tracing enabled")
        else:
            print(f"[{self.agent_id}] LangSmith tracing disabled")
        
        self.SYSTEM_PROMPT = """
            You are an extraction agent for a travel booking system.

            Your job: Extract travel-related entities from customer speech and convert activities into clear, searchable sentences.

            ACTIVITIES PARSING (CRITICAL):
            - Convert all activity mentions into complete, natural English sentences
            - Make sentences specific and context-rich for semantic search
            - Include relevant details (location, preferences, constraints)
            - Use action verbs and descriptive language
            - Focus on Egyptian tourism activities and experiences

            Examples for Egyptian tourism:
            Input: "want to see the pyramids and maybe the sphinx"
            Output examples activities: [
            "Visit and explore the Great Pyramids of Giza",
            "See the ancient Sphinx monument and learn its history"
            ]

            Input: "interested in diving in the Red Sea, coral reefs"
            Output examples activities: [
            "Experience scuba diving in the Red Sea coral reefs",
            "Explore underwater marine life and colorful coral formations"
            ]

            Input: "want to visit temples, maybe Luxor and Karnak"
            Output examples activities: [
            "Tour the ancient temples of Luxor and Karnak",
            "Explore pharaonic monuments and hieroglyphic inscriptions"
            ]

            Input: "desert safari, camel riding, maybe camping"
            Output examples activities: [
            "Experience a desert safari adventure in the Egyptian Sahara",
            "Go camel riding through sand dunes and desert landscapes",
            "Enjoy overnight camping under the stars in the desert"
            ]

            Input: "cruise down the Nile, see the valley of the kings"
            Output examples activities: [
            "Take a scenic Nile River cruise through ancient Egypt",
            "Visit the Valley of the Kings royal burial tombs"
            ]

            Extract other entities:
            - Dates (any mention of dates or timeframes avoid jargon)
            - Numbers (budget, people count, ages)
            - Locations (countries, cities, sites)
            - Preferences (hotel types, food, pace)
            - Feelings/tone (excited, worried, hesitant)

            Output JSON format:
            {
            "dates": ["December 2024", "winter holiday", "10 days"],
            "budget": {"amount": 3000,"flexibility": "moderate"},
            "travelers": {"adults": 2, "children": 1,"num_of_rooms":2},
            "locations": ["Cairo", "Giza"],
            "activities": [
                "Visit and explore the Great Pyramids of Giza",
                "Take a scenic Nile River cruise ",
                "Tour the egyptian national musem,
                "Shop for traditional Egyptian souvenirs at Khan el-Khalili bazaar"
            ],
            "preferences": ["family-friendly hotels", "cultural experiences", "moderate pace", "guided tours"],
            "keywords": Examples["ancient history", "adventure", "photography"],
            "tone": "excited and curious about Egyptian culture"
            }

            RULES:
            - Activities MUST be full sentences 
            - Make activities semantically rich for RAG retrieval
            - Include context from surrounding conversation when possible
            - If nothing travel-related, return empty dict: {}
            - Response MUST be valid RFC 8259 JSON ONLY (no markdown)
            - DO NOT include comments of any kind (no //, no /* */)
            - DO NOT include trailing commas
            - Use standard double quotes for keys and strings

            Be FAST but PRECISE on activities.
            """        
        print(f"[{self.agent_id}] Extraction Agent ready")

    def _generate_agent_metadata(self, **kwargs) -> dict:
        """
        Generate standardized metadata for agent-level traces.
        
        Args:
            **kwargs: Additional metadata fields
            
        Returns:
            dict: Agent metadata dictionary
        """
        metadata = get_trace_metadata(
            component="extraction_agent",
            agent_id=self.agent_id,
            tracing_enabled=self.tracing_enabled,
            **kwargs
        )
        return metadata

    def _generate_input_metadata(self, segment: TranscriptSegment, **kwargs) -> dict:
        """
        Generate metadata for input processing traces.
        
        Args:
            segment: The transcript segment being processed
            **kwargs: Additional metadata fields
            
        Returns:
            dict: Input processing metadata dictionary
        """
        metadata = {
            "input_id": segment.segment_id,
            "speaker": segment.speaker,
            "text_length": len(segment.text),
            "timestamp": segment.timestamp.isoformat(),
            "processing_mode": "direct_transcript",
            **kwargs
        }
        return metadata

    def _generate_llm_metadata(self, text: str, **kwargs) -> dict:
        """
        Generate metadata for LLM extraction traces.
        
        Args:
            text: Input text for LLM processing
            **kwargs: Additional metadata fields
            
        Returns:
            dict: LLM extraction metadata dictionary
        """
        metadata = {
            "model_name": getattr(self.client, 'model_name', 'unknown'),
            "input_text_length": len(text),
            "prompt_template_version": "v1.0",
            **kwargs
        }
        return metadata

    def _generate_validation_metadata(self, entities: dict, **kwargs) -> dict:
        """
        Generate metadata for entity validation traces.
        
        Args:
            entities: Extracted entities dictionary
            **kwargs: Additional metadata fields
            
        Returns:
            dict: Entity validation metadata dictionary
        """
        metadata = {
            "entities_found": list(entities.keys()) if entities else [],
            "activities_count": len(entities.get('activities', [])) if entities else 0,
            "validation_successful": bool(entities),
            **kwargs
        }
        return metadata

    def _generate_result_metadata(self, extraction: RawExtraction, **kwargs) -> dict:
        """
        Generate metadata for result generation traces.
        
        Args:
            extraction: The extraction result
            **kwargs: Additional metadata fields
            
        Returns:
            dict: Result generation metadata dictionary
        """
        metadata = {
            "extraction_id": extraction.extraction_id,
            "processing_time_ms": extraction.processing_time_ms,
            "output_size_bytes": len(extraction.model_dump_json()),
            "generation_successful": bool(extraction.entities),
            **kwargs
        }
        return metadata

    @traceable(run_type="tool", name="input_processing")
    async def _process_input(self, segment: TranscriptSegment) -> dict:
        """
        Process and validate input transcript segment with comprehensive tracing.
        
        Args:
            segment: The transcript segment to process
            
        Returns:
            dict: Processing metadata and results
        """
        processing_start_time = time.time()
        
        # Generate input processing metadata
        input_metadata = self._generate_input_metadata(segment)
        
        # Initialize performance metrics
        performance_metrics = {
            "parsing_time_ms": 0,
            "validation_time_ms": 0,
            "preprocessing_time_ms": 0,
            "total_processing_time_ms": 0,
            "throughput_chars_per_second": 0,
            "throughput_words_per_second": 0,
            "processing_efficiency_score": 0
        }
        
        # Initialize error tracking
        error_tracking = {
            "errors_encountered": [],
            "recovery_attempts": 0,
            "fallback_used": False,
            "critical_failure": False
        }
        
        try:
            # Parse input data with performance tracking
            parse_start = time.time()
            parsed_data = await self._parse_input(segment)
            performance_metrics["parsing_time_ms"] = (time.time() - parse_start) * 1000
            
            # Handle parsing errors
            if not parsed_data.get("parsing_successful", True):
                error_tracking["errors_encountered"].append("parsing_failed")
                error_tracking["recovery_attempts"] += 1
                # Attempt recovery with minimal parsing
                parsed_data = await self._fallback_parsing(segment)
                error_tracking["fallback_used"] = True
            
            # Validate input format and content with performance tracking
            validation_start = time.time()
            validation_result = await self._validate_input(segment, parsed_data)
            performance_metrics["validation_time_ms"] = (time.time() - validation_start) * 1000
            
            # Handle validation errors
            if not validation_result.get("validation_successful", True):
                error_tracking["errors_encountered"].append("validation_failed")
                error_tracking["recovery_attempts"] += 1
                # Continue with warnings but don't fail completely
                print(f"[{self.agent_id}] Warning: Input validation failed for {segment.segment_id}")
            
            # Preprocess text for LLM consumption with performance tracking
            preprocess_start = time.time()
            preprocessed_data = await self._preprocess_text(segment.text, parsed_data)
            performance_metrics["preprocessing_time_ms"] = (time.time() - preprocess_start) * 1000
            
            # Handle preprocessing errors
            if not preprocessed_data.get("preprocessing_successful", True):
                error_tracking["errors_encountered"].append("preprocessing_failed")
                error_tracking["recovery_attempts"] += 1
                # Use original text as fallback
                error_tracking["fallback_used"] = True
            
            # Calculate comprehensive performance metrics
            total_processing_time = (time.time() - processing_start_time) * 1000
            performance_metrics["total_processing_time_ms"] = total_processing_time
            
            if total_processing_time > 0:
                text_length = len(segment.text)
                word_count = len(segment.text.split())
                
                performance_metrics.update({
                    "throughput_chars_per_second": (text_length / total_processing_time) * 1000,
                    "throughput_words_per_second": (word_count / total_processing_time) * 1000,
                    "processing_efficiency_score": min(100, (1000 / total_processing_time) * 10)  # Higher is better
                })
            
            # Compile comprehensive processing results
            processing_result = {
                **input_metadata,
                **performance_metrics,
                **error_tracking,
                "parsing_successful": parsed_data.get("parsing_successful", True),
                "validation_successful": validation_result.get("validation_successful", True),
                "preprocessing_successful": preprocessed_data.get("preprocessing_successful", True),
                "processing_successful": True,
                "overall_success_rate": (
                    sum([
                        parsed_data.get("parsing_successful", True),
                        validation_result.get("validation_successful", True),
                        preprocessed_data.get("preprocessing_successful", True)
                    ]) / 3
                )
            }
            
            return processing_result
            
        except Exception as e:
            # Comprehensive error handling and metrics
            total_processing_time = (time.time() - processing_start_time) * 1000
            performance_metrics["total_processing_time_ms"] = total_processing_time
            
            error_tracking.update({
                "critical_failure": True,
                "errors_encountered": error_tracking["errors_encountered"] + [type(e).__name__],
                "final_error_type": type(e).__name__,
                "final_error_message": str(e)
            })
            
            error_result = {
                **input_metadata,
                **performance_metrics,
                **error_tracking,
                "processing_successful": False,
                "overall_success_rate": 0.0
            }
            
            # Log error for monitoring
            print(f"[{self.agent_id}] Critical input processing error for {segment.segment_id}: {e}")
            
            return error_result

    @traceable(run_type="tool", name="fallback_parsing")
    async def _fallback_parsing(self, segment: TranscriptSegment) -> dict:
        """
        Fallback parsing method for error recovery.
        
        Args:
            segment: The transcript segment to parse with minimal processing
            
        Returns:
            dict: Minimal parsing results
        """
        try:
            # Minimal parsing with basic validation
            fallback_result = {
                "input_id": segment.segment_id or f"fallback_{uuid.uuid4().hex[:8]}",
                "parsing_successful": True,
                "fallback_parsing": True,
                "speaker": segment.speaker or "unknown",
                "text_length": len(segment.text) if segment.text else 0,
                "has_content": bool(segment.text and segment.text.strip()),
                "parsing_time_ms": 0  # Minimal processing time
            }
            
            return fallback_result
            
        except Exception as e:
            return {
                "parsing_successful": False,
                "fallback_parsing": True,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="input_parsing")
    async def _parse_input(self, segment: TranscriptSegment) -> dict:
        """
        Parse input transcript segment and extract metadata.
        
        Args:
            segment: The transcript segment to parse
            
        Returns:
            dict: Parsing results and metadata
        """
        parsing_start_time = time.time()
        
        try:
            # Generate unique input ID if not present
            input_id = segment.segment_id or f"input_{uuid.uuid4().hex[:8]}"
            
            # Extract speaker information
            speaker_info = {
                "speaker": segment.speaker,
                "is_customer": segment.speaker.lower() == "customer",
                "is_agent": segment.speaker.lower() == "agent"
            }
            
            # Analyze text characteristics
            text_analysis = {
                "text_length": len(segment.text),
                "word_count": len(segment.text.split()),
                "character_count": len(segment.text),
                "has_content": bool(segment.text.strip()),
                "is_empty": not bool(segment.text.strip()),
                "contains_travel_keywords": any(keyword in segment.text.lower() 
                                              for keyword in ["travel", "trip", "vacation", "hotel", "flight", "visit"])
            }
            
            # Calculate parsing metrics
            parsing_time_ms = (time.time() - parsing_start_time) * 1000
            
            parsing_result = {
                "input_id": input_id,
                "parsing_time_ms": parsing_time_ms,
                "parsing_successful": True,
                **speaker_info,
                **text_analysis,
                "timestamp_parsed": segment.timestamp.isoformat(),
                "segment_id": segment.segment_id
            }
            
            return parsing_result
            
        except Exception as e:
            parsing_time_ms = (time.time() - parsing_start_time) * 1000
            return {
                "parsing_successful": False,
                "parsing_time_ms": parsing_time_ms,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="input_validation")
    async def _validate_input(self, segment: TranscriptSegment, parsed_data: dict) -> dict:
        """
        Validate input transcript segment format and content.
        
        Args:
            segment: The transcript segment to validate
            parsed_data: Results from input parsing
            
        Returns:
            dict: Validation results and metadata
        """
        validation_start_time = time.time()
        
        try:
            validation_results = {
                "segment_id_valid": bool(segment.segment_id and len(segment.segment_id) > 0),
                "timestamp_valid": isinstance(segment.timestamp, datetime),
                "speaker_valid": segment.speaker in ["customer", "agent"],
                "text_not_empty": bool(segment.text.strip()),
                "text_length_acceptable": 10 <= len(segment.text) <= 5000,  # Reasonable bounds
                "contains_meaningful_content": len(segment.text.split()) >= 3
            }
            
            # Overall validation status
            validation_successful = all(validation_results.values())
            
            # Calculate validation metrics
            validation_time_ms = (time.time() - validation_start_time) * 1000
            
            validation_result = {
                "validation_time_ms": validation_time_ms,
                "validation_successful": validation_successful,
                **validation_results,
                "validation_score": sum(validation_results.values()) / len(validation_results)
            }
            
            return validation_result
            
        except Exception as e:
            validation_time_ms = (time.time() - validation_start_time) * 1000
            return {
                "validation_successful": False,
                "validation_time_ms": validation_time_ms,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="text_preprocessing")
    async def _preprocess_text(self, text: str, parsed_data: dict) -> dict:
        """
        Preprocess text for LLM consumption with tracing.
        
        Args:
            text: Raw text to preprocess
            parsed_data: Results from input parsing
            
        Returns:
            dict: Preprocessing results and metadata
        """
        preprocessing_start_time = time.time()
        
        try:
            # Text cleaning operations
            original_length = len(text)
            
            # Remove excessive whitespace
            cleaned_text = re.sub(r'\s+', ' ', text.strip())
            
            # Remove special characters that might interfere with LLM processing
            normalized_text = re.sub(r'[^\w\s\.,!?;:\-\(\)]', '', cleaned_text)
            
            # Ensure text ends with punctuation for better LLM processing
            if normalized_text and normalized_text[-1] not in '.!?':
                normalized_text += '.'
            
            # Calculate preprocessing metrics
            preprocessing_time_ms = (time.time() - preprocessing_start_time) * 1000
            final_length = len(normalized_text)
            
            preprocessing_result = {
                "preprocessing_time_ms": preprocessing_time_ms,
                "preprocessing_successful": True,
                "original_length": original_length,
                "final_length": final_length,
                "length_reduction": original_length - final_length,
                "length_reduction_percent": ((original_length - final_length) / original_length * 100) if original_length > 0 else 0,
                "text_cleaned": cleaned_text != text,
                "text_normalized": normalized_text != cleaned_text,
                "punctuation_added": normalized_text.endswith('.') and not text.rstrip().endswith(('.', '!', '?')),
                "preprocessing_operations": ["whitespace_cleanup", "special_char_removal", "punctuation_normalization"]
            }
            
            return preprocessing_result
            
        except Exception as e:
            preprocessing_time_ms = (time.time() - preprocessing_start_time) * 1000
            return {
                "preprocessing_successful": False,
                "preprocessing_time_ms": preprocessing_time_ms,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="performance_monitoring")
    async def _monitor_performance_metrics(self, segment: TranscriptSegment, processing_results: dict) -> dict:
        """
        Monitor and trace comprehensive performance metrics for input processing.
        
        Args:
            segment: The transcript segment being processed
            processing_results: Results from input processing
            
        Returns:
            dict: Performance monitoring metadata
        """
        try:
            # System resource monitoring (with fallback if psutil not available)
            try:
                import psutil
                import os
                process = psutil.Process(os.getpid())
                psutil_available = True
            except ImportError:
                psutil_available = False
                process = None
            
            # Memory usage metrics (with fallback)
            if psutil_available and process:
                memory_info = process.memory_info()
                memory_metrics = {
                    "memory_rss_mb": round(memory_info.rss / (1024 * 1024), 2),
                    "memory_vms_mb": round(memory_info.vms / (1024 * 1024), 2),
                    "memory_percent": round(process.memory_percent(), 2)
                }
                
                # CPU usage metrics
                cpu_metrics = {
                    "cpu_percent": round(process.cpu_percent(), 2),
                    "cpu_times_user": process.cpu_times().user,
                    "cpu_times_system": process.cpu_times().system
                }
            else:
                # Fallback metrics when psutil is not available
                memory_metrics = {
                    "memory_rss_mb": 0,
                    "memory_vms_mb": 0,
                    "memory_percent": 0,
                    "psutil_available": False
                }
                
                cpu_metrics = {
                    "cpu_percent": 0,
                    "cpu_times_user": 0,
                    "cpu_times_system": 0,
                    "psutil_available": False
                }
            
            # Processing rate calculations
            total_processing_time = processing_results.get("total_processing_time_ms", 0)
            text_length = len(segment.text)
            
            rate_metrics = {
                "processing_rate_chars_per_second": (text_length / (total_processing_time / 1000)) if total_processing_time > 0 else 0,
                "processing_rate_segments_per_minute": (60000 / total_processing_time) if total_processing_time > 0 else 0,
                "error_rate": len(processing_results.get("errors_encountered", [])) / max(1, processing_results.get("recovery_attempts", 1)),
                "success_rate": processing_results.get("overall_success_rate", 0.0)
            }
            
            # Resource efficiency metrics
            memory_rss = memory_metrics.get("memory_rss_mb", 0) * 1024 * 1024  # Convert back to bytes
            efficiency_metrics = {
                "memory_efficiency": text_length / memory_rss if memory_rss > 0 else 0,
                "time_efficiency_score": min(100, 1000 / total_processing_time) if total_processing_time > 0 else 100,
                "resource_utilization_score": (cpu_metrics["cpu_percent"] + memory_metrics["memory_percent"]) / 2,
                "psutil_monitoring_enabled": psutil_available
            }
            
            performance_monitoring = {
                **memory_metrics,
                **cpu_metrics,
                **rate_metrics,
                **efficiency_metrics,
                "monitoring_timestamp": datetime.now().isoformat(),
                "monitoring_successful": True
            }
            
            return performance_monitoring
            
        except Exception as e:
            return {
                "monitoring_successful": False,
                "monitoring_error": str(e),
                "error_type": type(e).__name__
            }

    @traceable(run_type="agent", name="extraction_agent_main_workflow")
    async def extract_entities(self, segment: TranscriptSegment) -> RawExtraction:
        """
        Top-level agent extraction workflow with comprehensive hierarchical tracing.
        
        This is the main entry point for the extraction agent, creating a top-level
        agent trace that links all child spans (input processing, LLM extraction,
        entity validation, and result generation) into a complete hierarchical structure.
        
        Args:
            segment: The transcript segment to process
            
        Returns:
            RawExtraction: The extraction result with entities
            
        Traces:
            - Agent-level metadata with processing timestamps
            - Complete workflow hierarchy with all child spans
            - Performance metrics and resource usage
            - Error propagation and recovery attempts
        """
        workflow_start_time = time.time()
        
        # Generate comprehensive agent-level metadata for top-level trace
        agent_metadata = self._generate_agent_metadata(
            processing_start_time=datetime.now().isoformat(),
            workflow_type="complete_extraction",
            trace_level="agent_top_level",
            **self._generate_input_metadata(segment)
        )
        
        # Initialize error tracking for recovery tracing
        error_tracking = {
            "errors_encountered": [],
            "recovery_attempts": [],
            "fallback_strategies_used": [],
            "final_status": "pending"
        }
        
        try:
            # Process input with comprehensive tracing (child span)
            input_processing_result = await self._process_input(segment)
            
            # Track input processing errors for recovery
            if not input_processing_result.get("processing_successful", False):
                error_tracking["errors_encountered"].append({
                    "stage": "input_processing",
                    "error_details": input_processing_result.get("errors_encountered", []),
                    "recovery_attempted": input_processing_result.get("recovery_attempts", 0) > 0,
                    "fallback_used": input_processing_result.get("fallback_used", False)
                })
            
            # Monitor performance metrics (child span)
            performance_metrics = await self._monitor_performance_metrics(segment, input_processing_result)
            
            # Process the LLM extraction (child span)
            extraction = await self._extract(segment)
            
            # Track extraction errors for recovery
            if not extraction.entities:
                error_tracking["errors_encountered"].append({
                    "stage": "llm_extraction",
                    "error_details": "no_entities_extracted",
                    "recovery_attempted": False,
                    "fallback_used": False
                })
            
            # Calculate total workflow time
            total_workflow_time = (time.time() - workflow_start_time) * 1000
            
            # Mark final status as success
            error_tracking["final_status"] = "success"
            
            # Add comprehensive success metadata to agent-level trace
            agent_metadata.update(self._generate_result_metadata(extraction))
            agent_metadata.update({
                "extraction_successful": True,
                "input_processing_successful": input_processing_result.get("processing_successful", False),
                "total_workflow_time_ms": total_workflow_time,
                "input_processing_time_ms": input_processing_result.get("total_processing_time_ms", 0),
                "extraction_time_ms": extraction.processing_time_ms,
                "workflow_efficiency_score": min(100, 5000 / total_workflow_time) if total_workflow_time > 0 else 100,
                "workflow_completion_timestamp": datetime.now().isoformat(),
                "error_tracking": error_tracking,
                "child_spans_completed": ["input_processing", "performance_monitoring", "llm_extraction"],
                **performance_metrics
            })
            
            return extraction
            
        except Exception as e:
            # Calculate error workflow time
            total_workflow_time = (time.time() - workflow_start_time) * 1000
            
            # Track the critical error
            error_tracking["errors_encountered"].append({
                "stage": "workflow_critical_failure",
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_occurred_at": datetime.now().isoformat()
            })
            error_tracking["final_status"] = "critical_failure"
            
            # Attempt error recovery and trace the recovery process
            recovery_result = await self._trace_workflow_error_recovery(e, segment, error_tracking)
            error_tracking["recovery_attempts"].append(recovery_result)
            
            # Add comprehensive error metadata to agent-level trace
            agent_metadata.update({
                "extraction_successful": False,
                "total_workflow_time_ms": total_workflow_time,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "error_occurred_at": datetime.now().isoformat(),
                "error_stack_trace": str(e),
                "error_tracking": error_tracking,
                "recovery_attempted": len(error_tracking["recovery_attempts"]) > 0,
                "recovery_successful": recovery_result.get("recovery_successful", False) if recovery_result else False,
                "workflow_completion_timestamp": datetime.now().isoformat()
            })
            
            # Log error for monitoring
            print(f"[{self.agent_id}] Extraction workflow failed for {segment.segment_id}: {e}")
            
            # Re-raise the exception after tracing
            raise

    async def start(self):
        """Start listening to transcript stream"""
        self.redis = redis.from_url(self.config.REDIS_URL)
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.config.TRANSCRIPT_TOPIC)
        print(f"[{self.agent_id}] Listening for transcripts...")

        # Async loop to fetch messages
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and "data" in message:
                await self._process_message(message["data"])
            await asyncio.sleep(0.01)

    async def _process_message(self, data: bytes):
        """Process incoming transcript with comprehensive tracing"""
        try:
            segment_dict = json.loads(data)
            segment = TranscriptSegment(**segment_dict)

            print(f"\n[{self.agent_id}] Got transcript: {segment.segment_id}")
            print(f"  Speaker: {segment.speaker}")
            print(f"  Text: {segment.text[:80]}...")

            # Use the main extraction workflow which includes input processing tracing
            extraction = await self.extract_entities(segment)
            await self._publish(extraction)

        except Exception as e:
            print(f"[{self.agent_id}] Error processing message: {e}")

    @traceable(run_type="llm", name="llm_entity_extraction")
    async def _extract(self, segment: TranscriptSegment) -> RawExtraction:
        """Fast extraction using LLM with comprehensive tracing"""
        start = time.time()
        loop = asyncio.get_event_loop()
        
        # Generate LLM extraction metadata
        llm_metadata = self._generate_llm_metadata(
            segment.text,
            timeout_seconds=10,
            extraction_method="async_executor",
            segment_id=segment.segment_id
        )

        try:
            response = await asyncio.wait_for(
                loop.run_in_executor(None, self._call_llm, segment.text),
                timeout=10
            )
            # _call_llm returns a dict of entities (or empty dict on failure)
            entities = response if isinstance(response, dict) else {}
            
            # Calculate response time and success metrics
            response_time_ms = (time.time() - start) * 1000
            extraction_successful = bool(entities)
            
            # Update metadata with success information
            llm_metadata.update({
                "response_time_ms": response_time_ms,
                "timeout_occurred": False,
                "extraction_successful": extraction_successful,
                "entities_extracted": list(entities.keys()) if entities else [],
                "entity_count": len(entities) if entities else 0,
                "api_call_successful": True
            })
            
        except asyncio.TimeoutError:
            print("❌ LLM call timed out")
            entities = {}
            response_time_ms = (time.time() - start) * 1000
            
            # Update metadata with timeout information
            llm_metadata.update({
                "response_time_ms": response_time_ms,
                "timeout_occurred": True,
                "extraction_successful": False,
                "entities_extracted": [],
                "entity_count": 0,
                "api_call_successful": False,
                "error_type": "TimeoutError",
                "error_message": "LLM call exceeded 10 second timeout"
            })

        processing_time = (time.time() - start) * 1000

        extraction = RawExtraction(
            extraction_id=f"ext_{uuid.uuid4().hex[:8]}",
            segment_id=segment.segment_id,
            timestamp=datetime.now(),
            raw_text=segment.text,
            entities=entities,
            processing_time_ms=processing_time
        )

        print(f"  ✓ Extracted in {processing_time:.0f}ms")
        if entities:
            print(f"  Found keys: {list(entities.keys())}")

        return extraction

    @traceable(run_type="llm", name="llm_api_call")
    def _call_llm(self, text: str) -> dict:
        """Call local LLM model and parse output as TravelPlan with comprehensive tracing"""
        api_call_start_time = time.time()
        
        # Generate prompt building metadata
        prompt_metadata = self._generate_prompt_metadata(text)
        
        # Build messages for LLM
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": f"Extract entities from: \"{text}\""}
        ]
        
        # Trace request parameters
        request_metadata = {
            "message_count": len(messages),
            "system_prompt_length": len(self.SYSTEM_PROMPT),
            "user_prompt_length": len(messages[1]["content"]),
            "total_prompt_tokens_estimate": len(self.SYSTEM_PROMPT.split()) + len(messages[1]["content"].split()),
            "request_timestamp": datetime.now().isoformat()
        }
        
        try:
            # Make the API call with timing
            response_obj = self.client.chat(messages=messages)
            api_response_time_ms = (time.time() - api_call_start_time) * 1000
            
            # Trace API call success
            api_call_metadata = {
                "api_call_successful": True,
                "api_response_time_ms": api_response_time_ms,
                "response_received": True,
                **request_metadata
            }
            
            # Extract the assistant message content as string
            content = None
            # Ollama Python client may return a dict or a ChatResponse object
            if isinstance(response_obj, str):
                content = response_obj
            else:
                # Try dict-style access
                try:
                    content = response_obj.get("message", {}).get("content")  # type: ignore[attr-defined]
                except Exception:
                    content = None
                # Try attribute access (ChatResponse.message.content)
                if not content:
                    message_obj = getattr(response_obj, "message", None)
                    if message_obj is not None:
                        content = getattr(message_obj, "content", None)

            if not content or not isinstance(content, str):
                print("❌ Empty or invalid LLM response content")
                api_call_metadata.update({
                    "content_extraction_successful": False,
                    "content_empty": True,
                    "response_content_type": type(content).__name__
                })
                return {}

            # Trace response parsing
            parsing_result = self._parse_llm_response(content)
            
            # Update metadata with parsing results
            api_call_metadata.update({
                "content_extraction_successful": True,
                "content_empty": False,
                "response_content_length": len(content),
                "response_content_type": "string",
                **parsing_result["metadata"]
            })
            
            return parsing_result["entities"]
            
        except Exception as e:
            api_response_time_ms = (time.time() - api_call_start_time) * 1000
            
            # Trace API call failure
            api_call_metadata = {
                "api_call_successful": False,
                "api_response_time_ms": api_response_time_ms,
                "response_received": False,
                "error_type": type(e).__name__,
                "error_message": str(e),
                **request_metadata
            }
            
            print(f"❌ LLM API call failed: {e}")
            return {}

    @traceable(run_type="tool", name="prompt_building")
    def _generate_prompt_metadata(self, text: str) -> dict:
        """Generate metadata for prompt building with tracing"""
        prompt_start_time = time.time()
        
        try:
            # Analyze input text characteristics
            text_analysis = {
                "input_text_length": len(text),
                "input_word_count": len(text.split()),
                "input_character_count": len(text),
                "input_has_travel_keywords": any(keyword in text.lower() 
                                               for keyword in ["travel", "trip", "vacation", "hotel", "flight", "visit", "tour"]),
                "input_has_dates": bool(re.search(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\w+\s+\d{1,2},?\s+\d{4}\b', text)),
                "input_has_numbers": bool(re.search(r'\b\d+\b', text)),
                "input_language_detected": "english"  # Could be enhanced with actual language detection
            }
            
            # Analyze prompt template characteristics
            prompt_analysis = {
                "prompt_template_version": "v1.0",
                "system_prompt_length": len(self.SYSTEM_PROMPT),
                "system_prompt_word_count": len(self.SYSTEM_PROMPT.split()),
                "prompt_contains_examples": "Examples for Egyptian tourism:" in self.SYSTEM_PROMPT,
                "prompt_contains_rules": "RULES:" in self.SYSTEM_PROMPT,
                "prompt_contains_format_spec": "Output JSON format:" in self.SYSTEM_PROMPT
            }
            
            # Calculate prompt building metrics
            prompt_building_time_ms = (time.time() - prompt_start_time) * 1000
            
            prompt_metadata = {
                "prompt_building_time_ms": prompt_building_time_ms,
                "prompt_building_successful": True,
                **text_analysis,
                **prompt_analysis
            }
            
            return prompt_metadata
            
        except Exception as e:
            prompt_building_time_ms = (time.time() - prompt_start_time) * 1000
            return {
                "prompt_building_time_ms": prompt_building_time_ms,
                "prompt_building_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="llm_response_parsing")
    def _parse_llm_response(self, content: str) -> dict:
        """Parse LLM response with comprehensive tracing"""
        parsing_start_time = time.time()
        
        try:
            original_content = content
            content = content.strip()
            
            # Track content preprocessing
            preprocessing_metadata = {
                "original_content_length": len(original_content),
                "content_stripped": original_content != content,
                "content_has_markdown_fences": content.startswith("```") and content.endswith("```"),
                "content_preprocessing_steps": []
            }
            
            # Strip Markdown code fences if present
            if content.startswith("```") and content.endswith("```"):
                lines = content.splitlines()
                if len(lines) >= 2:
                    content = "\n".join(lines[1:-1]).strip()
                    preprocessing_metadata["content_preprocessing_steps"].append("markdown_fence_removal")

            # Sanitize common LLM JSON issues: comments and trailing commas
            def _strip_json_comments(s: str) -> str:
                # Remove //... comments
                s = re.sub(r"(^|[^:])//.*$", r"\1", s, flags=re.MULTILINE)
                # Remove /* ... */ comments
                s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
                return s

            def _remove_trailing_commas(s: str) -> str:
                # Remove trailing commas before } or ]
                return re.sub(r",\s*(\}|\])", r"\1", s)

            sanitized = _remove_trailing_commas(_strip_json_comments(content))
            
            if sanitized != content:
                preprocessing_metadata["content_preprocessing_steps"].extend(["comment_removal", "trailing_comma_removal"])
            
            # Track JSON parsing
            json_parsing_metadata = {
                "final_content_length": len(sanitized),
                "json_parsing_attempted": True,
                "json_parsing_successful": False,
                "json_parsing_error": None
            }
            
            # Ensure we have JSON output
            try:
                data = json.loads(sanitized)
                json_parsing_metadata["json_parsing_successful"] = True
                json_parsing_metadata["parsed_data_type"] = type(data).__name__
                json_parsing_metadata["parsed_data_keys"] = list(data.keys()) if isinstance(data, dict) else []
            except json.JSONDecodeError as e:
                # As a last resort, try original content without sanitation to aid debugging
                print(f"❌ Failed to parse LLM output as JSON: {content}")
                json_parsing_metadata["json_parsing_error"] = str(e)
                data = {}

            # Track TravelPlan validation
            validation_metadata = {
                "travel_plan_validation_attempted": True,
                "travel_plan_validation_successful": False,
                "validation_error": None,
                "final_entities_count": 0,
                "final_entities_keys": []
            }
            
            # Validate and parse using Pydantic model with comprehensive validation
            try:
                travel_plan = TravelPlan(**data)
                validated_entities = travel_plan.dict(exclude_none=True)
                
                # Perform comprehensive TravelPlan validation with tracing
                travel_plan_validation = self._validate_travel_plan(validated_entities)
                
                # Perform detailed entity analysis for backward compatibility
                entity_analysis = self._analyze_extracted_entities(validated_entities)
                
                validation_metadata.update({
                    "travel_plan_validation_successful": True,
                    "final_entities_count": len(validated_entities),
                    "final_entities_keys": list(validated_entities.keys()),
                    "comprehensive_validation": travel_plan_validation,
                    **entity_analysis
                })
                
                final_entities = validated_entities
                
            except Exception as e:
                print(f"❌ TravelPlan validation error: {e}")
                validation_metadata["validation_error"] = str(e)
                
                # Trace validation error and attempt recovery
                error_recovery_result = self._trace_validation_error_recovery(e, data, recovery_attempt=0)
                validation_metadata["error_recovery"] = error_recovery_result
                
                # Use recovered entities if recovery was successful
                if error_recovery_result.get("recovery_successful", False):
                    recovered_entities = error_recovery_result.get("recovered_entities", {})
                    final_entities = recovered_entities
                    
                    # Try validation again with recovered entities
                    if recovered_entities:
                        try:
                            travel_plan_validation = self._validate_travel_plan(recovered_entities)
                            validation_metadata["comprehensive_validation"] = travel_plan_validation
                            validation_metadata["recovery_validation_successful"] = True
                        except Exception as recovery_validation_error:
                            print(f"❌ Recovery validation also failed: {recovery_validation_error}")
                            validation_metadata["recovery_validation_error"] = str(recovery_validation_error)
                            validation_metadata["recovery_validation_successful"] = False
                else:
                    # Return raw dict if recovery failed
                    final_entities = data if isinstance(data, dict) else {}
                
                # Trace rejected fields between raw and final entities
                if data and final_entities:
                    rejected_fields_analysis = self._trace_rejected_fields(data, final_entities)
                    validation_metadata["rejected_fields_analysis"] = rejected_fields_analysis
                
                # Analyze final entities even if validation failed
                if final_entities:
                    entity_analysis = self._analyze_extracted_entities(final_entities)
                    validation_metadata.update({
                        "final_entities_count": len(final_entities),
                        "final_entities_keys": list(final_entities.keys()),
                        **entity_analysis
                    })
            
            # Calculate parsing metrics
            parsing_time_ms = (time.time() - parsing_start_time) * 1000
            
            parsing_result = {
                "entities": final_entities,
                "metadata": {
                    "parsing_time_ms": parsing_time_ms,
                    "parsing_successful": True,
                    **preprocessing_metadata,
                    **json_parsing_metadata,
                    **validation_metadata
                }
            }
            
            return parsing_result
            
        except Exception as e:
            parsing_time_ms = (time.time() - parsing_start_time) * 1000
            return {
                "entities": {},
                "metadata": {
                    "parsing_time_ms": parsing_time_ms,
                    "parsing_successful": False,
                    "error_type": type(e).__name__,
                    "error_message": str(e)
                }
            }

    @traceable(run_type="tool", name="travel_plan_validation")
    def _validate_travel_plan(self, entities: dict) -> dict:
        """
        Validate TravelPlan entities with comprehensive tracing.
        
        Args:
            entities: Raw extracted entities dictionary
            
        Returns:
            dict: Validation results with detailed metadata
        """
        validation_start_time = time.time()
        
        try:
            # Initialize validation tracking
            validation_metadata = self._generate_validation_metadata(entities)
            
            # Track input entities and validation rules application
            input_analysis = {
                "input_entities_received": list(entities.keys()) if entities else [],
                "input_entities_count": len(entities) if entities else 0,
                "validation_rules_applied": [],
                "validation_start_timestamp": datetime.now().isoformat()
            }
            
            # Apply date parsing and format validation tracing
            date_validation = self._validate_dates_with_tracing(entities.get("dates", []))
            input_analysis["validation_rules_applied"].append("date_validation")
            
            # Apply activity sentence structure analysis tracing
            activity_validation = self._validate_activities_with_tracing(entities.get("activities", []))
            input_analysis["validation_rules_applied"].append("activity_structure_analysis")
            
            # Apply budget validation tracing
            budget_validation = self._validate_budget_with_tracing(entities.get("budget"))
            input_analysis["validation_rules_applied"].append("budget_validation")
            
            # Apply travelers validation tracing
            travelers_validation = self._validate_travelers_with_tracing(entities.get("travelers"))
            input_analysis["validation_rules_applied"].append("travelers_validation")
            
            # Apply locations validation tracing
            locations_validation = self._validate_locations_with_tracing(entities.get("locations", []))
            input_analysis["validation_rules_applied"].append("locations_validation")
            
            # Apply preferences and keywords validation tracing
            preferences_validation = self._validate_preferences_with_tracing(entities.get("preferences", []))
            keywords_validation = self._validate_keywords_with_tracing(entities.get("keywords", []))
            input_analysis["validation_rules_applied"].extend(["preferences_validation", "keywords_validation"])
            
            # Compile comprehensive validation results
            validation_time_ms = (time.time() - validation_start_time) * 1000
            
            validation_result = {
                "validation_time_ms": validation_time_ms,
                "validation_successful": True,
                **input_analysis,
                **validation_metadata,
                "date_validation": date_validation,
                "activity_validation": activity_validation,
                "budget_validation": budget_validation,
                "travelers_validation": travelers_validation,
                "locations_validation": locations_validation,
                "preferences_validation": preferences_validation,
                "keywords_validation": keywords_validation,
                "overall_validation_score": self._calculate_validation_score([
                    date_validation, activity_validation, budget_validation,
                    travelers_validation, locations_validation, preferences_validation, keywords_validation
                ])
            }
            
            # Add validation completion tracing
            completion_tracing = self._trace_validation_completion(entities, validation_result)
            validation_result["validation_completion"] = completion_tracing
            
            return validation_result
            
        except Exception as e:
            validation_time_ms = (time.time() - validation_start_time) * 1000
            return {
                "validation_time_ms": validation_time_ms,
                "validation_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e),
                "validation_failed_at": datetime.now().isoformat()
            }

    @traceable(run_type="tool", name="date_parsing_validation")
    def _validate_dates_with_tracing(self, dates: list) -> dict:
        """
        Validate and parse travel dates with comprehensive tracing.
        
        Args:
            dates: List of date strings to validate
            
        Returns:
            dict: Date validation results with metadata
        """
        date_validation_start = time.time()
        
        try:
            date_validation_result = {
                "dates_received": dates,
                "dates_count": len(dates),
                "date_parsing_results": [],
                "format_validation_results": [],
                "normalization_results": []
            }
            
            # Parse and validate each date
            for i, date_str in enumerate(dates):
                date_parsing = self._parse_single_date_with_tracing(date_str, i)
                date_validation_result["date_parsing_results"].append(date_parsing)
                
                # Format validation
                format_validation = self._validate_date_format_with_tracing(date_str, date_parsing)
                date_validation_result["format_validation_results"].append(format_validation)
                
                # Date normalization
                normalization = self._normalize_date_with_tracing(date_str, date_parsing)
                date_validation_result["normalization_results"].append(normalization)
            
            # Calculate overall date validation metrics
            successful_parses = sum(1 for result in date_validation_result["date_parsing_results"] if result.get("parsing_successful", False))
            successful_formats = sum(1 for result in date_validation_result["format_validation_results"] if result.get("format_valid", False))
            successful_normalizations = sum(1 for result in date_validation_result["normalization_results"] if result.get("normalization_successful", False))
            
            date_validation_time_ms = (time.time() - date_validation_start) * 1000
            
            date_validation_result.update({
                "date_validation_time_ms": date_validation_time_ms,
                "successful_parses": successful_parses,
                "successful_formats": successful_formats,
                "successful_normalizations": successful_normalizations,
                "overall_date_success_rate": (successful_parses / len(dates)) if dates else 0.0,
                "date_validation_successful": successful_parses > 0 if dates else True
            })
            
            return date_validation_result
            
        except Exception as e:
            date_validation_time_ms = (time.time() - date_validation_start) * 1000
            return {
                "date_validation_time_ms": date_validation_time_ms,
                "date_validation_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="single_date_parsing")
    def _parse_single_date_with_tracing(self, date_str: str, index: int) -> dict:
        """Parse a single date string with detailed tracing."""
        parsing_start = time.time()
        
        try:
            # Analyze date string characteristics
            date_analysis = {
                "date_index": index,
                "original_date_string": date_str,
                "date_string_length": len(date_str),
                "contains_numbers": bool(re.search(r'\d', date_str)),
                "contains_month_names": any(month in date_str.lower() for month in [
                    "january", "february", "march", "april", "may", "june",
                    "july", "august", "september", "october", "november", "december",
                    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"
                ]),
                "contains_relative_terms": any(term in date_str.lower() for term in [
                    "next", "this", "coming", "upcoming", "soon", "later", "winter", "summer", "spring", "fall"
                ]),
                "date_format_detected": None
            }
            
            # Attempt to detect date format patterns
            if re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_str):
                date_analysis["date_format_detected"] = "numeric_slash_dash"
            elif re.search(r'\w+\s+\d{1,2},?\s+\d{4}', date_str):
                date_analysis["date_format_detected"] = "month_day_year"
            elif re.search(r'\d{4}-\d{2}-\d{2}', date_str):
                date_analysis["date_format_detected"] = "iso_format"
            else:
                date_analysis["date_format_detected"] = "relative_or_text"
            
            parsing_time_ms = (time.time() - parsing_start) * 1000
            
            parsing_result = {
                **date_analysis,
                "parsing_time_ms": parsing_time_ms,
                "parsing_successful": True,
                "parsing_confidence": "high" if date_analysis["date_format_detected"] in ["numeric_slash_dash", "month_day_year", "iso_format"] else "low"
            }
            
            return parsing_result
            
        except Exception as e:
            parsing_time_ms = (time.time() - parsing_start) * 1000
            return {
                "date_index": index,
                "parsing_time_ms": parsing_time_ms,
                "parsing_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="date_format_validation")
    def _validate_date_format_with_tracing(self, date_str: str, parsing_result: dict) -> dict:
        """Validate date format with tracing."""
        format_validation_start = time.time()
        
        try:
            format_checks = {
                "has_valid_numeric_format": bool(re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', date_str)),
                "has_valid_text_format": bool(re.search(r'\w+\s+\d{1,2},?\s+\d{4}', date_str)),
                "has_iso_format": bool(re.search(r'\d{4}-\d{2}-\d{2}', date_str)),
                "is_relative_date": any(term in date_str.lower() for term in ["next", "this", "winter", "summer"]),
                "format_ambiguous": len(date_str.split()) > 4,  # Too many words might be ambiguous
                "format_too_short": len(date_str.strip()) < 3
            }
            
            # Determine overall format validity
            format_valid = any([
                format_checks["has_valid_numeric_format"],
                format_checks["has_valid_text_format"],
                format_checks["has_iso_format"],
                format_checks["is_relative_date"]
            ]) and not format_checks["format_too_short"]
            
            format_validation_time_ms = (time.time() - format_validation_start) * 1000
            
            format_result = {
                "format_validation_time_ms": format_validation_time_ms,
                "format_valid": format_valid,
                "format_confidence": parsing_result.get("parsing_confidence", "unknown"),
                **format_checks
            }
            
            return format_result
            
        except Exception as e:
            format_validation_time_ms = (time.time() - format_validation_start) * 1000
            return {
                "format_validation_time_ms": format_validation_time_ms,
                "format_valid": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="date_normalization")
    def _normalize_date_with_tracing(self, date_str: str, parsing_result: dict) -> dict:
        """Normalize date string with tracing."""
        normalization_start = time.time()
        
        try:
            # Normalize the date string
            normalized_date = date_str.strip().lower()
            
            # Apply normalization rules
            normalization_steps = []
            
            # Convert common abbreviations
            month_abbrevs = {
                "jan": "january", "feb": "february", "mar": "march", "apr": "april",
                "jun": "june", "jul": "july", "aug": "august", "sep": "september",
                "oct": "october", "nov": "november", "dec": "december"
            }
            
            for abbrev, full_name in month_abbrevs.items():
                if abbrev in normalized_date:
                    normalized_date = normalized_date.replace(abbrev, full_name)
                    normalization_steps.append(f"expanded_{abbrev}_to_{full_name}")
            
            # Standardize relative terms
            if "next" in normalized_date:
                normalization_steps.append("identified_relative_next")
            if "this" in normalized_date:
                normalization_steps.append("identified_relative_this")
            
            normalization_time_ms = (time.time() - normalization_start) * 1000
            
            normalization_result = {
                "normalization_time_ms": normalization_time_ms,
                "normalization_successful": True,
                "original_date": date_str,
                "normalized_date": normalized_date,
                "normalization_steps": normalization_steps,
                "normalization_changed": normalized_date != date_str.strip().lower()
            }
            
            return normalization_result
            
        except Exception as e:
            normalization_time_ms = (time.time() - normalization_start) * 1000
            return {
                "normalization_time_ms": normalization_time_ms,
                "normalization_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="activity_structure_analysis")
    def _validate_activities_with_tracing(self, activities: list) -> dict:
        """
        Validate activity sentence structure with comprehensive tracing.
        
        Args:
            activities: List of activity strings to analyze
            
        Returns:
            dict: Activity validation results with detailed structure analysis
        """
        activity_validation_start = time.time()
        
        try:
            activity_validation_result = {
                "activities_received": activities,
                "activities_count": len(activities),
                "sentence_structure_analysis": [],
                "semantic_richness_analysis": [],
                "overall_activity_quality_score": 0.0
            }
            
            # Analyze each activity's sentence structure
            for i, activity in enumerate(activities):
                structure_analysis = self._analyze_activity_structure_with_tracing(activity, i)
                activity_validation_result["sentence_structure_analysis"].append(structure_analysis)
                
                semantic_analysis = self._analyze_activity_semantics_with_tracing(activity, i)
                activity_validation_result["semantic_richness_analysis"].append(semantic_analysis)
            
            # Calculate overall activity quality metrics
            if activities:
                structure_scores = [analysis.get("structure_quality_score", 0) for analysis in activity_validation_result["sentence_structure_analysis"]]
                semantic_scores = [analysis.get("semantic_richness_score", 0) for analysis in activity_validation_result["semantic_richness_analysis"]]
                
                avg_structure_score = sum(structure_scores) / len(structure_scores)
                avg_semantic_score = sum(semantic_scores) / len(semantic_scores)
                
                activity_validation_result["overall_activity_quality_score"] = (avg_structure_score + avg_semantic_score) / 2
                activity_validation_result["average_structure_score"] = avg_structure_score
                activity_validation_result["average_semantic_score"] = avg_semantic_score
                activity_validation_result["high_quality_activities"] = sum(1 for score in structure_scores if score >= 75)
            else:
                activity_validation_result["overall_activity_quality_score"] = 0.0
                activity_validation_result["average_structure_score"] = 0.0
                activity_validation_result["average_semantic_score"] = 0.0
                activity_validation_result["high_quality_activities"] = 0
            
            activity_validation_time_ms = (time.time() - activity_validation_start) * 1000
            
            activity_validation_result.update({
                "activity_validation_time_ms": activity_validation_time_ms,
                "activity_validation_successful": True,
                "activities_well_structured": activity_validation_result["high_quality_activities"] > 0 if activities else True
            })
            
            return activity_validation_result
            
        except Exception as e:
            activity_validation_time_ms = (time.time() - activity_validation_start) * 1000
            return {
                "activity_validation_time_ms": activity_validation_time_ms,
                "activity_validation_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="single_activity_structure_analysis")
    def _analyze_activity_structure_with_tracing(self, activity: str, index: int) -> dict:
        """Analyze the sentence structure of a single activity with tracing."""
        structure_analysis_start = time.time()
        
        try:
            # Analyze sentence structure components
            structure_components = {
                "activity_index": index,
                "original_activity": activity,
                "word_count": len(activity.split()),
                "character_count": len(activity),
                "is_complete_sentence": activity.strip().endswith(('.', '!', '?')),
                "has_action_verb": any(verb in activity.lower() for verb in [
                    "visit", "explore", "experience", "tour", "see", "enjoy", "take", "go", "travel",
                    "discover", "learn", "participate", "attend", "watch", "observe", "climb", "walk"
                ]),
                "has_descriptive_adjectives": any(adj in activity.lower() for adj in [
                    "ancient", "beautiful", "historic", "traditional", "cultural", "scenic", "amazing",
                    "spectacular", "magnificent", "breathtaking", "unique", "authentic", "local"
                ]),
                "has_location_context": any(loc in activity.lower() for loc in [
                    "pyramid", "nile", "desert", "temple", "museum", "red sea", "cairo", "giza", "luxor",
                    "aswan", "alexandria", "valley", "tomb", "monument", "bazaar", "market"
                ]),
                "has_prepositions": any(prep in activity.lower() for prep in [
                    "in", "at", "on", "through", "around", "near", "by", "from", "to", "with"
                ]),
                "sentence_complexity": "simple" if len(activity.split()) <= 5 else "moderate" if len(activity.split()) <= 10 else "complex"
            }
            
            # Calculate structure quality score
            structure_quality_score = (
                (structure_components["word_count"] >= 5) * 20 +  # Adequate length
                structure_components["is_complete_sentence"] * 15 +  # Proper sentence ending
                structure_components["has_action_verb"] * 25 +  # Action verb present
                structure_components["has_descriptive_adjectives"] * 15 +  # Descriptive language
                structure_components["has_location_context"] * 20 +  # Location context
                structure_components["has_prepositions"] * 5  # Grammatical complexity
            )
            
            structure_analysis_time_ms = (time.time() - structure_analysis_start) * 1000
            
            structure_result = {
                **structure_components,
                "structure_analysis_time_ms": structure_analysis_time_ms,
                "structure_quality_score": structure_quality_score,
                "structure_analysis_successful": True,
                "structure_quality_level": "high" if structure_quality_score >= 75 else "medium" if structure_quality_score >= 50 else "low"
            }
            
            return structure_result
            
        except Exception as e:
            structure_analysis_time_ms = (time.time() - structure_analysis_start) * 1000
            return {
                "activity_index": index,
                "structure_analysis_time_ms": structure_analysis_time_ms,
                "structure_analysis_successful": False,
                "structure_quality_score": 0,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="activity_semantic_analysis")
    def _analyze_activity_semantics_with_tracing(self, activity: str, index: int) -> dict:
        """Analyze the semantic richness of a single activity with tracing."""
        semantic_analysis_start = time.time()
        
        try:
            # Analyze semantic richness components
            semantic_components = {
                "activity_index": index,
                "contains_cultural_keywords": any(keyword in activity.lower() for keyword in [
                    "culture", "cultural", "history", "historic", "ancient", "traditional", "heritage",
                    "pharaoh", "egyptian", "islamic", "coptic", "bedouin", "nubian"
                ]),
                "contains_experience_keywords": any(keyword in activity.lower() for keyword in [
                    "experience", "adventure", "journey", "discovery", "exploration", "immersion",
                    "authentic", "unique", "memorable", "unforgettable"
                ]),
                "contains_activity_type_keywords": any(keyword in activity.lower() for keyword in [
                    "tour", "cruise", "safari", "diving", "snorkeling", "hiking", "climbing", "riding",
                    "shopping", "dining", "tasting", "learning", "photography"
                ]),
                "contains_sensory_language": any(keyword in activity.lower() for keyword in [
                    "see", "hear", "feel", "taste", "smell", "touch", "watch", "listen", "observe",
                    "colorful", "vibrant", "peaceful", "bustling", "quiet", "loud"
                ]),
                "contains_time_context": any(keyword in activity.lower() for keyword in [
                    "morning", "afternoon", "evening", "sunset", "sunrise", "night", "day", "overnight",
                    "duration", "hours", "minutes", "full-day", "half-day"
                ]),
                "searchability_score": 0
            }
            
            # Calculate searchability score for RAG retrieval
            searchability_factors = [
                semantic_components["contains_cultural_keywords"] * 20,
                semantic_components["contains_experience_keywords"] * 15,
                semantic_components["contains_activity_type_keywords"] * 25,
                semantic_components["contains_sensory_language"] * 15,
                semantic_components["contains_time_context"] * 10,
                (len(activity.split()) >= 6) * 15  # Adequate detail for search
            ]
            
            semantic_components["searchability_score"] = sum(searchability_factors)
            
            # Calculate overall semantic richness score
            semantic_richness_score = (
                semantic_components["contains_cultural_keywords"] * 20 +
                semantic_components["contains_experience_keywords"] * 20 +
                semantic_components["contains_activity_type_keywords"] * 25 +
                semantic_components["contains_sensory_language"] * 20 +
                semantic_components["contains_time_context"] * 15
            )
            
            semantic_analysis_time_ms = (time.time() - semantic_analysis_start) * 1000
            
            semantic_result = {
                **semantic_components,
                "semantic_analysis_time_ms": semantic_analysis_time_ms,
                "semantic_richness_score": semantic_richness_score,
                "semantic_analysis_successful": True,
                "semantic_quality_level": "high" if semantic_richness_score >= 75 else "medium" if semantic_richness_score >= 50 else "low",
                "rag_retrieval_ready": semantic_components["searchability_score"] >= 60
            }
            
            return semantic_result
            
        except Exception as e:
            semantic_analysis_time_ms = (time.time() - semantic_analysis_start) * 1000
            return {
                "activity_index": index,
                "semantic_analysis_time_ms": semantic_analysis_time_ms,
                "semantic_analysis_successful": False,
                "semantic_richness_score": 0,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="budget_validation")
    def _validate_budget_with_tracing(self, budget: dict) -> dict:
        """Validate budget information with tracing."""
        budget_validation_start = time.time()
        
        try:
            if not budget:
                return {
                    "budget_validation_time_ms": (time.time() - budget_validation_start) * 1000,
                    "budget_present": False,
                    "validation_score": 0.0,
                    "budget_validation_successful": True  # No budget is valid
                }
            
            budget_analysis = {
                "budget_present": True,
                "has_amount": "amount" in budget and budget["amount"] is not None,
                "has_flexibility": "flexibility" in budget and budget["flexibility"] is not None,
                "amount_is_numeric": isinstance(budget.get("amount"), (int, float)) if budget.get("amount") is not None else False,
                "amount_is_reasonable": False,
                "flexibility_is_valid": False
            }
            
            # Validate amount reasonableness
            if budget_analysis["amount_is_numeric"]:
                amount = budget["amount"]
                budget_analysis["amount_is_reasonable"] = 100 <= amount <= 50000  # Reasonable travel budget range
                budget_analysis["amount_value"] = amount
            
            # Validate flexibility values
            if budget_analysis["has_flexibility"]:
                flexibility = str(budget["flexibility"]).lower()
                valid_flexibility_terms = ["low", "moderate", "high", "flexible", "strict", "some", "none"]
                budget_analysis["flexibility_is_valid"] = any(term in flexibility for term in valid_flexibility_terms)
                budget_analysis["flexibility_value"] = flexibility
            
            # Calculate validation score
            validation_score = (
                budget_analysis["has_amount"] * 40 +
                budget_analysis["has_flexibility"] * 20 +
                budget_analysis["amount_is_numeric"] * 20 +
                budget_analysis["amount_is_reasonable"] * 15 +
                budget_analysis["flexibility_is_valid"] * 5
            )
            
            budget_validation_time_ms = (time.time() - budget_validation_start) * 1000
            
            budget_result = {
                **budget_analysis,
                "budget_validation_time_ms": budget_validation_time_ms,
                "validation_score": validation_score,
                "budget_validation_successful": True,
                "budget_quality_level": "high" if validation_score >= 75 else "medium" if validation_score >= 50 else "low"
            }
            
            return budget_result
            
        except Exception as e:
            budget_validation_time_ms = (time.time() - budget_validation_start) * 1000
            return {
                "budget_validation_time_ms": budget_validation_time_ms,
                "budget_validation_successful": False,
                "validation_score": 0.0,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="travelers_validation")
    def _validate_travelers_with_tracing(self, travelers: dict) -> dict:
        """Validate travelers information with tracing."""
        travelers_validation_start = time.time()
        
        try:
            if not travelers:
                return {
                    "travelers_validation_time_ms": (time.time() - travelers_validation_start) * 1000,
                    "travelers_present": False,
                    "validation_score": 0.0,
                    "travelers_validation_successful": True  # No travelers info is valid
                }
            
            travelers_analysis = {
                "travelers_present": True,
                "has_adults": "adults" in travelers and travelers["adults"] is not None,
                "has_children": "children" in travelers and travelers["children"] is not None,
                "has_rooms": "num_of_rooms" in travelers and travelers["num_of_rooms"] is not None,
                "adults_is_numeric": isinstance(travelers.get("adults"), int) if travelers.get("adults") is not None else False,
                "children_is_numeric": isinstance(travelers.get("children"), int) if travelers.get("children") is not None else False,
                "rooms_is_numeric": isinstance(travelers.get("num_of_rooms"), int) if travelers.get("num_of_rooms") is not None else False,
                "adults_is_reasonable": False,
                "children_is_reasonable": False,
                "rooms_is_reasonable": False,
                "total_travelers": 0
            }
            
            # Validate adults count
            if travelers_analysis["adults_is_numeric"]:
                adults = travelers["adults"]
                travelers_analysis["adults_is_reasonable"] = 1 <= adults <= 20  # Reasonable range
                travelers_analysis["adults_count"] = adults
                travelers_analysis["total_travelers"] += adults
            
            # Validate children count
            if travelers_analysis["children_is_numeric"]:
                children = travelers["children"]
                travelers_analysis["children_is_reasonable"] = 0 <= children <= 10  # Reasonable range
                travelers_analysis["children_count"] = children
                travelers_analysis["total_travelers"] += children
            
            # Validate rooms count
            if travelers_analysis["rooms_is_numeric"]:
                rooms = travelers["num_of_rooms"]
                travelers_analysis["rooms_is_reasonable"] = 1 <= rooms <= 10  # Reasonable range
                travelers_analysis["rooms_count"] = rooms
                
                # Check if rooms make sense with traveler count
                if travelers_analysis["total_travelers"] > 0:
                    travelers_analysis["rooms_to_travelers_ratio_reasonable"] = rooms <= travelers_analysis["total_travelers"]
                else:
                    travelers_analysis["rooms_to_travelers_ratio_reasonable"] = True
            
            # Calculate validation score
            validation_score = (
                travelers_analysis["has_adults"] * 30 +
                travelers_analysis["adults_is_numeric"] * 20 +
                travelers_analysis["adults_is_reasonable"] * 20 +
                travelers_analysis["has_children"] * 10 +
                travelers_analysis["children_is_reasonable"] * 10 +
                travelers_analysis["has_rooms"] * 5 +
                travelers_analysis["rooms_is_reasonable"] * 5
            )
            
            travelers_validation_time_ms = (time.time() - travelers_validation_start) * 1000
            
            travelers_result = {
                **travelers_analysis,
                "travelers_validation_time_ms": travelers_validation_time_ms,
                "validation_score": validation_score,
                "travelers_validation_successful": True,
                "travelers_quality_level": "high" if validation_score >= 75 else "medium" if validation_score >= 50 else "low"
            }
            
            return travelers_result
            
        except Exception as e:
            travelers_validation_time_ms = (time.time() - travelers_validation_start) * 1000
            return {
                "travelers_validation_time_ms": travelers_validation_time_ms,
                "travelers_validation_successful": False,
                "validation_score": 0.0,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="locations_validation")
    def _validate_locations_with_tracing(self, locations: list) -> dict:
        """Validate locations information with tracing."""
        locations_validation_start = time.time()
        
        try:
            locations_analysis = {
                "locations_received": locations,
                "locations_count": len(locations),
                "egyptian_locations_found": [],
                "international_locations_found": [],
                "location_types_identified": [],
                "location_specificity_scores": []
            }
            
            # Known Egyptian locations for validation
            egyptian_locations = [
                "cairo", "giza", "luxor", "aswan", "alexandria", "hurghada", "sharm el sheikh",
                "dahab", "marsa alam", "siwa", "abu simbel", "edfu", "kom ombo", "philae",
                "valley of the kings", "karnak", "pyramid", "pyramids", "sphinx", "nile"
            ]
            
            # Analyze each location
            for location in locations:
                location_lower = location.lower()
                
                # Check if it's an Egyptian location
                if any(eg_loc in location_lower for eg_loc in egyptian_locations):
                    locations_analysis["egyptian_locations_found"].append(location)
                else:
                    locations_analysis["international_locations_found"].append(location)
                
                # Determine location type
                if any(site in location_lower for site in ["pyramid", "temple", "museum", "valley", "tomb"]):
                    locations_analysis["location_types_identified"].append("historical_site")
                elif any(city in location_lower for city in ["cairo", "luxor", "aswan", "alexandria"]):
                    locations_analysis["location_types_identified"].append("city")
                elif any(water in location_lower for water in ["nile", "red sea", "mediterranean"]):
                    locations_analysis["location_types_identified"].append("water_body")
                else:
                    locations_analysis["location_types_identified"].append("general")
                
                # Calculate specificity score
                specificity_score = (
                    (len(location.split()) > 1) * 30 +  # Multi-word locations are more specific
                    any(eg_loc in location_lower for eg_loc in egyptian_locations) * 40 +  # Egyptian context
                    (len(location) > 5) * 20 +  # Adequate length
                    any(char.isupper() for char in location) * 10  # Proper capitalization
                )
                locations_analysis["location_specificity_scores"].append(specificity_score)
            
            # Calculate overall metrics
            avg_specificity = sum(locations_analysis["location_specificity_scores"]) / len(locations_analysis["location_specificity_scores"]) if locations_analysis["location_specificity_scores"] else 0
            egyptian_ratio = len(locations_analysis["egyptian_locations_found"]) / len(locations) if locations else 0
            
            validation_score = (
                (len(locations) > 0) * 30 +  # Has locations
                (avg_specificity >= 50) * 30 +  # Good specificity
                (egyptian_ratio >= 0.5) * 25 +  # Mostly Egyptian locations
                (len(set(locations_analysis["location_types_identified"])) > 1) * 15  # Diverse location types
            )
            
            locations_validation_time_ms = (time.time() - locations_validation_start) * 1000
            
            locations_result = {
                **locations_analysis,
                "locations_validation_time_ms": locations_validation_time_ms,
                "average_specificity_score": avg_specificity,
                "egyptian_locations_ratio": egyptian_ratio,
                "validation_score": validation_score,
                "locations_validation_successful": True,
                "locations_quality_level": "high" if validation_score >= 75 else "medium" if validation_score >= 50 else "low"
            }
            
            return locations_result
            
        except Exception as e:
            locations_validation_time_ms = (time.time() - locations_validation_start) * 1000
            return {
                "locations_validation_time_ms": locations_validation_time_ms,
                "locations_validation_successful": False,
                "validation_score": 0.0,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="preferences_validation")
    def _validate_preferences_with_tracing(self, preferences: list) -> dict:
        """Validate preferences information with tracing."""
        preferences_validation_start = time.time()
        
        try:
            preferences_analysis = {
                "preferences_received": preferences,
                "preferences_count": len(preferences),
                "preference_categories": {
                    "accommodation": [],
                    "activity_type": [],
                    "pace": [],
                    "budget_related": [],
                    "cultural": [],
                    "other": []
                },
                "preference_specificity_scores": []
            }
            
            # Categorize preferences
            for preference in preferences:
                pref_lower = preference.lower()
                
                # Accommodation preferences
                if any(term in pref_lower for term in ["hotel", "resort", "accommodation", "room", "suite", "luxury", "budget"]):
                    preferences_analysis["preference_categories"]["accommodation"].append(preference)
                # Activity type preferences
                elif any(term in pref_lower for term in ["tour", "guide", "adventure", "cultural", "historical", "relaxing"]):
                    preferences_analysis["preference_categories"]["activity_type"].append(preference)
                # Pace preferences
                elif any(term in pref_lower for term in ["fast", "slow", "moderate", "pace", "leisurely", "intensive"]):
                    preferences_analysis["preference_categories"]["pace"].append(preference)
                # Budget-related preferences
                elif any(term in pref_lower for term in ["cheap", "expensive", "affordable", "premium", "value"]):
                    preferences_analysis["preference_categories"]["budget_related"].append(preference)
                # Cultural preferences
                elif any(term in pref_lower for term in ["authentic", "local", "traditional", "modern", "western"]):
                    preferences_analysis["preference_categories"]["cultural"].append(preference)
                else:
                    preferences_analysis["preference_categories"]["other"].append(preference)
                
                # Calculate specificity score
                specificity_score = (
                    (len(preference.split()) > 1) * 25 +  # Multi-word preferences are more specific
                    (len(preference) > 8) * 25 +  # Adequate detail
                    any(term in pref_lower for term in ["family-friendly", "cultural", "historical", "authentic"]) * 30 +  # Travel-relevant terms
                    (preference != preference.lower()) * 20  # Proper capitalization
                )
                preferences_analysis["preference_specificity_scores"].append(specificity_score)
            
            # Calculate metrics
            avg_specificity = sum(preferences_analysis["preference_specificity_scores"]) / len(preferences_analysis["preference_specificity_scores"]) if preferences_analysis["preference_specificity_scores"] else 0
            category_diversity = sum(1 for category in preferences_analysis["preference_categories"].values() if category)
            
            validation_score = (
                (len(preferences) > 0) * 30 +  # Has preferences
                (avg_specificity >= 50) * 30 +  # Good specificity
                (category_diversity >= 2) * 25 +  # Diverse categories
                (len(preferences) >= 3) * 15  # Adequate number of preferences
            )
            
            preferences_validation_time_ms = (time.time() - preferences_validation_start) * 1000
            
            preferences_result = {
                **preferences_analysis,
                "preferences_validation_time_ms": preferences_validation_time_ms,
                "average_specificity_score": avg_specificity,
                "category_diversity_score": category_diversity,
                "validation_score": validation_score,
                "preferences_validation_successful": True,
                "preferences_quality_level": "high" if validation_score >= 75 else "medium" if validation_score >= 50 else "low"
            }
            
            return preferences_result
            
        except Exception as e:
            preferences_validation_time_ms = (time.time() - preferences_validation_start) * 1000
            return {
                "preferences_validation_time_ms": preferences_validation_time_ms,
                "preferences_validation_successful": False,
                "validation_score": 0.0,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="keywords_validation")
    def _validate_keywords_with_tracing(self, keywords: list) -> dict:
        """Validate keywords information with tracing."""
        keywords_validation_start = time.time()
        
        try:
            keywords_analysis = {
                "keywords_received": keywords,
                "keywords_count": len(keywords),
                "travel_relevant_keywords": [],
                "cultural_keywords": [],
                "activity_keywords": [],
                "emotional_keywords": [],
                "keyword_relevance_scores": []
            }
            
            # Analyze each keyword
            for keyword in keywords:
                keyword_lower = keyword.lower()
                
                # Travel-relevant keywords
                if any(term in keyword_lower for term in ["travel", "trip", "vacation", "tourism", "journey", "adventure"]):
                    keywords_analysis["travel_relevant_keywords"].append(keyword)
                
                # Cultural keywords
                if any(term in keyword_lower for term in ["culture", "history", "ancient", "traditional", "heritage", "art"]):
                    keywords_analysis["cultural_keywords"].append(keyword)
                
                # Activity keywords
                if any(term in keyword_lower for term in ["diving", "photography", "exploration", "sightseeing", "shopping", "dining"]):
                    keywords_analysis["activity_keywords"].append(keyword)
                
                # Emotional keywords
                if any(term in keyword_lower for term in ["exciting", "relaxing", "peaceful", "adventurous", "romantic", "fun"]):
                    keywords_analysis["emotional_keywords"].append(keyword)
                
                # Calculate relevance score
                relevance_score = (
                    any(term in keyword_lower for term in ["egypt", "cairo", "pyramid", "nile", "desert"]) * 40 +  # Egypt-specific
                    any(term in keyword_lower for term in ["culture", "history", "ancient", "traditional"]) * 30 +  # Cultural relevance
                    any(term in keyword_lower for term in ["adventure", "exploration", "photography"]) * 20 +  # Activity relevance
                    (len(keyword) > 4) * 10  # Adequate length
                )
                keywords_analysis["keyword_relevance_scores"].append(relevance_score)
            
            # Calculate metrics
            avg_relevance = sum(keywords_analysis["keyword_relevance_scores"]) / len(keywords_analysis["keyword_relevance_scores"]) if keywords_analysis["keyword_relevance_scores"] else 0
            high_relevance_keywords = sum(1 for score in keywords_analysis["keyword_relevance_scores"] if score >= 60)
            
            validation_score = (
                (len(keywords) > 0) * 25 +  # Has keywords
                (avg_relevance >= 40) * 35 +  # Good relevance
                (high_relevance_keywords > 0) * 25 +  # At least one highly relevant keyword
                (len(keywords) >= 3) * 15  # Adequate number of keywords
            )
            
            keywords_validation_time_ms = (time.time() - keywords_validation_start) * 1000
            
            keywords_result = {
                **keywords_analysis,
                "keywords_validation_time_ms": keywords_validation_time_ms,
                "average_relevance_score": avg_relevance,
                "high_relevance_keywords_count": high_relevance_keywords,
                "validation_score": validation_score,
                "keywords_validation_successful": True,
                "keywords_quality_level": "high" if validation_score >= 75 else "medium" if validation_score >= 50 else "low"
            }
            
            return keywords_result
            
        except Exception as e:
            keywords_validation_time_ms = (time.time() - keywords_validation_start) * 1000
            return {
                "keywords_validation_time_ms": keywords_validation_time_ms,
                "keywords_validation_successful": False,
                "validation_score": 0.0,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="validation_completion_tracing")
    def _trace_validation_completion(self, entities: dict, validation_results: dict) -> dict:
        """
        Trace validation completion with detailed entity and field analysis.
        
        Args:
            entities: The validated entities dictionary
            validation_results: Results from comprehensive validation
            
        Returns:
            dict: Validation completion metadata
        """
        completion_tracing_start = time.time()
        
        try:
            # Trace validated entities
            validated_entities_analysis = {
                "validated_entities": list(entities.keys()) if entities else [],
                "validated_entities_count": len(entities) if entities else 0,
                "entity_field_completeness": {},
                "data_completeness_score": 0.0,
                "validation_quality_indicators": {}
            }
            
            # Analyze completeness for each entity type
            expected_entities = ["dates", "budget", "travelers", "locations", "activities", "preferences", "keywords"]
            
            for entity_type in expected_entities:
                if entity_type in entities and entities[entity_type]:
                    entity_data = entities[entity_type]
                    
                    # Analyze field completeness based on entity type
                    if entity_type == "budget" and isinstance(entity_data, dict):
                        completeness = {
                            "has_amount": "amount" in entity_data and entity_data["amount"] is not None,
                            "has_flexibility": "flexibility" in entity_data and entity_data["flexibility"] is not None,
                            "completeness_percentage": 0
                        }
                        completeness["completeness_percentage"] = (
                            completeness["has_amount"] * 60 + completeness["has_flexibility"] * 40
                        )
                        validated_entities_analysis["entity_field_completeness"][entity_type] = completeness
                        
                    elif entity_type == "travelers" and isinstance(entity_data, dict):
                        completeness = {
                            "has_adults": "adults" in entity_data and entity_data["adults"] is not None,
                            "has_children": "children" in entity_data and entity_data["children"] is not None,
                            "has_rooms": "num_of_rooms" in entity_data and entity_data["num_of_rooms"] is not None,
                            "completeness_percentage": 0
                        }
                        completeness["completeness_percentage"] = (
                            completeness["has_adults"] * 50 + completeness["has_children"] * 25 + completeness["has_rooms"] * 25
                        )
                        validated_entities_analysis["entity_field_completeness"][entity_type] = completeness
                        
                    elif entity_type in ["dates", "locations", "activities", "preferences", "keywords"] and isinstance(entity_data, list):
                        completeness = {
                            "item_count": len(entity_data),
                            "has_items": len(entity_data) > 0,
                            "adequate_count": len(entity_data) >= 2 if entity_type == "activities" else len(entity_data) >= 1,
                            "completeness_percentage": min(100, len(entity_data) * 25) if entity_type != "activities" else min(100, len(entity_data) * 20)
                        }
                        validated_entities_analysis["entity_field_completeness"][entity_type] = completeness
                else:
                    # Entity is missing or empty
                    validated_entities_analysis["entity_field_completeness"][entity_type] = {
                        "present": False,
                        "completeness_percentage": 0
                    }
            
            # Calculate overall data completeness score
            completeness_scores = [
                field_data.get("completeness_percentage", 0) 
                for field_data in validated_entities_analysis["entity_field_completeness"].values()
            ]
            validated_entities_analysis["data_completeness_score"] = (
                sum(completeness_scores) / len(completeness_scores) if completeness_scores else 0.0
            )
            
            # Extract validation quality indicators from validation results
            if validation_results and isinstance(validation_results, dict):
                validated_entities_analysis["validation_quality_indicators"] = {
                    "overall_validation_score": validation_results.get("overall_validation_score", 0.0),
                    "validation_successful": validation_results.get("validation_successful", False),
                    "validation_rules_applied_count": len(validation_results.get("validation_rules_applied", [])),
                    "high_quality_activities": validation_results.get("activity_validation", {}).get("high_quality_activities", 0),
                    "date_validation_success_rate": validation_results.get("date_validation", {}).get("overall_date_success_rate", 0.0),
                    "validation_time_total_ms": validation_results.get("validation_time_ms", 0.0)
                }
            
            completion_tracing_time_ms = (time.time() - completion_tracing_start) * 1000
            
            completion_result = {
                **validated_entities_analysis,
                "completion_tracing_time_ms": completion_tracing_time_ms,
                "completion_tracing_successful": True,
                "validation_completion_timestamp": datetime.now().isoformat()
            }
            
            return completion_result
            
        except Exception as e:
            completion_tracing_time_ms = (time.time() - completion_tracing_start) * 1000
            return {
                "completion_tracing_time_ms": completion_tracing_time_ms,
                "completion_tracing_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="rejected_fields_analysis")
    def _trace_rejected_fields(self, raw_entities: dict, validated_entities: dict) -> dict:
        """
        Trace rejected fields and validation failures.
        
        Args:
            raw_entities: Original entities before validation
            validated_entities: Entities after validation
            
        Returns:
            dict: Rejected fields analysis
        """
        rejected_fields_start = time.time()
        
        try:
            rejected_analysis = {
                "rejected_fields": [],
                "rejected_values": {},
                "rejection_reasons": {},
                "field_rejection_count": 0,
                "value_rejection_count": 0
            }
            
            # Compare raw vs validated entities to find rejections
            if raw_entities and validated_entities:
                for field_name in raw_entities:
                    raw_value = raw_entities[field_name]
                    validated_value = validated_entities.get(field_name)
                    
                    # Check if field was completely rejected
                    if field_name not in validated_entities:
                        rejected_analysis["rejected_fields"].append(field_name)
                        rejected_analysis["rejected_values"][field_name] = raw_value
                        rejected_analysis["rejection_reasons"][field_name] = "field_completely_rejected"
                        rejected_analysis["field_rejection_count"] += 1
                        
                    # Check if field values were modified/filtered
                    elif raw_value != validated_value:
                        if isinstance(raw_value, list) and isinstance(validated_value, list):
                            # List items were filtered
                            rejected_items = [item for item in raw_value if item not in validated_value]
                            if rejected_items:
                                rejected_analysis["rejected_values"][f"{field_name}_items"] = rejected_items
                                rejected_analysis["rejection_reasons"][f"{field_name}_items"] = "list_items_filtered"
                                rejected_analysis["value_rejection_count"] += len(rejected_items)
                                
                        elif isinstance(raw_value, dict) and isinstance(validated_value, dict):
                            # Dict fields were filtered
                            rejected_dict_fields = {k: v for k, v in raw_value.items() if k not in validated_value}
                            if rejected_dict_fields:
                                rejected_analysis["rejected_values"][f"{field_name}_subfields"] = rejected_dict_fields
                                rejected_analysis["rejection_reasons"][f"{field_name}_subfields"] = "dict_fields_filtered"
                                rejected_analysis["value_rejection_count"] += len(rejected_dict_fields)
                        else:
                            # Value was completely changed
                            rejected_analysis["rejected_values"][f"{field_name}_original"] = raw_value
                            rejected_analysis["rejection_reasons"][f"{field_name}_original"] = "value_replaced"
                            rejected_analysis["value_rejection_count"] += 1
            
            # Calculate rejection metrics
            total_raw_fields = len(raw_entities) if raw_entities else 0
            rejection_rate = (rejected_analysis["field_rejection_count"] / total_raw_fields) if total_raw_fields > 0 else 0.0
            
            rejected_fields_time_ms = (time.time() - rejected_fields_start) * 1000
            
            rejected_result = {
                **rejected_analysis,
                "rejected_fields_time_ms": rejected_fields_time_ms,
                "total_raw_fields": total_raw_fields,
                "field_rejection_rate": rejection_rate,
                "rejection_analysis_successful": True,
                "has_rejections": rejected_analysis["field_rejection_count"] > 0 or rejected_analysis["value_rejection_count"] > 0
            }
            
            return rejected_result
            
        except Exception as e:
            rejected_fields_time_ms = (time.time() - rejected_fields_start) * 1000
            return {
                "rejected_fields_time_ms": rejected_fields_time_ms,
                "rejection_analysis_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }

    @traceable(run_type="tool", name="validation_error_recovery")
    def _trace_validation_error_recovery(self, validation_error: Exception, entities: dict, recovery_attempt: int = 0) -> dict:
        """
        Trace validation errors and recovery attempts.
        
        Args:
            validation_error: The validation exception that occurred
            entities: The entities that caused the validation error
            recovery_attempt: The current recovery attempt number
            
        Returns:
            dict: Validation error and recovery metadata
        """
        error_recovery_start = time.time()
        
        try:
            error_analysis = {
                "validation_error_type": type(validation_error).__name__,
                "validation_error_message": str(validation_error),
                "recovery_attempt_number": recovery_attempt,
                "error_occurred_at": datetime.now().isoformat(),
                "problematic_entities": list(entities.keys()) if entities else [],
                "error_context": {},
                "recovery_strategy": None,
                "recovery_successful": False
            }
            
            # Analyze error context based on error type
            if "ValidationError" in error_analysis["validation_error_type"]:
                # Pydantic validation error - analyze field-specific issues
                error_analysis["error_context"]["validation_type"] = "pydantic_model_validation"
                error_analysis["error_context"]["field_errors"] = []
                
                # Try to extract field-specific error information
                error_str = str(validation_error)
                if "field required" in error_str.lower():
                    error_analysis["error_context"]["error_category"] = "missing_required_fields"
                elif "invalid" in error_str.lower():
                    error_analysis["error_context"]["error_category"] = "invalid_field_values"
                else:
                    error_analysis["error_context"]["error_category"] = "general_validation_error"
                    
            elif "TypeError" in error_analysis["validation_error_type"]:
                error_analysis["error_context"]["validation_type"] = "type_mismatch"
                error_analysis["error_context"]["error_category"] = "data_type_incompatibility"
                
            elif "KeyError" in error_analysis["validation_error_type"]:
                error_analysis["error_context"]["validation_type"] = "missing_key"
                error_analysis["error_context"]["error_category"] = "required_field_missing"
                
            else:
                error_analysis["error_context"]["validation_type"] = "unknown_error"
                error_analysis["error_context"]["error_category"] = "unhandled_validation_error"
            
            # Determine recovery strategy based on error type and attempt number
            if recovery_attempt == 0:
                # First recovery attempt - try to clean/fix the data
                error_analysis["recovery_strategy"] = "data_cleaning_and_retry"
                recovered_entities = self._attempt_data_recovery(entities, error_analysis)
                
                if recovered_entities != entities:
                    error_analysis["recovery_successful"] = True
                    error_analysis["recovered_entities"] = recovered_entities
                    
            elif recovery_attempt == 1:
                # Second recovery attempt - use partial validation
                error_analysis["recovery_strategy"] = "partial_validation_fallback"
                recovered_entities = self._attempt_partial_validation_recovery(entities, error_analysis)
                
                if recovered_entities:
                    error_analysis["recovery_successful"] = True
                    error_analysis["recovered_entities"] = recovered_entities
                    
            else:
                # Final fallback - return empty or minimal entities
                error_analysis["recovery_strategy"] = "minimal_fallback"
                error_analysis["recovered_entities"] = {}
                error_analysis["recovery_successful"] = True  # Always succeeds with empty dict
            
            error_recovery_time_ms = (time.time() - error_recovery_start) * 1000
            
            error_recovery_result = {
                **error_analysis,
                "error_recovery_time_ms": error_recovery_time_ms,
                "error_recovery_tracing_successful": True
            }
            
            return error_recovery_result
            
        except Exception as e:
            error_recovery_time_ms = (time.time() - error_recovery_start) * 1000
            return {
                "error_recovery_time_ms": error_recovery_time_ms,
                "error_recovery_tracing_successful": False,
                "recovery_error_type": type(e).__name__,
                "recovery_error_message": str(e)
            }

    def _attempt_data_recovery(self, entities: dict, error_analysis: dict) -> dict:
        """Attempt to recover data by cleaning and fixing common issues."""
        try:
            recovered = entities.copy()
            
            # Clean up common data issues
            for key, value in recovered.items():
                if isinstance(value, list):
                    # Remove None values and empty strings from lists
                    recovered[key] = [item for item in value if item is not None and str(item).strip()]
                elif isinstance(value, dict):
                    # Remove None values from dictionaries
                    recovered[key] = {k: v for k, v in value.items() if v is not None}
                elif value is None or (isinstance(value, str) and not value.strip()):
                    # Remove completely empty fields
                    del recovered[key]
            
            return recovered
            
        except Exception:
            return entities

    def _attempt_partial_validation_recovery(self, entities: dict, error_analysis: dict) -> dict:
        """Attempt to recover by validating individual fields."""
        try:
            recovered = {}
            
            # Try to validate each field individually
            for key, value in entities.items():
                try:
                    if key == "budget" and isinstance(value, dict):
                        # Validate budget fields individually
                        budget = {}
                        if "amount" in value and isinstance(value["amount"], (int, float)):
                            budget["amount"] = value["amount"]
                        if "flexibility" in value and isinstance(value["flexibility"], str):
                            budget["flexibility"] = value["flexibility"]
                        if budget:
                            recovered[key] = budget
                            
                    elif key == "travelers" and isinstance(value, dict):
                        # Validate travelers fields individually
                        travelers = {}
                        if "adults" in value and isinstance(value["adults"], int):
                            travelers["adults"] = value["adults"]
                        if "children" in value and isinstance(value["children"], int):
                            travelers["children"] = value["children"]
                        if "num_of_rooms" in value and isinstance(value["num_of_rooms"], int):
                            travelers["num_of_rooms"] = value["num_of_rooms"]
                        if travelers:
                            recovered[key] = travelers
                            
                    elif isinstance(value, list):
                        # Validate list fields
                        clean_list = [item for item in value if isinstance(item, str) and item.strip()]
                        if clean_list:
                            recovered[key] = clean_list
                            
                except Exception:
                    # Skip fields that can't be individually validated
                    continue
            
            return recovered
            
        except Exception:
            return {}

    def _calculate_validation_score(self, validation_results: list) -> float:
        """Calculate overall validation score from individual validation results."""
        if not validation_results:
            return 0.0
        
        scores = []
        for result in validation_results:
            if isinstance(result, dict):
                # Extract score from different possible keys
                score = result.get("overall_activity_quality_score", 
                       result.get("validation_score", 
                       result.get("success_rate", 0.0)))
                scores.append(score)
        
        return sum(scores) / len(scores) if scores else 0.0

    @traceable(run_type="tool", name="entity_validation_analysis")
    def _analyze_extracted_entities(self, entities: dict) -> dict:
        """Analyze extracted entities with detailed validation tracing"""
        analysis_start_time = time.time()
        
        try:
            # Initialize entity analysis
            entity_analysis = {
                "entities_analyzed": True,
                "entity_types_found": [],
                "entity_completeness_score": 0.0,
                "confidence_indicators": {},
                "validation_warnings": [],
                "semantic_richness_scores": {}
            }
            
            # Analyze each entity type
            if "dates" in entities and entities["dates"]:
                dates = entities["dates"]
                entity_analysis["entity_types_found"].append("dates")
                entity_analysis["confidence_indicators"]["dates"] = {
                    "count": len(dates),
                    "has_specific_dates": any(re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', str(date)) for date in dates),
                    "has_relative_dates": any(word in str(dates).lower() for word in ["next", "this", "winter", "summer", "holiday"]),
                    "confidence_level": "high" if len(dates) > 0 else "low"
                }
            
            if "budget" in entities and entities["budget"]:
                budget = entities["budget"]
                entity_analysis["entity_types_found"].append("budget")
                budget_confidence = "high" if isinstance(budget, dict) and budget.get("amount") else "low"
                entity_analysis["confidence_indicators"]["budget"] = {
                    "has_amount": bool(budget.get("amount") if isinstance(budget, dict) else False),
                    "has_flexibility": bool(budget.get("flexibility") if isinstance(budget, dict) else False),
                    "confidence_level": budget_confidence
                }
            
            if "travelers" in entities and entities["travelers"]:
                travelers = entities["travelers"]
                entity_analysis["entity_types_found"].append("travelers")
                travelers_confidence = "high" if isinstance(travelers, dict) and (travelers.get("adults") or travelers.get("children")) else "low"
                entity_analysis["confidence_indicators"]["travelers"] = {
                    "has_adults": bool(travelers.get("adults") if isinstance(travelers, dict) else False),
                    "has_children": bool(travelers.get("children") if isinstance(travelers, dict) else False),
                    "has_rooms": bool(travelers.get("num_of_rooms") if isinstance(travelers, dict) else False),
                    "confidence_level": travelers_confidence
                }
            
            if "locations" in entities and entities["locations"]:
                locations = entities["locations"]
                entity_analysis["entity_types_found"].append("locations")
                entity_analysis["confidence_indicators"]["locations"] = {
                    "count": len(locations),
                    "has_countries": any(loc.lower() in ["egypt", "cairo", "giza", "luxor", "aswan"] for loc in locations),
                    "has_cities": len(locations) > 0,
                    "confidence_level": "high" if len(locations) > 0 else "low"
                }
            
            if "activities" in entities and entities["activities"]:
                activities = entities["activities"]
                entity_analysis["entity_types_found"].append("activities")
                
                # Analyze activity semantic richness
                semantic_scores = []
                for activity in activities:
                    if isinstance(activity, str):
                        # Score based on sentence completeness and descriptiveness
                        word_count = len(activity.split())
                        has_action_verb = any(verb in activity.lower() for verb in ["visit", "explore", "experience", "tour", "see", "enjoy", "take"])
                        has_location_context = any(loc in activity.lower() for loc in ["pyramid", "nile", "desert", "temple", "museum", "red sea"])
                        has_descriptive_words = len([word for word in activity.split() if len(word) > 5]) > 0
                        
                        semantic_score = (
                            (word_count >= 5) * 25 +  # Complete sentence
                            has_action_verb * 25 +     # Action verb present
                            has_location_context * 25 + # Location context
                            has_descriptive_words * 25  # Descriptive language
                        )
                        semantic_scores.append(semantic_score)
                
                avg_semantic_score = sum(semantic_scores) / len(semantic_scores) if semantic_scores else 0
                entity_analysis["semantic_richness_scores"]["activities"] = {
                    "average_score": avg_semantic_score,
                    "individual_scores": semantic_scores,
                    "high_quality_activities": sum(1 for score in semantic_scores if score >= 75),
                    "total_activities": len(activities)
                }
                
                entity_analysis["confidence_indicators"]["activities"] = {
                    "count": len(activities),
                    "average_semantic_richness": avg_semantic_score,
                    "confidence_level": "high" if avg_semantic_score >= 50 else "medium" if avg_semantic_score >= 25 else "low"
                }
            
            if "preferences" in entities and entities["preferences"]:
                preferences = entities["preferences"]
                entity_analysis["entity_types_found"].append("preferences")
                entity_analysis["confidence_indicators"]["preferences"] = {
                    "count": len(preferences),
                    "confidence_level": "high" if len(preferences) > 0 else "low"
                }
            
            if "keywords" in entities and entities["keywords"]:
                keywords = entities["keywords"]
                entity_analysis["entity_types_found"].append("keywords")
                entity_analysis["confidence_indicators"]["keywords"] = {
                    "count": len(keywords),
                    "confidence_level": "high" if len(keywords) > 0 else "low"
                }
            
            # Calculate overall completeness score
            expected_entity_types = ["dates", "budget", "travelers", "locations", "activities", "preferences"]
            found_types = len(entity_analysis["entity_types_found"])
            entity_analysis["entity_completeness_score"] = (found_types / len(expected_entity_types)) * 100
            
            # Generate validation warnings
            if found_types == 0:
                entity_analysis["validation_warnings"].append("no_entities_extracted")
            if "activities" not in entity_analysis["entity_types_found"]:
                entity_analysis["validation_warnings"].append("no_activities_found")
            if "locations" not in entity_analysis["entity_types_found"]:
                entity_analysis["validation_warnings"].append("no_locations_found")
            
            # Calculate analysis time
            analysis_time_ms = (time.time() - analysis_start_time) * 1000
            entity_analysis["analysis_time_ms"] = analysis_time_ms
            entity_analysis["analysis_successful"] = True
            
            return entity_analysis
            
        except Exception as e:
            analysis_time_ms = (time.time() - analysis_start_time) * 1000
            return {
                "entities_analyzed": False,
                "analysis_time_ms": analysis_time_ms,
                "analysis_successful": False,
                "error_type": type(e).__name__,
                "error_message": str(e)
            }


    @traceable(run_type="tool", name="workflow_error_recovery")
    async def _trace_workflow_error_recovery(self, error: Exception, segment: TranscriptSegment, error_tracking: dict) -> dict:
        """
        Trace workflow error recovery with comprehensive fallback behavior and retry mechanisms.
        
        This method implements error propagation tracing through the complete hierarchy,
        ensuring errors are traced with full context and recovery attempts are documented.
        
        Args:
            error: The exception that caused the workflow failure
            segment: The transcript segment being processed
            error_tracking: Current error tracking information
            
        Returns:
            dict: Recovery attempt results and metadata
        """
        recovery_start_time = time.time()
        
        try:
            # Initialize recovery metadata
            recovery_metadata = {
                "recovery_attempt_id": f"recovery_{uuid.uuid4().hex[:8]}",
                "original_error_type": type(error).__name__,
                "original_error_message": str(error),
                "recovery_start_timestamp": datetime.now().isoformat(),
                "segment_id": segment.segment_id,
                "recovery_strategies_attempted": [],
                "recovery_successful": False,
                "fallback_data_generated": False
            }
            
            # Analyze error context for recovery strategy selection
            error_context = self._analyze_error_context(error, error_tracking)
            recovery_metadata["error_context_analysis"] = error_context
            
            # Strategy 1: Retry with simplified processing
            if error_context.get("error_category") in ["timeout", "api_failure", "temporary_failure"]:
                recovery_metadata["recovery_strategies_attempted"].append("simplified_retry")
                
                try:
                    # Attempt simplified extraction with reduced timeout
                    simplified_result = await self._attempt_simplified_extraction(segment)
                    
                    if simplified_result and simplified_result.entities:
                        recovery_metadata.update({
                            "recovery_successful": True,
                            "recovery_strategy_successful": "simplified_retry",
                            "recovered_entities_count": len(simplified_result.entities),
                            "recovered_entities_keys": list(simplified_result.entities.keys())
                        })
                        
                        # Log successful recovery
                        print(f"[{self.agent_id}] Recovery successful via simplified retry for {segment.segment_id}")
                        
                        recovery_time_ms = (time.time() - recovery_start_time) * 1000
                        recovery_metadata["recovery_time_ms"] = recovery_time_ms
                        return recovery_metadata
                        
                except Exception as retry_error:
                    recovery_metadata["simplified_retry_error"] = {
                        "error_type": type(retry_error).__name__,
                        "error_message": str(retry_error)
                    }
            
            # Strategy 2: Fallback to minimal extraction
            recovery_metadata["recovery_strategies_attempted"].append("minimal_fallback")
            
            try:
                fallback_result = await self._generate_fallback_extraction(segment, error_context)
                
                if fallback_result:
                    recovery_metadata.update({
                        "recovery_successful": True,
                        "recovery_strategy_successful": "minimal_fallback",
                        "fallback_data_generated": True,
                        "fallback_entities_count": len(fallback_result.entities) if fallback_result.entities else 0,
                        "fallback_confidence": "low"
                    })
                    
                    # Log fallback recovery
                    print(f"[{self.agent_id}] Recovery successful via minimal fallback for {segment.segment_id}")
                    
            except Exception as fallback_error:
                recovery_metadata["minimal_fallback_error"] = {
                    "error_type": type(fallback_error).__name__,
                    "error_message": str(fallback_error)
                }
            
            # Strategy 3: Circuit breaker pattern - trace failure state
            if not recovery_metadata["recovery_successful"]:
                recovery_metadata["recovery_strategies_attempted"].append("circuit_breaker_activation")
                
                # Trace circuit breaker state
                circuit_breaker_state = self._trace_circuit_breaker_activation(error, segment, error_tracking)
                recovery_metadata["circuit_breaker_state"] = circuit_breaker_state
                
                # Generate empty extraction as final fallback
                empty_extraction = RawExtraction(
                    extraction_id=f"fallback_{uuid.uuid4().hex[:8]}",
                    segment_id=segment.segment_id,
                    timestamp=datetime.now(),
                    raw_text=segment.text,
                    entities={},
                    processing_time_ms=(time.time() - recovery_start_time) * 1000
                )
                
                recovery_metadata.update({
                    "recovery_successful": True,  # Always succeeds with empty result
                    "recovery_strategy_successful": "circuit_breaker_empty_fallback",
                    "fallback_data_generated": True,
                    "fallback_entities_count": 0,
                    "fallback_confidence": "none"
                })
            
            # Calculate final recovery metrics
            recovery_time_ms = (time.time() - recovery_start_time) * 1000
            recovery_metadata.update({
                "recovery_time_ms": recovery_time_ms,
                "recovery_completion_timestamp": datetime.now().isoformat(),
                "total_strategies_attempted": len(recovery_metadata["recovery_strategies_attempted"]),
                "recovery_efficiency_score": min(100, 2000 / recovery_time_ms) if recovery_time_ms > 0 else 100
            })
            
            return recovery_metadata
            
        except Exception as recovery_error:
            # Recovery itself failed - trace this critical situation
            recovery_time_ms = (time.time() - recovery_start_time) * 1000
            
            critical_recovery_failure = {
                "recovery_attempt_id": f"failed_recovery_{uuid.uuid4().hex[:8]}",
                "recovery_time_ms": recovery_time_ms,
                "recovery_successful": False,
                "recovery_critical_failure": True,
                "recovery_error_type": type(recovery_error).__name__,
                "recovery_error_message": str(recovery_error),
                "original_error_type": type(error).__name__,
                "original_error_message": str(error),
                "recovery_failure_timestamp": datetime.now().isoformat()
            }
            
            # Log critical recovery failure
            print(f"[{self.agent_id}] Critical: Recovery itself failed for {segment.segment_id}: {recovery_error}")
            
            return critical_recovery_failure

    @traceable(run_type="tool", name="error_context_analysis")
    def _analyze_error_context(self, error: Exception, error_tracking: dict) -> dict:
        """Analyze error context to determine appropriate recovery strategy."""
        try:
            error_type = type(error).__name__
            error_message = str(error).lower()
            
            # Categorize error types for recovery strategy selection
            if "timeout" in error_message or error_type == "TimeoutError":
                error_category = "timeout"
                recovery_priority = "high"
                suggested_strategy = "simplified_retry"
                
            elif "connection" in error_message or "network" in error_message:
                error_category = "api_failure"
                recovery_priority = "high"
                suggested_strategy = "simplified_retry"
                
            elif "validation" in error_message or error_type == "ValidationError":
                error_category = "validation_failure"
                recovery_priority = "medium"
                suggested_strategy = "minimal_fallback"
                
            elif "json" in error_message or "parse" in error_message:
                error_category = "parsing_failure"
                recovery_priority = "medium"
                suggested_strategy = "minimal_fallback"
                
            elif "memory" in error_message or "resource" in error_message:
                error_category = "resource_exhaustion"
                recovery_priority = "low"
                suggested_strategy = "circuit_breaker"
                
            else:
                error_category = "unknown_failure"
                recovery_priority = "low"
                suggested_strategy = "minimal_fallback"
            
            # Analyze error frequency from tracking
            error_frequency = len(error_tracking.get("errors_encountered", []))
            is_recurring = error_frequency > 2
            
            context_analysis = {
                "error_category": error_category,
                "recovery_priority": recovery_priority,
                "suggested_strategy": suggested_strategy,
                "error_frequency": error_frequency,
                "is_recurring_error": is_recurring,
                "error_analysis_timestamp": datetime.now().isoformat(),
                "context_analysis_successful": True
            }
            
            return context_analysis
            
        except Exception as analysis_error:
            return {
                "error_category": "analysis_failed",
                "recovery_priority": "low",
                "suggested_strategy": "minimal_fallback",
                "context_analysis_successful": False,
                "analysis_error": str(analysis_error)
            }

    @traceable(run_type="tool", name="simplified_extraction_retry")
    async def _attempt_simplified_extraction(self, segment: TranscriptSegment) -> RawExtraction:
        """Attempt simplified extraction with reduced complexity and timeout."""
        simplified_start = time.time()
        
        try:
            # Use a much simpler prompt for retry
            simple_prompt = """Extract basic travel info from this text. Return JSON only:
            {"locations": ["city names"], "activities": ["what they want to do"], "dates": ["when"]}
            
            Text: """ + segment.text[:200]  # Truncate for simplicity
            
            # Simplified LLM call with shorter timeout
            messages = [{"role": "user", "content": simple_prompt}]
            
            response_obj = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(
                    None, lambda: self.client.chat(messages=messages)
                ),
                timeout=5  # Reduced timeout
            )
            
            # Extract content
            content = None
            if isinstance(response_obj, str):
                content = response_obj
            else:
                try:
                    content = response_obj.get("message", {}).get("content")
                except Exception:
                    message_obj = getattr(response_obj, "message", None)
                    if message_obj is not None:
                        content = getattr(message_obj, "content", None)
            
            # Simple JSON parsing
            entities = {}
            if content:
                try:
                    entities = json.loads(content.strip())
                except json.JSONDecodeError:
                    # Extract any JSON-like content
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        try:
                            entities = json.loads(json_match.group())
                        except:
                            entities = {}
            
            processing_time = (time.time() - simplified_start) * 1000
            
            simplified_extraction = RawExtraction(
                extraction_id=f"simplified_{uuid.uuid4().hex[:8]}",
                segment_id=segment.segment_id,
                timestamp=datetime.now(),
                raw_text=segment.text,
                entities=entities,
                processing_time_ms=processing_time
            )
            
            return simplified_extraction
            
        except Exception as e:
            print(f"[{self.agent_id}] Simplified extraction also failed: {e}")
            return None

    @traceable(run_type="tool", name="fallback_extraction_generation")
    async def _generate_fallback_extraction(self, segment: TranscriptSegment, error_context: dict) -> RawExtraction:
        """Generate minimal fallback extraction based on text analysis."""
        fallback_start = time.time()
        
        try:
            # Basic text analysis for fallback entities
            text_lower = segment.text.lower()
            fallback_entities = {}
            
            # Extract locations using simple keyword matching
            egyptian_locations = ["cairo", "giza", "luxor", "aswan", "alexandria", "pyramid", "nile"]
            found_locations = [loc for loc in egyptian_locations if loc in text_lower]
            if found_locations:
                fallback_entities["locations"] = found_locations
            
            # Extract basic activities using keyword matching
            activity_keywords = ["visit", "see", "tour", "explore", "experience", "go to"]
            activities = []
            for keyword in activity_keywords:
                if keyword in text_lower:
                    # Create basic activity sentence
                    activities.append(f"Visit and explore Egyptian attractions")
                    break
            if activities:
                fallback_entities["activities"] = activities
            
            # Extract date-like patterns
            import re
            date_patterns = re.findall(r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b\w+\s+\d{4}\b', segment.text)
            if date_patterns:
                fallback_entities["dates"] = date_patterns
            
            # Extract number patterns for budget/travelers
            number_patterns = re.findall(r'\b\d+\b', segment.text)
            if number_patterns:
                # Assume first reasonable number might be budget or traveler count
                for num_str in number_patterns:
                    num = int(num_str)
                    if 100 <= num <= 10000:  # Likely budget
                        fallback_entities["budget"] = {"amount": num, "flexibility": "moderate"}
                        break
                    elif 1 <= num <= 10:  # Likely traveler count
                        fallback_entities["travelers"] = {"adults": num}
                        break
            
            processing_time = (time.time() - fallback_start) * 1000
            
            fallback_extraction = RawExtraction(
                extraction_id=f"fallback_{uuid.uuid4().hex[:8]}",
                segment_id=segment.segment_id,
                timestamp=datetime.now(),
                raw_text=segment.text,
                entities=fallback_entities,
                processing_time_ms=processing_time
            )
            
            return fallback_extraction
            
        except Exception as e:
            print(f"[{self.agent_id}] Fallback extraction failed: {e}")
            return None

    @traceable(run_type="tool", name="circuit_breaker_activation")
    def _trace_circuit_breaker_activation(self, error: Exception, segment: TranscriptSegment, error_tracking: dict) -> dict:
        """Trace circuit breaker activation and failure state management."""
        try:
            circuit_breaker_state = {
                "activation_timestamp": datetime.now().isoformat(),
                "trigger_error_type": type(error).__name__,
                "trigger_error_message": str(error),
                "segment_id": segment.segment_id,
                "failure_count": len(error_tracking.get("errors_encountered", [])),
                "circuit_state": "open",  # Circuit is open, blocking further attempts
                "recovery_window_seconds": 60,  # Time before allowing retry
                "fallback_strategy": "empty_response",
                "circuit_breaker_active": True
            }
            
            # Determine circuit breaker behavior based on error frequency
            if circuit_breaker_state["failure_count"] >= 3:
                circuit_breaker_state["circuit_state"] = "open"
                circuit_breaker_state["recovery_window_seconds"] = 300  # 5 minutes
            elif circuit_breaker_state["failure_count"] >= 2:
                circuit_breaker_state["circuit_state"] = "half_open"
                circuit_breaker_state["recovery_window_seconds"] = 60  # 1 minute
            else:
                circuit_breaker_state["circuit_state"] = "closed"
                circuit_breaker_state["recovery_window_seconds"] = 0
            
            return circuit_breaker_state
            
        except Exception as cb_error:
            return {
                "circuit_breaker_active": False,
                "circuit_breaker_error": str(cb_error),
                "fallback_strategy": "empty_response"
            }

    async def _publish(self, extraction: RawExtraction):
        """Publish to Redis event bus"""
        try:
            await self.redis.publish(
                self.config.EXTRACTION_TOPIC,
                extraction.model_dump_json()
            )
            print(f"  → Published to Profile Agent")
        except Exception as e:
            print(f"❌ Failed to publish extraction: {e}")


