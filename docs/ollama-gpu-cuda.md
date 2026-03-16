# Ollama Local com GPU CUDA

Guia para configurar o Ollama instalado localmente para executar inferencia nos nucleos CUDA da GPU NVIDIA, em vez da CPU.

Rodar o modelo na GPU reduz drasticamente o tempo de geracao: modelos de 7-9B que levam 2-5 minutos na CPU costumam responder em 10-30 segundos numa GPU com 8 GB VRAM.

---

## Pre-requisitos

| Requisito | Verificacao |
|-----------|-------------|
| GPU NVIDIA (Turing+, serie 20xx ou superior recomendado) | `nvidia-smi` |
| Driver NVIDIA atualizado (>=525 recomendado) | `nvidia-smi` |
| CUDA Toolkit instalado | `nvcc --version` |
| Ollama instalado localmente | `ollama --version` |

> GPUs mais antigas (Maxwell, Pascal, Volta) funcionam, mas podem ter suporte limitado a quantizacoes recentes.

---

## 1. Verificar driver e CUDA

```bash
nvidia-smi
```

Saida esperada (exemplo):

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 535.104    Driver Version: 535.104    CUDA Version: 12.2        |
+-----------------------------------------------------------------------------+
| GPU  Name         Temp  Perf  Pwr:Usage/Cap  Memory-Usage  GPU-Util        |
|   0  RTX 3070     42C   P8    15W / 220W     512MiB / 8192MiB  0%          |
+-----------------------------------------------------------------------------+
```

Se o comando falhar, instale ou atualize o driver NVIDIA antes de continuar.

---

## 2. O Ollama detecta a GPU automaticamente

Ao instalar o Ollama no Windows ou Linux com driver NVIDIA presente, **ele ja usa a GPU por padrao** — nao e necessaria nenhuma configuracao adicional.

Ao iniciar o servidor, o log confirma o backend em uso:

```bash
ollama serve
```

Procure por linhas como:

```
time=... level=INFO source=gpu.go msg="inference compute" id=GPU-... library=cuda ...
```

Se aparecer `library=cpu`, a GPU nao foi detectada — veja a secao de troubleshooting abaixo.

---

## 3. Confirmar uso da GPU durante inferencia

Com o servidor rodando, execute o modelo e em outro terminal observe a GPU:

```bash
# Terminal 1 — rodar uma inferencia de teste
ollama run qwen2.5:7b "Ola, me explique o que e CUDA em uma frase."

# Terminal 2 — monitorar GPU em tempo real
nvidia-smi dloop 1
```

Durante a geracao, a coluna `GPU-Util` deve subir (tipicamente 60-100%) e `Memory-Usage` deve refletir o modelo carregado.

---

## 4. Variaveis de ambiente uteis

O Ollama expoe variaveis para ajuste fino do uso de GPU:

### Selecionar GPUs especificas (multi-GPU)

```bash
# Usar apenas a GPU de indice 0
CUDA_VISIBLE_DEVICES=0 ollama serve

# Usar GPUs 0 e 1
CUDA_VISIBLE_DEVICES=0,1 ollama serve
```

### Forcar CPU (desabilitar GPU)

```bash
OLLAMA_INTEL_GPU=0 CUDA_VISIBLE_DEVICES="" ollama serve
```

Util para comparar performance ou quando a VRAM e insuficiente para o modelo.

### Numero de camadas na GPU

O Ollama carrega automaticamente o maximo de camadas que cabem na VRAM. Para forcar um numero especifico (avancado):

```bash
OLLAMA_NUM_GPU=999 ollama serve   # tenta colocar tudo na GPU
OLLAMA_NUM_GPU=20  ollama serve   # apenas 20 camadas na GPU, resto na CPU
```

---

## 5. Requisitos de VRAM por modelo

| Modelo | Quantizacao padrao | VRAM minima estimada |
|--------|--------------------|----------------------|
| qwen2.5:7b | Q4_K_M | ~5 GB |
| qwen2.5:9b / qwen3.5:9b | Q4_K_M | ~6 GB |
| qwen2.5:14b | Q4_K_M | ~9 GB |
| qwen2.5:32b | Q4_K_M | ~20 GB |

Se a VRAM for insuficiente para o modelo inteiro, o Ollama divide automaticamente entre GPU e RAM (modo hibrido), o que e mais lento mas ainda mais rapido do que CPU puro.

---

## 6. Troubleshooting

### `library=cpu` no log do ollama serve

**Causa mais comum**: driver NVIDIA nao encontrado ou versao incompativel com o CUDA embutido no Ollama.

```bash
# Verificar versao do driver
nvidia-smi --query-gpu=driver_version --format=csv,noheader

# Atualizar driver via Windows Update ou baixar em nvidia.com/drivers
```

### Erro `CUDA error: no kernel image is available`

GPU muito antiga para a versao de CUDA usada pelo Ollama. Tente instalar uma versao anterior do Ollama ou use uma quantizacao diferente.

### Modelo lento mesmo com GPU detectada

Verifique se o modelo esta sendo carregado totalmente na GPU:

```bash
ollama ps
```

A saida mostra o modelo ativo e o percentual de camadas na GPU:

```
NAME            ID       SIZE    PROCESSOR    UNTIL
qwen2.5:7b      abc123   5.2 GB  100% GPU     4 minutes from now
```

Se `PROCESSOR` mostrar `CPU` ou percentual baixo, a VRAM pode estar esgotada — considere um modelo menor ou quantizacao mais agressiva (ex: `Q2_K`).

---

## 7. Integrar com o PullNotes

Nenhuma alteracao no PullNotes e necessaria. Basta garantir que:

1. O Ollama esta rodando com GPU (`ollama serve`)
2. O campo `ollama_base_url` no `config.default.json` aponta para `http://localhost:11434`
3. O campo `model` corresponde ao modelo baixado (ex: `qwen2.5:7b`)

```json
{
  "ollama_base_url": "http://localhost:11434",
  "model": "qwen2.5:7b"
}
```

A aceleracao por GPU e transparente — o PullNotes simplesmente chamara o Ollama mais rapido.
