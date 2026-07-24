import os

def search_vector_queries():
    backend_dir = "d:\\Projects\\3 RAG\\RAG-chatbot-RAG-CHATBOT-FASTAPI (8)\\RAG-chatbot-RAG-CHATBOT-FASTAPI"
    print("Searching for vector operations in SQL queries...")
    for root, dirs, files in os.walk(backend_dir):
        if any(ignored in root for ignored in ["node_modules", "venv", ".git", "__pycache__"]):
            continue
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, 1):
                            if "<=>" in line or "vector(" in line or "vector" in line.lower() and ("select" in line.lower() or "from" in line.lower()):
                                print(f"Found in {file}:{line_num}: {line.strip()}")
                except Exception:
                    pass

if __name__ == "__main__":
    search_vector_queries()
