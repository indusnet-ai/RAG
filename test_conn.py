import psycopg2
import sys

connection_urls = [
    "postgresql://postgres.ubekmwmxmwmhcnhqkdwn:nG6iPUvOwiI3skLw@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres",
    "postgresql://postgres.ubekmwmxmwmhcnhqkdwn:nG6iPUvOwiI3skLw@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres",
    "postgresql://postgres.ubekmwmxmwmhcnhqkdwn:nG6iPUvOwiI3skLw@db.ubekmwmxmwmhcnhqkdwn.supabase.co:5432/postgres",
]

for idx, url in enumerate(connection_urls):
    print(f"\n--- Testing Connection URL {idx + 1} ---")
    print(f"URL: {url.split('@')[1] if '@' in url else url}")
    try:
        conn = psycopg2.connect(url, connect_timeout=5)
        print("Success!")
        conn.close()
        sys.exit(0)
    except Exception as e:
        print(f"Failed: {e}")

sys.exit(1)
