import requests

url = "http://127.0.0.1:5000/create-checkout-session"
print("START DEBUGU: WYSYŁAM POST DO:", url)

try:
    # Sprawdzenie połączenia z serwerem
    response = requests.post(url, timeout=5)
    print("POŁĄCZENIE UDAŁO SIĘ")
    print("STATUS KOD:", response.status_code)

    # Sprawdzenie treści odpowiedzi
    try:
        data = response.json()
        print("ODPOWIEDŹ JSON:", data)
    except ValueError:
        print("ODPOWIEDŹ NIE JEST JSON:", response.text)

except requests.exceptions.ConnectTimeout:
    print("BŁĄD: TIMEOUT – Flask nie odpowiada na połączenie")
except requests.exceptions.ConnectionError:
    print("BŁĄD: NIE MOŻNA POŁĄCZYĆ SIĘ – sprawdź Flask i port")
except Exception as e:
    print("INNY BŁĄD:", e)
