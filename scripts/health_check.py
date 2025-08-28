import requests
print(requests.get("http://localhost:8080/healthz").json())
