# Integração com a Evolution API e Controle de Sessão

Este documento detalha o gerenciamento e as políticas operacionais para a **Evolution API**, que atua como nosso gateway de comunicação com o WhatsApp.

## 1. Isolamento Absoluto de Banco de Dados

- **Regra P0 Crítica**: A Evolution API **nunca** deve compartilhar o mesmo banco de dados ou a mesma URI de conexão (`DATABASE_URL`) que a aplicação do WhatsApp RAG.
- A Evolution API possui seu próprio banco de dados e schema de persistência para gerenciar chats, mídias e chaves de criptografia. Compartilhar o banco de dados corrompe os schemas e gera indisponibilidade crítica em ambos os serviços.
- Se `EVOLUTION_DATABASE_URL` estiver ausente no `.env`, recupere a chave correta do cofre local de senhas. Nunca a substitua pelo endereço do banco da aplicação.

---

## 2. Gerenciamento de Sessão e QR Code

- **Sessão Ativa**: A instância do bot roda sob o identificador parametrizado em `EVOLUTION_INSTANCE`. 
- **Proibição de Comandos Destrutivos**: Nunca envie requisições para os endpoints `/instance/logout`, `/instance/delete` ou limpe volumes Docker associados à Evolution sem autorização explícita e um plano de rollback testado.
- **Leitura de QR Code**: Em caso de desconexão da instância, o QR Code de autenticação deve ser gerado através do painel de administração da Evolution ou via chamada autenticada ao endpoint `/instance/connect`.
- **Sigilo**: Nunca imprima, capture ou versionar imagens de QR Codes ou payloads contendo as chaves de API (`EVOLUTION_API_KEY`) em arquivos públicos, respostas, ou commits do repositório.

---

## 3. Configuração do Webhook

- Para subir a Evolution API com segurança e garantindo a verificação prévia de conectividade, use sempre o script utilitário:
  `scripts/evolution-safe-up.sh`
- Este script roda testes pré-flight garantindo que a rede local do Tailscale e a porta do PostgreSQL estejam ativas antes de disparar o comando `docker compose up -d evolution-api`.
- O webhook de entrega deve apontar para o IP Tailscale estável do PC2 (`http://100.66.232.72:8000/webhook`) ou `http://localhost:8000/webhook` dependendo da topologia de contêineres adotada.
