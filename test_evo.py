import requests
import base64
import os

url = "http://localhost:8080/message/sendWhatsAppAudio/RefrimixLead"
headers = {"apikey": "429683C4C977415CAAFCCE10F7D57E11", "Content-Type": "application/json"}

# small 1s wav 
b64 = "UklGRjIAAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAAABmYWN0BAAAAAAAAABkYXRhAAAAAA=="

payload = {
    "number": "5513996659382",
    "audio": b64
}

r = requests.post(url, headers=headers, json=payload)
print("sendWhatsAppAudio:", r.status_code, r.text)

url2 = "http://localhost:8080/message/sendMedia/RefrimixLead"
payload2 = {
    "number": "5513996659382",
    "mediatype": "audio",
    "mimetype": "audio/mp4",
    "media": b64
}

r2 = requests.post(url2, headers=headers, json=payload2)
print("sendMedia:", r2.status_code, r2.text)
