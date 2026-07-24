import os

paths_to_check = [
    "C:\\Program Files\\PostgreSQL",
    "C:\\Program Files (x86)\\PostgreSQL",
]

for path in paths_to_check:
    if os.path.exists(path):
        print(f"PostgreSQL directory found at: {path}")
        # List contents
        try:
            print("Contents:", os.listdir(path))
        except Exception as e:
            print(f"Error listing: {e}")
    else:
        print(f"PostgreSQL directory NOT found at: {path}")
