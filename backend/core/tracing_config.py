import os
import logging
from typing import Optional
from dotenv import load_dotenv
from langsmith import traceable

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class TracingConfig:
    """Configuration class for LangSmith tracing."""
    
    def __init__(self):
        """Initialize tracing configuration from environment variables."""
        self.tracing_enabled = self._get_bool_env("LANGSMITH_TRACING_V2", False)
        self.endpoint = os.getenv("LANGSMITH_ENDPOINT")
        self.api_key = os.getenv("LANGSMITH_API_KEY")
        self.project = os.getenv("LANGSMITH_PROJECT")
        
        # Validate configuration
        self._validate_config()
        
    def _get_bool_env(self, key: str, default: bool = False) -> bool:
        """Get boolean value from environment variable."""
        value = os.getenv(key, "").lower()
        return value in ("true", "1", "yes", "on")
    
    def _validate_config(self) -> None:
        """Validate tracing configuration."""
        if self.tracing_enabled:
            if not self.api_key:
                logger.warning(
                    "LangSmith tracing is enabled but LANGSMITH_API_KEY is not set. "
                    "Tracing will be disabled."
                )
                self.tracing_enabled = False
            else:
                logger.info(f"LangSmith tracing enabled for project: {self.project}")
        else:
            logger.info("LangSmith tracing is disabled")
    
    def is_enabled(self) -> bool:
        """Check if tracing is enabled and properly configured."""
        return self.tracing_enabled and bool(self.api_key)
    
    def get_environment_vars(self) -> dict:
        """Get environment variables for LangSmith configuration."""
        if not self.is_enabled():
            return {}
            
        return {
            "LANGSMITH_TRACING_V2": "true",
            "LANGSMITH_ENDPOINT": self.endpoint,
            "LANGSMITH_API_KEY": self.api_key,
            "LANGSMITH_PROJECT": self.project
        }

# Global tracing configuration instance
tracing_config = TracingConfig()

def setup_tracing() -> bool:
    """
    Set up LangSmith tracing for the application.
    
    Returns:
        bool: True if tracing was successfully configured, False otherwise.
    """
    if not tracing_config.is_enabled():
        logger.info("Tracing setup skipped - tracing is disabled or misconfigured")
        return False
    
    try:
        # Set environment variables for LangSmith
        env_vars = tracing_config.get_environment_vars()
        for key, value in env_vars.items():
            os.environ[key] = value
        
        logger.info(
            f"LangSmith tracing configured successfully. "
            f"Project: {tracing_config.project}, "
            f"Endpoint: {tracing_config.endpoint}"
        )
        return True
        
    except Exception as e:
        logger.error(f"Failed to setup LangSmith tracing: {e}")
        return False

def get_trace_metadata(component: str, **kwargs) -> dict:
    """
    Generate standardized metadata for traces.
    
    Args:
        component: Name of the component being traced
        **kwargs: Additional metadata fields
        
    Returns:
        dict: Standardized metadata dictionary
    """
    metadata = {
        "component": component,
        "project": tracing_config.project,
        "tracing_enabled": tracing_config.is_enabled()
    }
    metadata.update(kwargs)
    return metadata

def is_tracing_enabled() -> bool:
    """Check if tracing is enabled."""
    return tracing_config.is_enabled()

