import os
import re

backend_dir = r"d:\Projects\3 RAG\RAG-chatbot-RAG-CHATBOT-FASTAPI (8)\RAG-chatbot-RAG-CHATBOT-FASTAPI"

patterns = [
    r'NOW\(\)',
    r'\bNOW\b',
    r'gen_random_uuid\(\)'
]

for root, dirs, files in os.walk(backend_dir):
    if "venv" in root or "__pycache__" in root or ".git" in root:
        continue
    for file in files:
        if file.endswith(".py"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                for pattern in patterns:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        # print line and context
                        start = max(0, match.start() - 50)
                        end = min(len(content), match.end() + 50)
                        context = content[start:end].replace("\n", " ")
                        print(f"File: {os.path.relpath(path, backend_dir)}")
                        print(f"  Pattern: {pattern}")
                        print(f"  Context: ... {context} ...")
                        print("-" * 40)
            except Exception as e:
                pass
