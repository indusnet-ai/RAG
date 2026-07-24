import os

backend_dir = r"d:\Projects\3 RAG\RAG-chatbot-RAG-CHATBOT-FASTAPI (8)\RAG-chatbot-RAG-CHATBOT-FASTAPI"

for root, dirs, files in os.walk(backend_dir):
    if "venv" in root or "__pycache__" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                if "<->" in content:
                    print(f"File: {os.path.relpath(path, backend_dir)}")
                    for line_no, line in enumerate(content.splitlines(), 1):
                        if "<->" in line:
                            print(f"  Line {line_no}: {line}")
            except Exception as e:
                pass
