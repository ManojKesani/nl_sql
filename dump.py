from pathlib import Path


def combine_py_files(folder_path: str, output_file: str = "combined_code.txt"):
    """Combines all .py files in folder_path into a single .txt file with headers."""
    source_dir = Path(folder_path).resolve()
    output_path = Path(output_file).resolve()

    # Folders to ignore
    ignored_dirs = {
        ".git",
        "__pycache__",
        "venv",
        ".venv",
        "env",
        ".env",
        "build",
        "dist",
    }

    count = 0
    with open(output_path, "w", encoding="utf-8") as outfile:
        # Recursively search for .py files
        for py_file in sorted(source_dir.rglob("*.py")):
            # Skip files in ignored directories
            if any(part in ignored_dirs for part in py_file.parts):
                continue

            relative_path = py_file.relative_to(source_dir)

            # Write header tag for the file
            outfile.write(f"{'=' * 80}\n")
            outfile.write(f"FILE: {relative_path}\n")
            outfile.write(f"{'=' * 80}\n\n")

            # Read and write content
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
                outfile.write(content)
                outfile.write("\n\n\n")
                count += 1
            except Exception as e:
                outfile.write(f"# Error reading file: {e}\n\n\n")

    print(
        f"Done! Combined {count} Python file(s) into '{output_path.name}' at:\n{output_path}"
    )


if __name__ == "__main__":
    # Replace with your target folder path
    TARGET_FOLDER = "/home/dell/Desktop/nl_sql/nlsql"
    OUTPUT_FILE = "combined_code.txt"

    combine_py_files(TARGET_FOLDER, OUTPUT_FILE)