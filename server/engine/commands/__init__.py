# engine/commands/__init__.py
"""
Commands package initializer.
"""
import os
import importlib
from .movement import register_movement_commands
from engine.utils.logger import Logger

# Get the directory of this file
package_dir = os.path.dirname(__file__)
package_name = __name__

Logger.info("Commands", f"Loading Command Modules from '{package_name}'")

for item in os.listdir(package_dir):
    item_path = os.path.join(package_dir, item)
    
    # Case 1: Standard .py files
    if os.path.isfile(item_path) and item.endswith(".py") and not item.startswith("__"):
        module_name = item[:-3]
        try:
            # The '.' indicates a relative import within 'engine.commands'
            importlib.import_module(f".{module_name}", package=package_name)
            Logger.debug("Commands", f"Loaded module: {module_name}")
        except ImportError as e:
            Logger.error("Commands", f"FAILED to load module '{module_name}': {e}")

    # Case 2: Sub-packages (e.g., interaction/)
    elif os.path.isdir(item_path) and not item.startswith("__"):
        if os.path.exists(os.path.join(item_path, "__init__.py")):
            try:
                importlib.import_module(f".{item}", package=package_name)
                Logger.debug("Commands", f"Loaded package: {item}")
            except ImportError as e:
                Logger.error("Commands", f"FAILED to load package '{item}': {e}")

Logger.info("Commands", "Registering Dynamic Movement Commands")
register_movement_commands()
Logger.info("Commands", "Command Loading Complete")