import os

def search_supabase_urls():
    start_dir = "d:\\Projects"
    print(f"Scanning {start_dir} for supabase strings...")
    found_urls = set()
    for root, dirs, files in os.walk(start_dir):
        if any(ignored in root for ignored in ["node_modules", "venv", ".git", "__pycache__"]):
            continue
        for file in files:
            path = os.path.join(root, file)
            # Only read text files or config files
            if file.endswith(('.env', '.yaml', '.yml', '.toml', '.json', '.js', '.ts', '.py')):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            if "supabase" in line.lower() and ("postgres://" in line or "postgresql://" in line or "pooler" in line):
                                clean_line = line.strip()
                                if clean_line not in found_urls:
                                    found_urls.add(clean_line)
                                    print(f"Found in {path}: {clean_line}")
                except Exception:
                    pass

if __name__ == "__main__":
    search_supabase_urls()
