# WhatsApp Audio Delivery Runbook — Phase 2.3.2

## Visão Geral

Valida que áudio gerado por Edge TTS chega corretamente no WhatsApp via Evolution API, com fallback seguro para texto.

## Pipeline

```
TTSService (WAV 16kHz mono)
  → audio_delivery_policy.should_send_audio()
  → audio_transcode.wav_to_whatsapp_optimal()
  → WAV → OGG/Opus (preferido) ou MP3 (fallback)
  → Evolution API /message/sendWhatsAppAudio
  → fallback texto se falhar
```

## Formato de Áudio

| Formato | MIME | Status |
|---------|------|--------|
| OGG/Opus | `audio/ogg; codecs=opus` | ✓ Preferido WhatsApp |
| MP3 | `audio/mpeg` | ✓ Suportado |
| WAV | `audio/wav` | ⚠ Funciona mas é grande/reescalado |

WhatsApp prefere OGG/Opus 64kbps mono 16kHz — feito localmente via ffmpeg para evitar conversão ruim pela Evolution API.

## Variáveis de Ambiente

```env
# TTS
TTS_ENGINE=edge
TTS_EDGE_VOICE=pt-BR-ThalitaMultilingualNeural
TTS_EDGE_FALLBACK_VOICE=pt-BR-FranciscaNeural
TTS_MAX_CHARS=420
TTS_MAX_SECONDS=35

# Audio delivery
CONFIRM_WHATSAPP_AUDIO_TEST=0   # 1 = envia WhatsApp real

# Evolution API
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY={SECRET}
EVOLUTION_INSTANCE=default
WHATSAPP_TEST_PHONE=5511999999999
```

## Regras de Delivery

### Gerar e enviar áudio ✓
- Texto ≤ 420 caracteres
- Action types: `welcome_onboarding`, `microcopy`, `schedule_confirmation`, `visit_orientation`, `short_followup`
- Sem documento anexo (PDF de orçamento/laudo/contrato/PMOC = texto)

### NÃO enviar áudio ✗
- Documentos: quote_pdf, budget_pdf, pmoc_pdf, contract_pdf, sla_pdf, technical_report_pdf
- Texto > 420 caracteres
- Usuário prefere texto
- Falha no envio → texto fallback

## Logging

Campos estruturados no log:

```
tts_engine_requested     → "edge"
tts_engine_used         → "edge"
fallback_reason         → "none" ou "edge_timeout_12.0s → chatterbox"
voice_requested          → "pt-BR-ThalitaMultilingualNeural"
duration_ms              → 1840
audio_mime_final         → "audio/ogg; codecs=opus"
audio_bytes_final        → 18640
send_result             → "ok" | "failed" | "skipped_text_fallback"
```

**Nunca logar texto completo** do áudio.

## Smoke Test

```bash
# TTS + transcode + policy (sem WhatsApp real):
.venv/bin/python scripts/smoke_whatsapp_audio.py

# Com envio real (sessão ativa necessária):
CONFIRM_WHATSAPP_AUDIO_TEST=1 \
  EVOLUTION_API_URL=http://localhost:8080 \
  EVOLUTION_INSTANCE=default \
  EVOLUTION_API_KEY=$KEY \
  WHATSAPP_TEST_PHONE=55XXXXXXXXXXX \
  .venv/bin/python scripts/smoke_whatsapp_audio.py
```

**CI/Never**: Não rodar `CONFIRM_WHATSAPP_AUDIO_TEST=1` em CI — envia áudio real para número real.

## Transcode

`audio_transcode.py` fornece:
- `detect_mime_from_bytes(audio_bytes)` — detecção por magic bytes
- `detect_mime_from_file(path)` — detecção por arquivo
- `wav_to_ogg_opus(wav_bytes)` — WAV → OGG/Opus 64kbps
- `wav_to_mp3(wav_bytes)` — WAV → MP3 64kbps
- `wav_to_whatsapp_optimal(wav_bytes)` — tenta OGG → MP3 → WAV

ffmpeg precisa estar no PATH. Parâmetros otimizados para voz:
```
OGG/Opus: -c:a libopus -b:a 64k -ar 16000 -ac 1 -application voip
MP3:       -c:a libmp3lame -b:a 64k -ar 16000 -ac 1
```

## Fallback

```
Edge TTS → Chatterbox → OmniVoice
     ↓            ↓           ↓
  WAV 16kHz   WAV 16kHz  WAV 16kHz
     ↓            ↓           ↓
  OGG/Opus   OGG/Opus   OGG/Opus  (via wav_to_whatsapp_optimal)
     ↓            ↓           ↓
  Evolution API /message/sendWhatsAppAudio
     ↓ falhou
  Texto original (fallback_text)
```

## Troubleshooting

### Áudio enviado mas não toca
1. Verificar MIME: deve ser `audio/ogg; codecs=opus` ou `audio/mpeg`
2. Verificar tamanho: WhatsApp rejeita > 16MB
3. Verificar se número está formatado: `55XXXXXXXXXXX` (código país + DDD + número)

### Evolução API retorna 400/500
1. Verificar `EVOLUTION_INSTANCE` — instância precisa existir e estar conectada
2. Verificar `EVOLUTION_API_KEY` — chave correta
3. Verificar se `/message/sendWhatsAppAudio` endpoint existe na versão da API

### Fallback texto não chega
1. Se `send_whatsapp_audio` retorna `False`, código chamador deve acionar texto
2. Verificar `should_send_audio` não está bloqueando antes do envio

### Transcode retorna WAV original
1. `ffmpeg` não está no PATH ou falhou
2. Verificar `which ffmpeg` e `ffmpeg -version`
3. Bytes de entrada pequenos demais (mínimo ~100 bytes)
