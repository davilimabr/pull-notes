#!/usr/bin/env bash
# =============================================================================
# Setup PullNotes com Ollama LOCAL (sem Docker)
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

# --- Instalar Ollama ---------------------------------------------------------
if command -v ollama &>/dev/null; then
    echo "[INFO] Ollama ja instalado: $(ollama --version)"
else
    echo "[INFO] Instalando Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
    echo "[INFO] Ollama instalado com sucesso."
fi

# --- Iniciar Ollama se nao estiver rodando -----------------------------------
if ! ollama list &>/dev/null 2>&1; then
    echo "[INFO] Iniciando servidor Ollama em background..."
    ollama serve &>/dev/null &
    sleep 3
fi

# --- Baixar modelo -----------------------------------------------------------
echo "[INFO] Baixando modelo '$MODEL' (pode levar alguns minutos)..."
ollama pull "$MODEL"
echo "[INFO] Modelo '$MODEL' disponivel."

# --- Instalar pacote Python --------------------------------------------------
echo "[INFO] Instalando pacote pullnotes..."
cd "$SCRIPT_DIR"
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
