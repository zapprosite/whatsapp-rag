# docs/operations/prune-old-repo.md

# Plano de Prune — Repo Antigo (whatsapp-rag)

**ATENÇÃO**: Este plano é só documentação. NÃO executar antes da aprovação.

## Critérios para Prune (Gate)

Antes de fazer qualquer prune, TODOS os itens abaixo devem estar OK:

- [ ] Repo limpo (`whatsapp-rag-clean`) respondeu WhatsApp real por pelo menos **24-72h**
- [ ] `dead_letter` no Redis está em **zero** por pelo menos 24h
- [ ] Health endpoint retorna `"status": "ok"` consistentemente
- [ ] Todos os 5 smoke tests continuam passando
- [ ] Backup completo do repo antigo (`whatsapp-rag`) existe
- [ ] Commit do repo antigo está **taggeado** (ex: `legacy-before-clean-YYYYMMDD`)
- [ ] `.env` do repo limpo está **preservado** (não no git)
- [ ] Evolution API está apontando para o novo serviço (ou migração de webhook validada)
- [ ] Rollback documentado e testado (voltar pro repo antigo em <5 min)
- [ ] Equipe (William) aprovou o prune

## Pré-requisitos

### 1. Backup do Repo Antigo

```bash
cd /home/will/whatsapp-rag

# Tag o commit atual como legacy
git tag legacy-before-clean-$(date +%Y%m%d)

# Cria backup em tar
tar -czf ~/backups/whatsapp-rag-legacy-$(date +%Y%m%d).tar.gz \
  --exclude='.git/objects' \
  --exclude='__pycache__' \
  --exclude='.venv' \
  -C /home/will whatsapp-rag

# Verificar integridade
tar -tzf ~/backups/whatsapp-rag-legacy-$(date +%Y%m%d).tar.gz | wc -l
```

### 2. Verificar que .env está preservado

```bash
# .env deve existir fora do repo
ls -la ~/secrets/whatsapp-rag.env
# ou
ls -la /home/will/workspace/whatsapp-rag-clean/.env
```

### 3. Testar rollback

```bash
# Parar clean
cd /home/will/workspace/whatsapp-rag-clean && docker compose down

# Startar antigo
cd /home/will/whatsapp-rag && docker compose up -d

# Verificar health do antigo
curl http://localhost:8000/health

# Verificar que WhatsApp ainda funciona
# (enviar mensagem real via WhatsApp)
```

## Opções de Prune

### Opção A: Archive (Recomendado — não deleta nada)

Mover repo antigo para `_archive/` e fazer readonly.

```bash
cd /home/will

# Renomear repo antigo
mv whatsapp-rag whatsapp-rag-legacy-archive

# Criar symlink ou documenting para referência
echo "Legacy archived: whatsapp-rag-legacy-archive" > whatsapp-rag/README-PRUNE.md
```

**Vantagem**: pode reverter qualquer momento
**Desvantagem**: ocupa espaço em disco

### Opção B: GitHub Archive (baixo custo)

Criar release no GitHub e arquivar.

```bash
cd /home/will/whatsapp-rag

# Criar release no GitHub (não no Gitea — offline)
gh release create legacy-before-clean-$(date +%Y%m%d) \
  --title "Legacy Archive — antes do clean v2" \
  --notes "Repositório legado arquivado. Novo repo: whatsapp-rag-clean"

#飞 Tornar repo readonly
gh repo edit zapprosite/whatsapp-rag --visibility private
# ou
gh repo edit zapprosite/whatsapp-rag --archived true
```

**Vantagem**: GitHub guarda histórico completo
**Desvantagem**: visibilidade alterada

### Opção C: Delete (NÃO RECOMENDADO sem backup verificado)

Apagar repo antigo após todas as verificações acima.

```bash
# SÓ FAZER SE:
# 1. Backup está verificado e acessível
# 2. Rollback foi testado
# 3. Clean está em produção há pelo menos 72h sem incidentes
# 4. William aprovou explicitamente

cd /home/will
rm -rf whatsapp-rag

# NÃO FAZER ISTO SEM BACKUP
# rm -rf ~/backups/whatsapp-rag-legacy-YYYYMMDD.tar.gz
```

## Após Prune

### Cleanup de artefatos órfãos

```bash
# Limpar containers e imagens do repo antigo
docker compose -f /home/will/whatsapp-rag/docker-compose.yml down 2>/dev/null
docker image prune -f --filter "reference=*:whatsapp-rag*"

# Verificar que não há dangling volumes
docker volume ls | grep whatsapp
```

### Atualizar documentação

```markdown
# No novo repo (whatsapp-rag-clean), adicionar:

## Histórico
- Repo anterior: [link para legacy archive ou release]
- Migrado em: YYYYMMDD
- Motivo: clean v2 com pipeline determinístico
- Backup: ~/backups/whatsapp-rag-legacy-YYYYMMDD.tar.gz
```

## Rollback de Emergência

Se algo der errado com o prune:

```bash
# 1. Extrair backup
tar -xzf ~/backups/whatsapp-rag-legacy-YYYYMMDD.tar.gz -C /home/will/

# 2. Subir antigo
cd /home/will/whatsapp-rag
docker compose up -d

# 3. Verificar
curl http://localhost:8000/health
```

## Checklist Final

- [ ] Backup criado e verificado
- [ ] Commit taggeado no repo antigo
- [ ] Rollback testado
- [ ] .env preservado fora do git
- [ ] Evolution API aponta para novo serviço
- [ ] William aprovou
- [ ] Prune executado (archive/delete)
- [ ] Documentação atualizada