#!/usr/bin/env bash
# =============================================================================
# EXEMPLOS DE USO — pullnotes
# =============================================================================
# Sintaxe geral:
#   python -m pullnotes [repo] --config <arquivo.json> [opções]
#
# Argumentos posicionais:
#   repo          Caminho para o repositório Git (padrão: diretório atual ".")
#
# Opções de filtro de commits (pelo menos uma é necessária para delimitar o range):
#   --range       Range de revisão Git (ex: v1.0..v1.1, branch1..branch2)
#   --since       Data de início (ex: 2024-01-01)
#   --until       Data de fim (ex: 2024-12-31)
#
# Opções de geração:
#   --generate    O que gerar: "pr" | "release" | "both" (padrão: both)
#   --version     Rótulo da versão para o release notes (ex: 2.0.0)
#   --output-dir  Sobrescreve o diretório de saída definido no config
#
# Opções de LLM:
#   --model       Sobrescreve o modelo LLM definido no config (ex: llama3:8b)
#   --no-llm      Pula resumos por LLM; usa os subjects dos commits diretamente
#
# Outros:
#   --refresh-domain  Reconstrói o perfil de domínio do repositório
#   --debug           Ativa logs detalhados (nível DEBUG)
# =============================================================================


# -----------------------------------------------------------------------------
# 1. USO MÍNIMO — repositório atual, range por revisão
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range v1.0..v1.1


# -----------------------------------------------------------------------------
# 2. REPOSITÓRIO EXPLÍCITO — caminho passado como argumento posicional
# -----------------------------------------------------------------------------
python -m pullnotes /caminho/para/meu-repo --config config.default.json --range main..feature/minha-feature


# -----------------------------------------------------------------------------
# 3. FILTRO POR DATA — commits de um período específico
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --since 2024-01-01 --until 2024-03-31


# -----------------------------------------------------------------------------
# 4. FILTRO POR DATA (apenas since) — do dia até hoje
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --since 2024-06-01


# -----------------------------------------------------------------------------
# 5. FILTRO POR DATA + RANGE — combina range de branches com janela de datas
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json \
  --range development..master \
  --since 2024-01-01 \
  --until 2024-12-31


# -----------------------------------------------------------------------------
# 6. GERAR APENAS PR DESCRIPTION
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range main..minha-branch --generate pr


# -----------------------------------------------------------------------------
# 7. GERAR APENAS RELEASE NOTES (com rótulo de versão)
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range v1.0..v2.0 --generate release --version 2.0.0


# -----------------------------------------------------------------------------
# 8. GERAR AMBOS (comportamento padrão) COM VERSÃO EXPLÍCITA
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range v1.0..v2.0 --generate both --version 2.0.0


# -----------------------------------------------------------------------------
# 9. SOBRESCREVER DIRETÓRIO DE SAÍDA
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range main..release/v3 --output-dir /tmp/notas-release


# -----------------------------------------------------------------------------
# 10. SOBRESCREVER MODELO LLM
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range main..release/v3 --model llama3:8b


# -----------------------------------------------------------------------------
# 11. PULAR LLM — usar subjects dos commits sem resumo por IA
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range main..release/v3 --no-llm


# -----------------------------------------------------------------------------
# 12. RECONSTRUIR PERFIL DE DOMÍNIO — reanalisa o repositório
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range main..release/v3 --refresh-domain


# -----------------------------------------------------------------------------
# 13. MODO DEBUG — logs detalhados no console
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json --range main..release/v3 --debug


# -----------------------------------------------------------------------------
# 14. COMBINAÇÃO COMPLETA — todos os parâmetros juntos
# -----------------------------------------------------------------------------
python -m pullnotes C:\Users\Davi\repo\ytmdesktop `
  --range v1..v2 `
  --config config.default.json `
  --generate release `
  --version 2.0.0 `
  --output-dir C:\Users\Davi\Desktop\pull-notes `
  --refresh-domain



# -----------------------------------------------------------------------------
# 15. SEM LLM + SAÍDA CUSTOMIZADA + DEBUG
# -----------------------------------------------------------------------------
python -m pullnotes --config config.default.json \
  --range v2.0..v3.0 \
  --generate both \
  --version 3.0.0 \
  --output-dir ./saida \
  --no-llm \
  --debug
