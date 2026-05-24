---
source: modelos_ptbr_huggingface.md
type: generic
---

# Modelos PT-BR testados no Hugging Face

Objetivo: reduzir português genérico no atendimento da Refrimix sem piorar latência do WhatsApp.

## Resultado prático

- Melhor candidato local encontrado: `mradermacher/AV-BI-Qwen2.5-7B-PT-BR-Instruct-i1-GGUF`, arquivo `AV-BI-Qwen2.5-7B-PT-BR-Instruct.i1-Q4_K_M.gguf`.
- Baixado em `/home/will/llama.cpp/models/AV-BI-Qwen2.5-7B-PT-BR-Instruct.i1-Q4_K_M.gguf`.
- Servidor GPU no PC1 disponível em `http://127.0.0.1:8011/v1`, alias `qwen2.5-7b-pt-br-instruct`.
- Túnel no PC2 disponível em `http://127.0.0.1:8211/v1`.
- Não ativar como polidor em produção por padrão: na RTX 4090 do PC1 ficou muito rápido, mas ainda precisa de contexto comercial forte para não ficar genérico.

## Decisão

- Manter só o 7B PT-BR local como modelo auxiliar.
- Não manter modelos pequenos de português no ambiente.
- LoRA safetensors solto não é o melhor encaixe agora, porque o runtime local usa `llama.cpp`; GGUF mesclado é mais simples e seguro.

## Uso recomendado

- Manter `PTBR_POLISH_ENABLED=0` no atendimento ao vivo.
- Usar o 7B PT-BR em avaliação offline, geração de exemplos e comparação de tom.
- Para melhorar produção, preferir respostas determinísticas para preço e RAG com exemplos locais validados.
