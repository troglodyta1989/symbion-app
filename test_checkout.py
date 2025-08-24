import requests

url = "http://127.0.0.1:5000/create-checkout-session"

try:
    response = requests.post(url)
    print(response.json())
except Exception as e:
    print("Błąd:", e)
