# engine/ai/llm_interface.py
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.pipelines import pipeline
import json
import os
import sys
from typing import Dict, Any

class LLMInterface:
    """
    A class to load an LLM and generate text from prompts.
    Manages a single instance of the model and tokenizer.
    """
    def __init__(self, model_id="microsoft/Phi-4-mini-instruct"):
    # def __init__(self, model_id="microsoft/Phi-3.5-mini"):
        self.model_id = model_id
        self.pipe = None
        self._load_model()
        self.prompts = self._load_prompts()

    def _load_model(self):
        """
        Loads the model and tokenizer into memory. This is a one-time,
        resource-intensive operation.
        """
        # loading the model takes several seconds, so disabling for now until we're ready to work more with ai functionality
        return
    
        print(f"Loading LLM: {self.model_id}...")
        print("This may take a while and require a significant download on the first run.")
        
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"Using device: {device.upper()}")

            model = AutoModelForCausalLM.from_pretrained(
                self.model_id, device_map=device, torch_dtype="auto", trust_remote_code=True
            )
            tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            
            self.pipe = pipeline("text-generation", model=model, tokenizer=tokenizer)
            print("--- LLM Model Loaded Successfully! ---")
        except Exception as e:
            print(f"\n--- FATAL MODEL LOADING ERROR ---", file=sys.stderr)
            print(f"Could not load the model: {e}", file=sys.stderr)
            print("Please check your dependencies (transformers, torch, accelerate) and internet connection.", file=sys.stderr)
            self.pipe = None # Ensure pipe is None on failure

    def _load_prompts(self) -> Dict[str, Any]:
        """Loads prompt templates from the prompts.json file."""
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts.json")
        try:
            with open(prompt_path, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Warning: Could not load prompts from {prompt_path}: {e}")
            return {}

    def generate(self, prompt_key: str, replacements: Dict[str, str], max_new_tokens=50) -> str:
        """
        Generates text using a prompt template and the loaded pipeline.
        """
        if not self.pipe:
            return "Error: LLM pipeline is not available."

        base_prompt = self.prompts.get(prompt_key)
        if not base_prompt:
            return f"Error: Prompt key '{prompt_key}' not found."

        try:
            system_prompt = base_prompt.get("system", "")
            user_prompt_template = base_prompt.get("user", "")
            formatted_user_prompt = user_prompt_template.format(**replacements)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": formatted_user_prompt},
            ]
            
            generation_args = {
                "max_new_tokens": max_new_tokens, "return_full_text": False,
                "temperature": 0.8, "top_p": 0.95, "do_sample": True,
            }

            raw_output = self.pipe(messages, **generation_args)
            if raw_output is None: return "Error: Generation pipeline returned no output."

            output_list = list(raw_output)
            
            if output_list and isinstance(output_list[0], dict) and "generated_text" in output_list[0]:
                return str(output_list[0]["generated_text"]).strip() # type: ignore
            else:
                print(f"Warning: Unexpected LLM output format: {output_list}")
                return "Error: Generation failed to produce expected output format."
        except Exception as e:
            return f"An unexpected error occurred during generation: {e}"