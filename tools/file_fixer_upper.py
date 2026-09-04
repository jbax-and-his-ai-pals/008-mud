# tools/file_fixer_upper.py
import os

# Configuration: Directories to skip
IGNORE_DIRS = {'.git', '__pycache__', 'venv', '.venv', 'env', 'build', 'dist'}

def process_files(root_dir=".."):
    for root, dirs, files in os.walk(root_dir):
        # Modifying dirs in-place allows os.walk to skip ignored directories
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                # Normalize path to use forward slashes for the comment
                relative_path = os.path.relpath(file_path, root_dir).replace(os.sep, '/')
                header_line = f"# {relative_path}\n"

                print(f"file: {file_path}")
                print(f"header: {header_line}")
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.readlines()

                    # Check if the first line already matches
                    if not content or content[0] != header_line:
                        print(f"Updating: {file_path}")
                        
                        # If the first line is an old path comment, replace it
                        if content and content[0].startswith("# ") and content[0].endswith(".py\n"):
                            content[0] = header_line
                        else:
                            # Otherwise, insert it at the very top
                            content.insert(0, header_line)

                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.writelines(content)
                except Exception as e:
                    print(f"Error processing {file_path}: {e}")

if __name__ == "__main__":
    process_files()