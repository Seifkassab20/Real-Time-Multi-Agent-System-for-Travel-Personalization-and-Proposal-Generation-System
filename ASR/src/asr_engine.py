import os
from dotenv import load_dotenv
from transformers import AutoProcessor, SeamlessM4Tv2Model
from huggingface_hub import snapshot_download

load_dotenv()
DEVICE = os.getenv("DEVICE")
cache_dir = os.getenv("cache_dir")
def ensure_model_downloaded(model_name: str, cache_dir: str | None = None ) -> str:
    """Download model with progress via huggingface_hub."""
    print(f"[model] Ensuring model {model_name} is available locally...")
    repo_dir = snapshot_download(repo_id=model_name, cache_dir=cache_dir)
    print(f"[model] ✓ Model available at: {repo_dir}")
    return repo_dir


class SeamlessModel:
    """One-shot SeamlessM4Tv2 transcriber with strict preprocessing."""

    def __init__(
        self,
        model_name: str = "facebook/seamless-m4t-v2-large",
        cache_dir: str | None = None,
    ):
        """
        Initialize the model.
        
        Args:
            model_name: HuggingFace model ID
            device: -1 for CPU, >=0 for GPU device ID
            cache_dir: Optional HF cache directory
        """
        print("[Seamless] Loading SeamlessM4T v2 model...")
        self.model_name = model_name
        self.device = DEVICE
        self.cache_dir = cache_dir
        self.loaded = False
        self.processor = None
        self.model = None

        self._load()

    def _load(self) -> None:
        """Load model with progress."""
        ensure_model_downloaded(self.model_name, cache_dir=self.cache_dir)
        print(f"[model] Loading processor & model (device={DEVICE})...")
        self.processor = AutoProcessor.from_pretrained( self.model_name, cache_dir=self.cache_dir, use_fast=False
        )
        self.model = SeamlessM4Tv2Model.from_pretrained(self.model_name, cache_dir=self.cache_dir, device_map="cpu"
        )
        self.model.to(self.device)
        self.loaded = True
        print("[Seamless] ✓ Model loaded successfully.")
