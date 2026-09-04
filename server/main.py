# main.py
import argparse
import os
import sys

# Ensure the current directory is in sys.path so 'engine' is found
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine.config import DEFAULT_SAVE_FILE, SAVE_GAME_DIR
from engine.core.game_manager import GameManager
# This triggers the engine/commands/__init__.py logic
import engine.commands 

def main():
    print(f"Save Directory: {SAVE_GAME_DIR}")

    parser = argparse.ArgumentParser(description='Pygame MUD Game')
    parser.add_argument('--content-set', required=True,
                        help='Path to the required content-set package or manifest')
    parser.add_argument('--save', '-s', type=str, default=DEFAULT_SAVE_FILE,
                        help='Save game file to load/save (default: default_save.json)')
    args = parser.parse_args()

    os.makedirs(SAVE_GAME_DIR, exist_ok=True)
    game = GameManager(args.content_set, args.save)
    game.run()

if __name__ == "__main__":
    main()
