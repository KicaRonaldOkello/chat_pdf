#!/bin/bash
set -euxo pipefail
exec > >(tee /var/log/user-data.log | logger -t user-data -s 2>/dev/console) 2>&1

export HOME=/root
dnf update -y
dnf install -y docker
systemctl enable --now docker

# Qdrant
docker run -d --name qdrant --restart unless-stopped \
  -p 6333:6333 -p 6334:6334 \
  -v qdrant_data:/qdrant/storage \
  qdrant/qdrant:v1.17.1

# Ollama
curl -fsSL https://ollama.com/install.sh | sh
systemctl enable ollama
systemctl start ollama
sleep 5
%{ for m in ollama_models ~}
ollama pull ${m} || true
%{ endfor ~}

echo "data plane user_data complete" | logger -t user-data
