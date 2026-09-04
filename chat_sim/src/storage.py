import json
import os
import random
from .models import Character
from .config import DATA_FILE

def load_characters():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            all_characters = [Character.from_dict(c) for c in data]
            return all_characters
    except (json.JSONDecodeError, IOError):
        return []

def save_characters(characters):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump([c.to_dict() for c in characters], f, indent=2)