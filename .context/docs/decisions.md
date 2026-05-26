# Decisões e Regras Comerciais do MVP

Este documento consolida todas as políticas comerciais oficiais adotadas pela Refrimix no MVP. Essas regras são codificadas no bot de forma determinística para evitar divergências de orçamentação.

## 1. Tabela de Preços Oficial

| Tipo de Serviço | Condições do Cenário | Preço Cobrado | Observações comerciais |
| :--- | :--- | :--- | :--- |
| **Instalação Simples** | Costa a costa, evaporadora e condensadora próximas, até 3m de tubulação, acesso fácil. | **R$ 850,00** | Inclui material básico e mão de obra. Considera ponto elétrico pronto. |
| **Higienização** | Split padrão (hi-wall), equipamento funcionando e instalado corretamente. | **R$ 200,00 / aparelho** | Se o aparelho não climatizar, vira análise de manutenção por R$50. |
| **Visita Técnica / Análise** | Manutenção geral, conserto de vazamentos, ou instalações sem dados/fotos suficientes. | **R$ 50,00** | Valor é **abatido** do preço final se o orçamento proposto for aprovado. |
| **Equipamentos Complexos** | Cassete, Piso-teto, Multi-split, Dutos, VRF/VRV ou potências superiores a 18k BTUs. | **A partir de R$ 50,00** | Tratado como visita ou projeto residencial/comercial personalizado. |

## 2. Regra de Fotos e Bloqueios

- **A foto ajuda, mas não trava**: No fluxo anterior, o cliente ficava travado em loops caso não enviasse fotos do local. 
- No MVP, se o cliente disser que não tem foto, não sabe tirar, ou o bot detectar intenção de indisponibilidade de imagens, o fluxo avança **imediatamente** para o agendamento de uma Visita Técnica de **R$50**, explicando que a análise será feita presencialmente pelo profissional.

## 3. Fluxo de Direcionamento Comercial

O bot segue a árvore de prioridade estrita de direcionamento comercial para evitar fricções com o cliente:
1. **Identificar o Nome**: Sempre capturar o nome do cliente no início da conversa para deixar o atendimento profissional e humanizado.
2. **Definir o Serviço**: Entender se é Instalação, Higienização ou Manutenção/Conserto.
3. **Validar Cenário Simples (apenas para Instalação)**: Se o cliente tem fotos/dados e o cenário é simples, oferece R$850. Se falta informação ou é complexo, oferece a Visita Técnica de R$50.
4. **Agendar Janela**: Solicitar a preferência de período (manhã ou tarde) para que o time operacional finalize o agendamento humano de forma ágil.
