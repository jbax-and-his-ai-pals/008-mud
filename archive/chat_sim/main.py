import pygame
from archive.chat_sim.src.app import App
from archive.chat_sim.src.llm_client import init_ai

if __name__ == "__main__":
    # Initialize the brain before the GUI (or move this into App thread if you want a loading screen)
    print("Initializing System...")
    init_ai()
    
    pygame.init()
    app = App()
    app.run()