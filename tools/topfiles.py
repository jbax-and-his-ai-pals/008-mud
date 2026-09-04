# tools/topfiles.py
import os
import argparse
from pathlib import Path

# Directories to ignore
DEFAULT_EXCLUDES = {
    '.git', '__pycache__', 'venv', '.venv', 'env', 
    'node_modules', '.idea', '.vscode', 'build', 'dist', 
    'target', 'bin', 'obj'
}

def get_readable_size(size_in_bytes):
    """Converts bytes to human readable string."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

def find_largest_files(extension, count=10, search_path='.'):
    # Ensure extension starts with a dot
    if not extension.startswith('.'):
        extension = '.' + extension

    files_data = []
    
    print(f"Searching for *{extension} in '{search_path}'...")
    print(f"Excluding directories: {', '.join(sorted(DEFAULT_EXCLUDES))}")

    try:
        # os.walk allows us to modify 'dirs' in-place to skip whole trees
        for root, dirs, files in os.walk(search_path):
            # Prune excluded directories
            # We must modify the 'dirs' list in-place using slice assignment [:]
            dirs[:] = [d for d in dirs if d not in DEFAULT_EXCLUDES]
            
            for filename in files:
                if filename.endswith(extension):
                    filepath = os.path.join(root, filename)
                    try:
                        size = os.path.getsize(filepath)
                        files_data.append((size, filepath))
                    except OSError:
                        pass
                        
    except KeyboardInterrupt:
        print("\nSearch cancelled.")
        return

    # Sort by size (descending)
    files_data.sort(key=lambda x: x[0], reverse=True)

    # Slice the top N
    top_files = files_data[:count]

    if not top_files:
        print(f"\nNo files found with extension '{extension}'")
        return

    print(f"\nTop {count} largest '{extension}' files:")
    print("-" * 80)
    print(f"{'Size':<15} | {'File Path'}")
    print("-" * 80)

    for size, path in top_files:
        readable_size = get_readable_size(size)
        # Try to make path relative for display
        try:
            display_path = os.path.relpath(path, os.getcwd())
        except ValueError:
            display_path = path
        print(f"{readable_size:<15} | {display_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Find largest files recursively, excluding common trash folders.")
    parser.add_argument("extension", help="File extension to search for (e.g., py, json, txt)")
    parser.add_argument("-n", "--number", type=int, default=10, help="Number of files to show (default: 10)")
    parser.add_argument("-p", "--path", default="..", help="Directory to search (default: current)")

    args = parser.parse_args()
    
    find_largest_files(args.extension, args.number, args.path)