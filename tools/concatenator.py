# tools/concatenator.py
import os

# --- Configuration ---
MAX_SIZE = 1 * 1024 * 1024  # 1MB per part
SOURCE_DIR = ".."           # Scan parent directory (project root)
OUTPUT_DIR = "concatenated" # Write to ./concatenated (inside tools)

# Directories to ignore entirely
IGNORE_DIRS = {
    '.git', '__pycache__', 'venv', '.venv', '_old', 
    'mud-world-editor', 'concatenated', '.vscode', '.idea', 
    'tools', 'tests_quarantine' # Important: Ignore the tools dir so we don't scan this script or the output
}

# Files to ignore specific filenames
IGNORE_FILES = {
    'concatenator.py', 'concatenated.py', 'file_fixer_upper.py', '.DS_Store'
}

# Mapping root-level files to specific folder groups.
# Files in the root NOT in this list will be ignored.
ROOT_FILE_MAPPING = {
    'main.py': 'engine'
}
# ---------------------

class OutputManager:
    def __init__(self, group_name, extension):
        self.group_name = group_name
        self.extension = extension
        self.part_num = 1
        self.current_size = 0
        self.file_handle = None

    def _get_filename(self):
        # Format: concatenated/all_code_engine_part1.py.txt
        return os.path.join(OUTPUT_DIR, f"all_code_{self.group_name}_part{self.part_num}.{self.extension}.txt")

    def _open_file_if_needed(self):
        """Lazy loader: only creates the file if we actually have content to write."""
        if self.file_handle is None:
            filename = self._get_filename()
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            self.file_handle = open(filename, "w", encoding="utf-8")
            print(f"  [NEW FILE] Created {filename}")

    def _rotate_file(self):
        """Closes current file and increments part number."""
        if self.file_handle:
            self.file_handle.close()
        
        self.part_num += 1
        self.current_size = 0
        self.file_handle = None

    def write(self, text):
        encoded_text = text.encode("utf-8")
        text_size = len(encoded_text)

        # Check split requirement
        if self.file_handle and (self.current_size + text_size > MAX_SIZE):
            self._rotate_file()

        self._open_file_if_needed()

        if not self.file_handle:
            print("No bueno.")
        else:
            self.file_handle.write(text)
            self.current_size += text_size

    def close(self):
        if self.file_handle:
            self.file_handle.close()

def get_file_content(file_path, rel_path):
    """Reads file, adds path header if missing."""
    # Standardize path separators to forward slash for headers
    clean_rel_path = rel_path.replace(os.sep, '/')
    header = f"# {clean_rel_path}\n"
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        if not lines:
            return header + "\n"

        # Check if first line is already a path comment to avoid duplication
        first_line = lines[0].strip()
        # Basic check to see if it looks like a path comment we generated
        if not (first_line.startswith("# ") and (first_line.endswith(".py") or first_line.endswith(".json"))):
            content_to_write = [header] + lines
        else:
            # Replace existing header to ensure accuracy of path
            lines[0] = header
            content_to_write = lines

        return "".join(content_to_write) + "\n"
    except Exception as e:
        print(f"!! Error reading {file_path}: {e}")
        return ""

def process_and_concatenate(extension):
    print(f"--- Processing .{extension} files ---")
    
    # Key: group_name, Value: OutputManager instance
    managers = {}

    def get_manager(group):
        if group not in managers:
            managers[group] = OutputManager(group, extension)
        return managers[group]

    # 1. Process Root Directory (Only mapped files)
    # ---------------------------------------------
    try:
        root_items = sorted(os.listdir(SOURCE_DIR))
    except FileNotFoundError:
        print(f"Error: Source directory '{SOURCE_DIR}' not found.")
        return

    for item in root_items:
        full_path = os.path.join(SOURCE_DIR, item)
        
        if os.path.isfile(full_path):
            if item in IGNORE_FILES or not item.endswith(f".{extension}"):
                continue
            
            # Only process root files if they are in the mapping
            if item in ROOT_FILE_MAPPING:
                group = ROOT_FILE_MAPPING[item]
                print(f"  Processing root file: {item} -> Group: {group}")
                # For root files, the relative path is just the filename
                content = get_file_content(full_path, item)
                get_manager(group).write(content)

    # 2. Process Subdirectories (Dynamic Groups)
    # ---------------------------------------------
    for item in root_items:
        full_path = os.path.join(SOURCE_DIR, item)
        
        if os.path.isdir(full_path):
            if item in IGNORE_DIRS:
                continue
            
            # The folder name becomes the group name (e.g., 'engine', 'tests')
            group_name = item
            
            # Walk through this specific subdirectory
            for root, dirs, files in os.walk(full_path):
                # Modify dirs in-place to skip ignored folders during walk
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                
                for file in sorted(files):
                    if file in IGNORE_FILES or not file.endswith(f".{extension}"):
                        continue
                    
                    file_path = os.path.join(root, file)
                    # Calculate relative path from the project root for the header comment
                    rel_path = os.path.relpath(file_path, SOURCE_DIR)
                    
                    content = get_file_content(file_path, rel_path)
                    if content:
                        get_manager(group_name).write(content)

    # Clean up
    for mgr in managers.values():
        mgr.close()

if __name__ == "__main__":
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    process_and_concatenate('py')
    process_and_concatenate('json')
    print("\nDone.")