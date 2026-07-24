import urllib.request
import json

data = {
    "name": "Test User",
    "email": "test@example.com",
    "password": "Password123",
    "confirm_password": "Password123"
}

req = urllib.request.Request(
    "http://127.0.0.1:8000/register",
    data=json.dumps(data).encode('utf-8'),
    headers={"Content-Type": "application/json"},
    method="POST"
)

try:
    with urllib.request.urlopen(req) as res:
        print("Success:", res.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
    if hasattr(e, 'read'):
        print("Response:", e.read().decode('utf-8'))
