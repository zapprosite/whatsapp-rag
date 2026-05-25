---
source: docs/mapa-pc1-pc2-refinamento.md
type: generic
---

# Voz PT-BR / TTS PC1-PC2

## Decisão Operacional

- TTS de produção: `Chatterbox Multilingual` no PC1.
- Locale obrigatório do atendimento: `pt-BR`.
- `OmniVoice` fica como fallback seguro quando Chatterbox falhar.
- `XTTS` foi removido do caminho de produção; não usar como fallback pt-BR.

## Estado PC1 Auditado Em 2026-05-25

- `Chatterbox`: `127.0.0.1:8200`, API ativa como `ChatterboxMultilingualTTS`, com `pt` habilitado.
- `OmniVoice`: `127.0.0.1:8202`, CUDA, fallback.
- Voz única ativa: `willrefrimix-influencer.wav` em `/srv/data/tts/voices` (11 vozes extras removidas em 2026-05-25).
- Textos de referência: `/srv/data/voice-instance/ref_texts/willrefrimix-influencer.txt`.
- Backups do ajuste no PC1: `config.yaml.bak-20260525-060856-pre-multilingual`, `config.yaml.bak-20260525-060930-selector-repoid`, `config.yaml.bak-20260525-094333-pre-singlevoice`.

## Parâmetros de Geração (pt-BR influencer WhatsApp)

| Parâmetro | Valor | Motivo |
|---|---|---|
| `temperature` | 0.75 | prosódia natural sem variação excessiva |
| `exaggeration` | 0.5 | expressividade de influencer, não robótico |
| `cfg_weight` | 0.35 | pacing rápido mantendo aderência à voz |
| `seed` | 0 | variação natural por chamada |
| `speed_factor` | 1.05 | fala levemente mais rápida, estilo WhatsApp |
| `chunk_size` | 400 | 1 chunk único até 420 chars → sem pausa de concatenação |
| `language` | pt | único código aceito pelo multilingual model |

Todos os parâmetros são configuráveis via `.env` sem rebuild de container (ver `.env.example`).

## Variáveis Obrigatórias

```env
TTS_ENGINE=chatterbox
TTS_LOCALE=pt-BR
OMNIVOICE_URL=http://127.0.0.1:8202
CHATTERBOX_URL=http://127.0.0.1:8200
TTS_CHATTERBOX_LANGUAGE=pt
TTS_ALLOW_CHATTERBOX_PTBR=1
TTS_MAX_CHARS=420
SSH_HOST_PC1=will-zappro@192.168.15.83
TTS_CHATTERBOX_CHUNK_SIZE=400
TTS_CHATTERBOX_TEMPERATURE=0.75
TTS_CHATTERBOX_EXAGGERATION=0.5
TTS_CHATTERBOX_CFG_WEIGHT=0.35
TTS_CHATTERBOX_SPEED_FACTOR=1.05
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
