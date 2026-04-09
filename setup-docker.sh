#!/usr/bin/env bash
# =============================================================================
# Setup PullNotes com Ollama via Docker Compose
# =============================================================================
set -euo pipefail
trap 'echo ""; echo "[ERRO] Setup falhou."; read -n 1 -s -r -p "Pressione qualquer tecla para fechar..."; echo ""' ERR

# --- Solicitar caminho do config ---------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

while true; do
    read -r -p "Informe o caminho do arquivo de configuracao [Enter para usar config.default.json na pasta do script]: " CONFIG_INPUT
    if [ -z "$CONFIG_INPUT" ]; then
        CONFIG="$SCRIPT_DIR/config.default.json"
    else
        CONFIG="${CONFIG_INPUT//\\//}"
    fi
    if [ -f "$CONFIG" ]; then
        break
    fi
    echo "[ERRO] Arquivo nao encontrado: $CONFIG. Tente novamente."
done

echo "[INFO] Usando config: $CONFIG"

# --- Detectar Python --------------------------------------------------------
PYTHONS=()
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHONS+=("$cmd")
    fi
done

if [ ${#PYTHONS[@]} -eq 0 ]; then
    echo "[ERRO] Python nao encontrado. Instale Python 3.10+ antes de continuar."
    exit 1
fi

if [ ${#PYTHONS[@]} -eq 1 ]; then
    PYTHON="${PYTHONS[0]}"
    echo "[INFO] Usando Python: $($PYTHON --version)"
else
    echo "[INFO] Multiplas instalacoes de Python encontradas:"
    for i in "${!PYTHONS[@]}"; do
        VERSION=$(${PYTHONS[$i]} --version 2>&1)
        LOCATION=$(command -v "${PYTHONS[$i]}")
        echo "  $((i+1))) $VERSION ($LOCATION)"
    done
    while true; do
        read -r -p "Selecione o Python desejado [1-${#PYTHONS[@]}]: " choice
        if [[ "$choice" =~ ^[0-9]+$ ]] && [ "$choice" -ge 1 ] && [ "$choice" -le ${#PYTHONS[@]} ]; then
            PYTHON="${PYTHONS[$((choice-1))]}"
            break
        fi
        echo "[ERRO] Opcao invalida."
    done
    echo "[INFO] Usando Python: $($PYTHON --version)"
fi

# --- Verificar Docker --------------------------------------------------------
if ! command -v docker &>/dev/null; then
    echo "[ERRO] Docker nao encontrado. Instale Docker antes de continuar:"
    echo "       https://docs.docker.com/get-docker/"
    exit 1
fi

echo "[INFO] Docker encontrado: $(docker --version)"

# --- Extrair modelo do config e selecionar -----------------------------------
CONFIGURED_MODEL=$($PYTHON -c "
import json, sys
try:
    cfg = json.load(open('$CONFIG'))
    print(cfg.get('llm_model', 'qwen2.5:14b'))
except Exception as e:
    print('qwen2.5:14b', file=sys.stderr)
    print('qwen2.5:14b')
")

SUGGESTED_MODELS=("qwen2.5:7b (4.7GB)" "qwen2.5:14b (9GB)" "qwen2.5:32b (20GB)")
SUGGESTED_NAMES=("qwen2.5:7b" "qwen2.5:14b" "qwen2.5:32b")

echo ""
echo "[INFO] Modelo configurado atualmente: $CONFIGURED_MODEL"
echo ""
echo "Deseja baixar o modelo '$CONFIGURED_MODEL' ou escolher um dos modelos sugeridos?"
echo "  1) Manter e baixar '$CONFIGURED_MODEL'"
for i in "${!SUGGESTED_MODELS[@]}"; do
    echo "  $((i+2))) ${SUGGESTED_MODELS[$i]}"
done

MAX_OPT=$((${#SUGGESTED_MODELS[@]} + 1))
while true; do
    read -r -p "Selecione uma opcao [1-$MAX_OPT]: " model_choice
    if [[ "$model_choice" =~ ^[0-9]+$ ]] && [ "$model_choice" -ge 1 ] && [ "$model_choice" -le "$MAX_OPT" ]; then
        break
    fi
    echo "[ERRO] Opcao invalida."
done

if [ "$model_choice" -eq 1 ]; then
    MODEL="$CONFIGURED_MODEL"
else
    MODEL="${SUGGESTED_NAMES[$((model_choice-2))]}"
    echo "[INFO] Atualizando modelo no arquivo de configuracao para '$MODEL'..."
    $PYTHON -c "
import json
cfg = json.load(open('$CONFIG'))
cfg['llm_model'] = '$MODEL'
if 'domain' in cfg and 'model' in cfg['domain']:
    cfg['domain']['model'] = '$MODEL'
json.dump(cfg, open('$CONFIG', 'w'), indent=2, ensure_ascii=False)
print('[INFO] Configuracao atualizada.')
"
fi

echo "[INFO] Modelo selecionado: $MODEL"

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
echo "   pullnotes /caminho/repo --config $CONFIG --generate both"
echo "============================================="
echo ""
read -n 1 -s -r -p "Pressione qualquer tecla para fechar..."
echo ""