@traceable(run_type="tool", name="file_operations")
def trace_file_operation(file_path: str, operation_type: str, **kwargs) -> dict:
    """
    Trace file operations with comprehensive metadata.
    
    Args:
        file_path: Path to the file being operated on
        operation_type: Type of operation (exists_check, access_check, size_check, etc.)
        **kwargs: Additional operation-specific metadata
        
    Returns:
        dict: Operation result with metadata
    """
    import os
    import stat
    import time
    
    operation_start_time = time.time()
    
    # Basic file information
    file_metadata = {
        "file_path": file_path,
        "operation_type": operation_type,
        "operation_timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
    }
    
    try:
        # Check if file exists
        file_exists = os.path.exists(file_path)
        file_metadata["file_exists"] = file_exists
        
        if file_exists:
            # Get file stats
            file_stats = os.stat(file_path)
            file_metadata.update({
                "file_size_bytes": file_stats.st_size,
                "file_size_mb": round(file_stats.st_size / (1024 * 1024), 3),
                "is_file": os.path.isfile(file_path),
                "is_directory": os.path.isdir(file_path),
                "last_modified": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stats.st_mtime)),
                "creation_time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(file_stats.st_ctime)),
            })
            
            # Check permissions
            file_metadata.update({
                "readable": os.access(file_path, os.R_OK),
                "writable": os.access(file_path, os.W_OK),
                "executable": os.access(file_path, os.X_OK),
                "file_mode": oct(file_stats.st_mode)
            })
        else:
            file_metadata.update({
                "file_size_bytes": None,
                "file_size_mb": None,
                "is_file": False,
                "is_directory": False,
                "readable": False,
                "writable": False,
                "executable": False,
                "error_reason": "file_not_found"
            })
        
        # Add operation-specific metadata
        file_metadata.update(kwargs)
        
        # Calculate operation time
        operation_time = (time.time() - operation_start_time) * 1000
        file_metadata["operation_time_ms"] = round(operation_time, 3)
        file_metadata["operation_successful"] = True
        
        return file_metadata
        
    except Exception as e:
        operation_time = (time.time() - operation_start_time) * 1000
        file_metadata.update({
            "operation_successful": False,
            "operation_time_ms": round(operation_time, 3),
            "error_type": type(e).__name__,
            "error_message": str(e)
        })
        
        logger.error(f"File operation error for {file_path}: {e}")
        return file_metadata

@traceable(run_type="tool", name="external_service_check")
def trace_external_service_connection(service_name: str, host: str, **kwargs) -> dict:
    """
    Trace external service connections and health checks.
    
    Args:
        service_name: Name of the external service (e.g., "ollama", "redis")
        host: Host URL or connection string
        **kwargs: Additional service-specific metadata
        
    Returns:
        dict: Connection result with metadata
    """
    import time
    import requests
    from urllib.parse import urlparse
    
    connection_start_time = time.time()
    
    # Basic service information
    service_metadata = {
        "service_name": service_name,
        "host": host,
        "connection_timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
    }
    
    try:
        # Parse host URL
        parsed_url = urlparse(host)
        service_metadata.update({
            "protocol": parsed_url.scheme,
            "hostname": parsed_url.hostname,
            "port": parsed_url.port,
            "path": parsed_url.path
        })
        
        # Perform service-specific health check
        if service_name.lower() == "ollama":
            # Check Ollama service availability
            health_url = f"{host.rstrip('/')}/api/tags"
            response = requests.get(health_url, timeout=5)
            
            service_metadata.update({
                "health_check_url": health_url,
                "http_status_code": response.status_code,
                "service_available": response.status_code == 200,
                "response_time_ms": round((time.time() - connection_start_time) * 1000, 3)
            })
            
            if response.status_code == 200:
                try:
                    models_data = response.json()
                    available_models = [model.get('name', 'unknown') for model in models_data.get('models', [])]
                    service_metadata.update({
                        "available_models": available_models,
                        "model_count": len(available_models)
                    })
                except Exception as e:
                    service_metadata["model_parsing_error"] = str(e)
            else:
                service_metadata["error_reason"] = f"HTTP {response.status_code}"
        
        else:
            # Generic service check - try basic HTTP request
            try:
                response = requests.get(host, timeout=5)
                service_metadata.update({
                    "http_status_code": response.status_code,
                    "service_available": response.status_code < 400,
                    "response_time_ms": round((time.time() - connection_start_time) * 1000, 3)
                })
            except requests.exceptions.RequestException as e:
                service_metadata.update({
                    "service_available": False,
                    "connection_error": str(e),
                    "response_time_ms": round((time.time() - connection_start_time) * 1000, 3)
                })
        
        # Add additional metadata
        service_metadata.update(kwargs)
        service_metadata["connection_successful"] = service_metadata.get("service_available", False)
        
        return service_metadata
        
    except Exception as e:
        connection_time = (time.time() - connection_start_time) * 1000
        service_metadata.update({
            "connection_successful": False,
            "service_available": False,
            "connection_time_ms": round(connection_time, 3),
            "error_type": type(e).__name__,
            "error_message": str(e)
        })
        
        logger.error(f"External service connection error for {service_name} at {host}: {e}")
        return service_metadata

