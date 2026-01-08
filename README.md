# Gerador de PR e Release Notes

Ferramenta local em Python para gerar descricoes de Pull Requests e Release Notes a partir de um repositorio Git.

## Requisitos
- Python 3.10+
- Ollama rodando localmente

## Instalacao
```
python -m pip install -r requirements.txt
```

## Uso rapido
```
python gerador.py /caminho/para/repo --range v1.0..v1.1
```

Saidas padrao em `out/`:
- `out/pr.md`
- `out/release.md`
- `out/commits.json`
- `out/conventions.md`

## Configuracao
Use `config.default.json` como base e passe com `--config`.

## Dominio (POC)
A etapa de definicao de dominio reutiliza a POC em `preencher_dominio.py` via `domain_step.py`.
