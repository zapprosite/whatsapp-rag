# Entendimento Macro do MVP Refrimix

Este documento define a visão de negócios e o objetivo central do MVP (Minimum Viable Product) de atendimento automático via WhatsApp para a Refrimix.

## 1. Por que reduzimos o escopo?

O projeto anterior continha uma infraestrutura complexa com múltiplos agentes inteligentes, processamento de áudio por inteligência artificial (TTS/STT), análise multimodal de imagens via Vision (Qwen-VL), roteamento avançado via Qdrant e suporte a calendários externos. 

Embora robusta tecnicamente, essa arquitetura causava:
- **Loops Conversacionais**: Clientes ficavam presos em fluxos repetitivos de perguntas sobre fotos e infraestrutura.
- **Respostas Lentificadas**: Latências de processamento dos modelos de linguagem atrasavam as respostas do atendimento.
- **Erros de Interpretação**: Mudanças sutis de contexto geravam saídas erráticas dos LLMs.

Para garantir **velocidade, estabilidade e clareza**, eliminamos as inteligências artificiais complexas do caminho crítico, transformando o bot em um sistema de decisão determinístico baseado em intents claras e respostas unificadas no catálogo.

## 2. Objetivo Principal

O objetivo central do MVP é realizar um **pré-atendimento rápido e eficiente**, guiando o cliente até duas conclusões possíveis:
1. **Instalação Simples**: Apresentar o preço fixo de **R$850** quando todos os requisitos forem atendidos.
2. **Visita Técnica / Projeto**: Agendar uma visita presencial por **R$50** caso falte alguma informação (fotos, capacidade) ou seja um serviço de manutenção/conserto.

## 3. Persona do Cliente

O cliente da Refrimix busca soluções rápidas para climatização de sua residência ou comércio. Ele quer saber **quanto custa** e **quando pode ser feito**. O bot deve se comunicar de forma amigável, clara e objetiva, evitando termos técnicos desnecessários e direcionando para o agendamento rápido sem criar bloqueios (como exigir obrigatoriamente o envio de fotos).
