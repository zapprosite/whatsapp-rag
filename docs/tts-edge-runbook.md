# Edge TTS Runbook — Phase 2.3.1

## Visão Geral

Edge TTS (Microsoft Azure) é o engine TTS default pragmático para o WhatsApp Refrimix. Não depende do PC1, usa voz pt-BR ThalitaNeural, e tem fallback para Chatterbox/OmniVoice.

## Arquitetura

```
Edge TTS (pt-BR-ThalitaMultilingualNeural)
  ↓ falha
pt-BR-FranciscaNeural (fallback de voz)
  ↓ falha
Chatterbox local (PC1)
  ↓ falha
OmniVoice (PC1)
  ↓ falha
Texto (TTS_SEND_TEXT_FALLBACK=1)
```

## Variáveis de Ambiente

```env
# Engine
TTS_ENGINE=edge

# Voz principal
TTS_EDGE_VOICE=pt-BR-ThalitaMultilingualNeural
TTS_EDGE_FALLBACK_VOICE=pt-BR-FranciscaNeural
TTS_EDGE_SPEED=+0%

# Timeouts e retry
TTS_EDGE_TIMEOUT_SECONDS=12
TTS_EDGE_RETRIES=1

# Saída (sempre 16kHz mono WAV para compatibilidade com send_whatsapp_audio)
TTS_EDGE_OUTPUT_SAMPLE_RATE=16000
TTS_EDGE_OUTPUT_CHANNELS=1

# Cache
TTS_EDGE_CACHE_ENABLED=1
TTS_CACHE_TTL_SECONDS=604800   # 7 dias
TTS_CACHE_DIR=/tmp/refrimix_tts_cache

# Limites de conteúdo
TTS_MAX_CHARS=420
TTS_MAX_SECONDS=35
TTS_SEND_TEXT_FALLBACK=1
```

## Quando Usar Áudio

### Gerar áudio ✓
- Confirmação curta (agendamento, visita)
- Acolhimento inicial
- Orientação simples
- Follow-up humano/natural
- Microcopy natural

### NÃO gerar áudio ✗
- Orçamento / contrato / laudo / PMOC
- Listas grandes de horários
- Explicação técnica longa
- Documentos formais
- Qualquer texto > 420 caracteres
- Qualquer coisa que passe de 35 segundos de fala

## Logging Estruturado

Todo synthesize gera um log com campos estruturados:

```json
{
  "tts_engine_requested": "edge",
  "tts_engine_used": "chatterbox",
  "fallback_reason": "edge_timeout → chatterbox",
  "voice_requested": "pt-BR-ThalitaMultilingualNeural",
  "duration_ms": 1840,
  "text_len": 87
}
```

Motivos de fallback:
- `edge_timeout_12.0s` — Edge TTS não respondeu no timeout
- `edge_ffmpeg_failed_{voice}` — conversão WAV falhou
- `edge_wav_too_small_{voice}` — áudio gerado corrupto
- `edge_voice_fallback_{from}_to_{to}` — Thalita falhou, Francisca OK
- `edge_exception_{type}_{voice}` — outra exceção
- `chatterbox → omnivoice` — Chatterbox falhou
- `omnivoice → chatterbox` — OmniVoice falhou
- `text_fallback` — todos os engines falharam

## Cache

```
tts:edge:pt-BR-ThalitaMultilingualNeural:+0%:a3f2b1c4...
```

- Chave: hash SHA256 do texto normalizado (case-insensitive, collapse whitespace)
- TTL: 7 dias
- Formato: WAV 16kHz mono + .meta.json
- Diretório: `/tmp/refrimix_tts_cache` (ou TTS_CACHE_DIR)

## Limites

| Parâmetro | Valor | Razão |
|-----------|-------|-------|
| TTS_MAX_CHARS | 420 | ~35s de fala na velocidade normal |
| TTS_MAX_SECONDS | 35 | ninguém quer ouvir um textão |
| TTS_EDGE_TIMEOUT | 12s | latência aceitável, não bloqueia |
| TTL cache | 7 dias | freshness vs disk |

## Voz — Regras

- **Usar**: ThalitaNeural como assistente técnico da Refrimix
- **Nunca**: imitar o Will ou qualquer pessoa real
- **Som**: profissional, direto, natural — como um assistente executivo
- **Evitar**: beep, saudação longa, tom robótico, exagero

## Troubleshooting

### Edge TTS lento
1. Verificar `TTS_EDGE_TIMEOUT_SECONDS=12` — se rede lenta, subir para 20
2. Habilitar cache: `TTS_EDGE_CACHE_ENABLED=1` — repete não tenta rede

### Fallback Chatterbox
- Chatterbox depende do PC1 — se PC1 fora, Chatterbox também falha
- OmniVoice é último fallback PC1

### health() retorna False
- Edge TTS health tenta sintetizar "ok" — verifica ffmpeg + MP3→WAV
- Não testa latência real, só se consegue completar a síntese

### Cache não命中率
- Verificar `TTS_EDGE_CACHE_ENABLED=1`
- TTL expirou: `TTS_CACHE_TTL_SECONDS=604800` (7 dias)
- Diretório cheio: `TTS_CACHE_DIR` em partição com espaço
