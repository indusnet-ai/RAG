import urllib.request
import json

token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2NGNkZWRlOS1jZmE1LTRhMjItYTVkMS0yNTQ4YzZhMzQ4OTIiLCJlbWFpbCI6ImFkbWluQHJhZ2NoYXQuY29tIiwiZXhwIjoxNzgxMDEzNzc5fQ.l4palLyCsmYfhSL_jddUZrOTXNAZfG3NiZxMA-nNlgY"

req = urllib.request.Request(
    "http://127.0.0.1:8000/collections/create",
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as res:
        print("Success:", res.read().decode('utf-8'))
except Exception as e:
    print("Error:", e)
    if hasattr(e, 'read'):
        print("Response:", e.read().decode('utf-8'))
