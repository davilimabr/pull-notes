#!/usr/bin/env bash
# =============================================================================
# Setup PullNotes com Ollama via Docker Compose
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$SCRIPT_DIR/config.default.json"

# --- Detectar Python --------------------------------------------------------
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "[ERRO] Python nao encontrado. Instale Python 3.10+ antes de continuar."
    exit 1
fi

echo "[INFO] Usando Python: $($PYTHON --version)"

# --- Verificar Docker --------------------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "[ERRO] Docker nao encontrado. Instale Docker antes de continuar:"
    echo "       https://docs.docker.com/get-docker/"
    exit 1
fi

echo "[INFO] Docker encontrado: $(docker --version)"

# --- Extrair modelo do config ------------------------------------------------
MODEL=$($PYTHON -c "
import json, sys
try:
    cfg = json.load(open('$CONFIG'))
    print(cfg.get('llm_model', 'qwen2.5:14b'))
except Exception as e:
    print('qwen2.5:14b', file=sys.stderr)
    print('qwen2.5:14b')
")

echo "[INFO] Modelo configurado: $MODEL"

# --- Subir Ollama via Docker Compose -----------------------------------------
cd "$SCRIPT_DIR"
export OLLAMA_MODEL="$MODEL"

echo "[INFO] Iniciando Ollama via Docker Compose (modelo: $MODEL)..."
docker compose up -d

echo "[INFO] Aguardando Ollama ficar saudavel e o modelo ser baixado..."
echo "[INFO] Acompanhe o progresso com: docker compose logs -f ollama-model-pull"

# Aguardar o servico de pull do modelo terminar
docker compose wait ollama-model-pull 2>/dev/null || \
    docker compose logs -f ollama-model-pull

echo "[INFO] Ollama pronto."

# --- Instalar pacote Python --------------------------------------------------
echo "[INFO] Instalando pacote pullnotes..."
$PYTHON -m pip install --force-reinstall .

echo ""
echo "============================================="
echo " Setup concluido!"
echo " Ollama rodando em http://localhost:11434"
echo " Modelo: $MODEL"
echo ""
echo " Uso:"
echo "   pullnotes /caminho/repo --config config.default.json --generate both"
echo "============================================="
