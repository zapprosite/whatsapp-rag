import time
import uuid
import requests
import concurrent.futures

API_URL = "http://localhost:8000/webhook/evolution"
INSTANCE = "RefrimixLead"
PHONE = "5513999999999"

AUDIO_URL = "https://upload.wikimedia.org/wikipedia/commons/c/c8/Example.ogg"
IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/1/17/Air_Conditioner_-_Window_Type.jpg/320px-Air_Conditioner_-_Window_Type.jpg"

def create_payload(msg_type, content=None):
    msg_id = str(uuid.uuid4())
    payload = {
        "instance": INSTANCE,
        "data": {
            "key": {
                "remote": f"{PHONE}@s.whatsapp.net",
                "id": msg_id,
                "fromMe": False
            },
            "messageType": msg_type,
            "message": {}
        }
    }
    
    if msg_type == "conversation":
        payload["data"]["message"]["conversation"] = content
    elif msg_type == "audioMessage":
        payload["data"]["message"]["audioMessage"] = {"url": AUDIO_URL}
    elif msg_type == "imageMessage":
        payload["data"]["message"]["imageMessage"] = {"url": IMAGE_URL, "caption": content or ""}
        
    return payload

def send_request(args):
    req_id, payload = args
    try:
        t0 = time.time()
        response = requests.post(API_URL, json=payload, timeout=10)
        status = response.status_code
        try:
            data = response.json()
        except:
            data = response.text
        latency = time.time() - t0
        return (req_id, status, data, latency)
    except Exception as e:
        return (req_id, 500, str(e), 0)

def test_e2e_real():
    print("=== INICIANDO E2E REAL (1 requisição por modalidade) ===")
    tests = [
        ("conversation", "Olá, gostaria de fazer um orçamento de higienização."),
        ("audioMessage", None),
        ("imageMessage", "Dá uma olhada em como tá sujo esse ar!"),
    ]
    
    for i, (msg_type, content) in enumerate(tests):
        print(f"-> Enviando {msg_type}...")
        payload = create_payload(msg_type, content)
        _, status, data, latency = send_request((f"e2e_{i}", payload))
        print(f"<- Status: {status} | Latência Webhook: {latency:.3f}s | Resposta: {data}")
        time.sleep(1)
    print("=== FIM E2E REAL ===\n")

def test_stress(num_requests=30, concurrency=10):
    print(f"=== INICIANDO TESTE DE STRESS ({num_requests} requisições, {concurrency} threads) ===")
    
    payloads = []
    for i in range(num_requests):
        if i % 5 == 0:
            payloads.append((i, create_payload("audioMessage")))
        elif i % 5 == 1:
            payloads.append((i, create_payload("imageMessage", "Orçamento pra esse ar?")))
        else:
            payloads.append((i, create_payload("conversation", f"Teste de carga rápido #{i}")))
            
    t0_total = time.time()
    
    print("Enviando requisições concorrentes...")
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        for res in executor.map(send_request, payloads):
            results.append(res)
            
    total_time = time.time() - t0_total
    
    success = sum(1 for r in results if r[1] == 200)
    errors = len(results) - success
    avg_latency = sum(r[3] for r in results) / len(results) if results else 0
    
    print("\n--- RESULTADOS STRESS ---")
    print(f"Tempo total: {total_time:.2f}s")
    print(f"Requisições/segundo: {num_requests/total_time:.2f}")
    print(f"Sucesso: {success} | Falhas: {errors}")
    print(f"Latência média do Webhook: {avg_latency:.3f}s")
    print("NOTA: O Webhook responde imediatamente pois enfileira no Redis.")
    print("Para ver o processamento real (LLM/Vision/STT/TTS), acompanhe os logs:")
    print("docker logs -f whatsapp-rag-fastapi-rag-1")

if __name__ == "__main__":
    import sys
    mode = "both"
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        
    if mode in ["e2e", "both"]:
        test_e2e_real()
    if mode in ["stress", "both"]:
        test_stress(num_requests=30, concurrency=10)
