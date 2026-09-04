import pygame
from src.app import App
from src.llm_client import init_ai

if __name__ == "__main__":
    # Initialize the brain before the GUI (or move this into App thread if you want a loading screen)
    print("Initializing System...")
    init_ai()
    
    pygame.init()
    app = App()
    app.run()