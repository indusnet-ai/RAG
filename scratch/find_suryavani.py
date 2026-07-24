import os

def find_suryavani():
    base_dir = r"d:\Projects\3 RAG\RAG-chatbot-frontend-main (2)\RAG-chatbot-frontend-main"
    matches = []
    for root, dirs, files in os.walk(base_dir):
        if "node_modules" in root or ".git" in root or "dist" in root:
            continue
        for file in files:
            if file.endswith((".js", ".jsx", ".ts", ".tsx", ".html", ".json", ".css")):
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if "suryavani" in content.lower():
                        # Find line numbers
                        lines = content.splitlines()
                        for idx, line in enumerate(lines):
                            if "suryavani" in line.lower():
                                matches.append((file_path, idx + 1, line.strip()))
                except Exception as e:
                    pass
    
    print(f"Found {len(matches)} occurrences:")
    for filepath, line_num, text in matches:
        print(f"{filepath}:{line_num}: {text}")

if __name__ == "__main__":
    find_suryavani()
