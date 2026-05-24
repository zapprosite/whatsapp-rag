import requests
import json
import time

API_URL = "http://localhost:8000/webhook/evolution"

# 1. Teste de Áudio (Onboarding / Saudação)
audio_payload = {
    "instance": "RefrimixLead",
    "data": {
        "key": {
            "remote": "5511999999999",
            "id": f"audio_msg_{int(time.time())}",
            "fromMe": False
        },
        "messageType": "audioMessage",
        "message": {
            "audioMessage": {
                "url": "https://upload.wikimedia.org/wikipedia/commons/c/c8/Example.ogg" 
            }
        }
    }
}

# 2. Teste de Imagem (Multimodal)
image_payload = {
    "instance": "RefrimixLead",
    "data": {
        "key": {
            "remote": "5511999999999",
            "id": f"img_msg_{int(time.time())}",
            "fromMe": False
        },
        "messageType": "imageMessage",
        "message": {
            "imageMessage": {
                "url": "https://raw.githubusercontent.com/python/cpython/main/Doc/static/favicon.png", 
                "caption": "O meu ar quebrou, olha a foto."
            }
        }
    }
}

print("Enviando Audio Webhook...")
r1 = requests.post(API_URL, json=audio_payload)
print(r1.status_code, r1.json())

print("Aguardando 5s...")
time.sleep(5)

print("Enviando Image Webhook...")
r2 = requests.post(API_URL, json=image_payload)
print(r2.status_code, r2.json())
