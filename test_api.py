import requests
import json

payload = {
    "query": "Summarize the resume for me",
    "conversation_id": "test_script_123",
    "filters": {},
    "generate_full_response": True
}

print("Testing direct non-streaming POST...")
try:
    resp = requests.post("http://127.0.0.1:8000/ask", json=payload)
    print("Non-streaming response:", resp.json())
except Exception as e:
    print(e)

print("\nTesting streaming POST...")
try:
    resp = requests.post("http://127.0.0.1:8000/ask/stream", json=payload, stream=True)
    for line in resp.iter_lines():
        if line:
            print("STREAM:", line.decode("utf-8"))
except Exception as e:
    print(e)
