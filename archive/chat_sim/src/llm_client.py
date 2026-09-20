import torch
import time
from transformers import AutoModelForCausalLM, AutoTokenizer
from .config import LLM_MODEL_ID, DEVICE, MAX_NEW_TOKENS

_model = None
_tokenizer = None

def init_ai():
    global _model, _tokenizer
    print(f"--- [SYSTEM] Loading AI Model ({LLM_MODEL_ID})... ---")
    
    try:
        _tokenizer = AutoTokenizer.from_pretrained(LLM_MODEL_ID)
        _model = AutoModelForCausalLM.from_pretrained(
            LLM_MODEL_ID, 
            trust_remote_code=False
        ).to(torch.device('cuda'))
        if DEVICE == "cpu":
            _model.to("cpu")
            print("Running on cpu. Slower!")
            
        print("--- [SYSTEM] Model Loaded successfully. ---")
    except Exception as e:
        print(f"!!! [ERROR] FAILED to load AI model: {e}")

def generate_response(character, history):
    global _model, _tokenizer
    
    if _model is None or _tokenizer is None:
        print("!!! [ERROR] Model not loaded.")
        return "[System Error: Brain missing]"

    print(f"\n=== [TURN] {character.name} is thinking... ===")
    start_time = time.time()

    # 1. Format History
    chat_log = ""
    for msg in history:
        chat_log += f"{msg.sender}: {msg.text}\n"

    # 2. Construct Messages
    # We log the prompt components separately so they are easy to read
    system_prompt = (
        f"You are a user in an online chatroom named {character.name}. "
        "Your job is to pay attention to and then continue the conversation that's happening. "
        "If no conversation exists, start one. "
        "Don't just say something generic. Focus on the conversation. "
        "Keep your response short, casual, and text-only (no actions like *waves*). "
        "Do not prefix your response with your name. "
        f"Form a complete and coherent phrase within a {MAX_NEW_TOKENS - 5} token limit. "
        "Stop immediately after this personality has spoken. "
        "Your response should not contain previous conversation."
        f"Your personality is: {character.prompt}. "
    )
    
    user_prompt = f"Here is the recent chat conversation:\n{chat_log}\n\nRespond as {character.name}:"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    print(f"--- [PROMPT] System: {character.prompt}...")
    print(f"--- [PROMPT] Context: {len(history)} previous messages.")

    # 3. Tokenize
    input_ids = _tokenizer.apply_chat_template(
        messages, 
        add_generation_prompt=True, 
        return_tensors="pt"
    ).to(_model.device)

    terminators = [
        _tokenizer.eos_token_id,
        _tokenizer.convert_tokens_to_ids("<|endoftext|>")
    ]

    # 4. Generate
    outputs = _model.generate(
        input_ids,
        max_new_tokens=MAX_NEW_TOKENS,
        eos_token_id=terminators,
        do_sample=True,
        temperature=1.2,
        top_p=0.9,
    )

    # 5. Decode & Clean
    response_tokens = outputs[0][input_ids.shape[-1]:]
    raw_text = _tokenizer.decode(response_tokens, skip_special_tokens=True)
    
    cleaned_text = raw_text.replace(f"{character.name}:", "").strip()
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"--- [RAW OUTPUT] '{raw_text}'")
    print(f"--- [FINAL TEXT] '{cleaned_text}'")
    print(f"--- [STATS] Time: {duration:.2f}s | Device: {DEVICE}")
    print("==========================================\n")

    return cleaned_text