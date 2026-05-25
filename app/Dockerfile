FROM python:3.11-slim
WORKDIR /app

# libatomic1 para Prisma CLI + openssh-client para tunel PC1 + ffmpeg para WAV→OGG OPUS (WhatsApp)
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 openssh-client ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código e schema
COPY app/ /app/
COPY agent_graph/ /app/agent_graph/
COPY knowledge/ /app/knowledge/
COPY qdrant/ /app/qdrant/
COPY prisma/ /app/prisma/

# Gera client Prisma (não precisa de banco real, só do schema)
ENV DATABASE_URL=postgresql://x:x@localhost:5432/x
RUN prisma generate --schema prisma/schema.prisma

ENV PYTHONPATH=/app
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
