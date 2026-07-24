import psycopg2
import sys
import urllib.parse

regions = [
    "ap-south-1",      # Mumbai
    "ap-southeast-1",  # Singapore
    "ap-southeast-2",  # Sydney
    "ap-northeast-1",  # Tokyo
    "us-east-1",       # N. Virginia
    "us-east-2",       # Ohio
    "us-west-1",       # N. California
    "us-west-2",       # Oregon
    "eu-west-1",       # Ireland
    "eu-central-1",    # Frankfurt
    "eu-west-2",       # London
]

project_id = "mbzyrbikvsqritfouwfy"
username = f"postgres.{project_id}"
password = "Orangeblue@12345678901"
# URL-encode the password to handle special characters like '@'
encoded_password = urllib.parse.quote_plus(password)
db_name = "postgres"

for region in regions:
    # Try aws-0 first, then aws-1
    for prefix in ["aws-0", "aws-1"]:
        host = f"{prefix}-{region}.pooler.supabase.com"
        print(f"Trying connection to {host} (port 6543)...")
        conn_str = f"postgresql://{username}:{encoded_password}@{host}:6543/{db_name}?sslmode=require"
        try:
            conn = psycopg2.connect(conn_str, connect_timeout=3)
            print(f"SUCCESS! Connected using host: {host}")
            conn.close()
            # print out the correct URL for .env
            print(f"Your DATABASE_URL should be:\nDATABASE_URL=postgresql://{username}:{encoded_password}@{host}:6543/{db_name}?sslmode=require")
            sys.exit(0)
        except Exception as e:
            print(f"Failed: {e}")

print("All connection attempts failed.")
sys.exit(1)
