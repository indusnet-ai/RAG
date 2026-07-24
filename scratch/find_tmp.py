import os

def scan_files():
    base_dir = r"d:\Projects\3 RAG\RAG-chatbot-RAG-CHATBOT-FASTAPI (8)\RAG-chatbot-RAG-CHATBOT-FASTAPI"
    matches = []
    for root, dirs, files in os.walk(base_dir):
        if "venv" in root or ".git" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        if "file_path" in line:
                            matches.append((file_path, idx + 1, line.strip()))
                except Exception as e:
                    pass
    
    print(f"Found {len(matches)} occurrences:")
    for filepath, line_num, text in matches:
        print(f"{filepath}:{line_num}: {text}")

if __name__ == "__main__":
    scan_files()
