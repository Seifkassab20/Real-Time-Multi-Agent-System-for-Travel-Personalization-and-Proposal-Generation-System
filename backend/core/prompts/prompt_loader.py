from pathlib import Path
import yaml

class PromptLoader:
    @staticmethod
    def load_prompt(relative_path: str) -> str:
        """
        Loads the 'SYSTEM_PROMPT' string from a YAML file using pathlib.
        """
        # 1. Get the folder where THIS script lives
        # .resolve() fixes symlinks and ensures absolute path
        # .parent gets the directory, not the file itself
        base_path = Path(__file__).resolve().parent
        
        # 2. Join paths using the / operator (Clean!)
        file_path = base_path / relative_path

        # 3. Check existence
        if not file_path.exists():
            raise FileNotFoundError(f"❌ Prompt file missing: {file_path}")

        # 4. Open and Load
        # pathlib handles the opening context cleanly
        with file_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        # 5. Extract Data
        prompt_template = data.get("SYSTEM_PROMPT")
        
        if not prompt_template:
            raise ValueError(f"❌ key 'SYSTEM_PROMPT' missing in {file_path}")
            
        return prompt_template