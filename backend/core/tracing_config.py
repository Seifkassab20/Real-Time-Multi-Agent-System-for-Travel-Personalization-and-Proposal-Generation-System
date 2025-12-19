import os
import logging
from dotenv import load_dotenv
from langsmith import traceable


load_dotenv()
logger = logging.getLogger("langsmith_tracing")
IS_TRACING_ENABLED = os.getenv("LANGSMITH_TRACING_V2", "").lower() in ("true", "1", "yes")
PROJECT_NAME ="multi-agent-travel-recommendation-engine"
def get_metadata(component: str, **kwargs) -> dict:
    """Standardized metadata for any @traceable function."""
    return {"component": component, "project": PROJECT_NAME, **kwargs}

@traceable(run_type="tool")
def trace_service_health(service_name: str, url: str):
    import requests
    try:
        response = requests.get(url, timeout=5)
        return {"service": service_name, "ok": response.status_code == 200}
    except Exception as e:
        return {"service": service_name, "ok": False, "error": str(e)}

def init_tracing():
    status = "enabled" if IS_TRACING_ENABLED else "disabled"
    logger.info(f"LangSmith tracing is {status} for project: {PROJECT_NAME}")
    return IS_TRACING_ENABLED

init_tracing()