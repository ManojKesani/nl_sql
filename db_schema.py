import json
import sqlite3

def get_database_schema(db_path: str) -> str:
    """Extracts DDL for all tables and views from SQLite."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = conn.cursor()
    query = """
        SELECT sql 
        FROM sqlite_schema 
        WHERE type IN ('table', 'view') 
          AND name NOT LIKE 'sqlite_%' 
          AND sql IS NOT NULL;
    """
    cursor.execute(query)
    tables = cursor.fetchall()
    conn.close()
    return "\n\n".join(row[0].strip() + ";" for row in tables)


def build_system_prompt(prompt_path: str, db_path: str) -> dict:
    """Loads prompt JSON and replaces database_schema with extracted DDL."""
    # 1. Extract database schema DDL
    schema = get_database_schema(db_path)
    
    # 2. Read existing system prompt file
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt_data = json.load(f)
    
    # 3. Inject schema into dictionary
    prompt_data["instructions"]["database_schema"] = schema
    
    return prompt_data


# --- Usage Example ---
if __name__ == "__main__":
    db_file = "longlist.db"
    prompt_file = "sys_prompt.json"
    
    # Generate updated prompt object
    system_prompt_config = build_system_prompt(prompt_file, db_file)
    
    # Convert system prompt into text payload for LLM API calls
    system_prompt_text = json.dumps(system_prompt_config["instructions"], indent=2)
    
    # (Optional) Save back to a new populated JSON file
    with open("sys_promt_populated.json", "w", encoding="utf-8") as f:
        json.dump(system_prompt_config, f, indent=2)

    print("Schema successfully injected!")