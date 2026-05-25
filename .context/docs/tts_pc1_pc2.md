---
source: docs/mapa-pc1-pc2-refinamento.md
type: generic
---

# Voz PT-BR / TTS PC1-PC2

## Decisão Operacional

- TTS de produção: `Chatterbox Multilingual` no PC1.
- Locale obrigatório do atendimento: `pt-BR`.
- `XTTS` é legado e não deve ser fallback automático para pt-BR, porque opera com código genérico `pt`.
- `OmniVoice` fica como fallback seguro quando Chatterbox falhar.

## Estado PC1 Auditado Em 2026-05-25

- `Chatterbox`: `127.0.0.1:8200`, API ativa como `ChatterboxMultilingualTTS`, com `pt` habilitado.
- `OmniVoice`: `127.0.0.1:8202`, CUDA, 12 vozes em `/srv/data/tts/voices`, fallback.
- Textos de referência: `/srv/data/voice-instance/ref_texts`.
- Backups do ajuste no PC1: `/srv/apps/chatterbox-tts/config.yaml.bak-20260525-060856-pre-multilingual` e `/srv/apps/chatterbox-tts/config.yaml.bak-20260525-060930-selector-repoid`.

## Variáveis Obrigatórias

```env
TTS_ENGINE=chatterbox
TTS_LOCALE=pt-BR
OMNIVOICE_URL=http://127.0.0.1:8202
CHATTERBOX_URL=http://127.0.0.1:8200
XTTS_URL=http://localhost:8020
TTS_VOICES_PATH=/srv/data/tts/voices
TTS_ALLOW_XTTS_PT_FALLBACK=0
TTS_ALLOW_CHATTERBOX_PTBR=1
TTS_MAX_CHARS=420
SSH_HOST_PC1=will-zappro@192.168.15.83
```

## Auditoria SRE

```bash
.venv/bin/python -m sre.probes tts-audit
.venv/bin/python -m sre.probes tts-audit --synthesize
```

Regra: Chatterbox só fica primário enquanto este comando estiver verde:

```bash
.venv/bin/python -m sre.probes tts-audit --require-chatterbox-pt
```

Se falhar, volte para `TTS_ENGINE=omnivoice`.