@traceable(run_type="tool", name="cleanup_operations")
def trace_cleanup_operation(cleanup_type: str, resource_details: dict, **kwargs) -> dict:
    """
    Trace cleanup and resource deallocation operations.
    
    Args:
        cleanup_type: Type of cleanup (mps_cache, memory_cleanup, model_unload, etc.)
        resource_details: Details about resources being cleaned up
        **kwargs: Additional cleanup-specific metadata
        
    Returns:
        dict: Cleanup result with metadata
    """
    import time
    import torch
    
    cleanup_start_time = time.time()
    
    # Basic cleanup information
    cleanup_metadata = {
        "cleanup_type": cleanup_type,
        "cleanup_timestamp": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()),
        "resource_details": resource_details
    }
    
    try:
        # Perform cleanup-specific operations and gather metrics
        if cleanup_type == "mps_cache":
            # Get memory info before cleanup
            if torch.backends.mps.is_available():
                try:
                    # MPS doesn't have direct memory stats, but we can track the operation
                    torch.mps.empty_cache()
                    cleanup_metadata.update({
                        "mps_available": True,
                        "cache_cleared": True,
                        "cleanup_method": "torch.mps.empty_cache()"
                    })
                except Exception as e:
                    cleanup_metadata.update({
                        "mps_available": True,
                        "cache_cleared": False,
                        "cleanup_error": str(e)
                    })
            else:
                cleanup_metadata.update({
                    "mps_available": False,
                    "cache_cleared": False,
                    "skip_reason": "MPS not available"
                })
        
        elif cleanup_type == "cuda_cache":
            if torch.cuda.is_available():
                memory_before = torch.cuda.memory_allocated()
                torch.cuda.empty_cache()
                memory_after = torch.cuda.memory_allocated()
                cleanup_metadata.update({
                    "cuda_available": True,
                    "memory_before_mb": round(memory_before / (1024 * 1024), 2),
                    "memory_after_mb": round(memory_after / (1024 * 1024), 2),
                    "memory_freed_mb": round((memory_before - memory_after) / (1024 * 1024), 2),
                    "cache_cleared": True
                })
            else:
                cleanup_metadata.update({
                    "cuda_available": False,
                    "cache_cleared": False,
                    "skip_reason": "CUDA not available"
                })
        
        elif cleanup_type == "general_memory":
            # General memory cleanup
            import gc
            collected = gc.collect()
            cleanup_metadata.update({
                "garbage_collected": True,
                "objects_collected": collected,
                "cleanup_method": "gc.collect()"
            })
        
        # Add additional metadata
        cleanup_metadata.update(kwargs)
        
        # Calculate cleanup time
        cleanup_time = (time.time() - cleanup_start_time) * 1000
        cleanup_metadata.update({
            "cleanup_time_ms": round(cleanup_time, 3),
            "cleanup_successful": True
        })
        
        return cleanup_metadata
        
    except Exception as e:
        cleanup_time = (time.time() - cleanup_start_time) * 1000
        cleanup_metadata.update({
            "cleanup_successful": False,
            "cleanup_time_ms": round(cleanup_time, 3),
            "error_type": type(e).__name__,
            "error_message": str(e)
        })
        
        logger.error(f"Cleanup operation error for {cleanup_type}: {e}")
        return cleanup_metadata