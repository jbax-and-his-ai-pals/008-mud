from dataclasses import dataclass, asdict, field
import time

@dataclass
class Character:
    name: str
    prompt: str
    # Runtime stats (not saved to JSON)
    messages_sent: int = field(default=0, metadata={'exclude': True})
    color: tuple = field(default=(0,0,0), metadata={'exclude': True})

    def to_dict(self):
        # We only save name/prompt, ignoring runtime stats
        return {'name': self.name, 'prompt': self.prompt}

    @staticmethod
    def from_dict(data):
        return Character(name=data['name'], prompt=data['prompt'])

@dataclass
class ChatMessage:
    sender: str
    text: str
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()