"""Testes ponta a ponta sem mocks.

Estes testes verificam o pipeline real usando Git e sistema de arquivos
de verdade, sem nenhum mock ou patch.

Grupos:
- TestRealGitPipeline   : coleta de dados Git + processamento + exportação (sem LLM)
- TestFullWorkflowWithLLM : run_workflow() completo com Ollama real
                            (pulado se Ollama não estiver rodando)
- TestWorkflowEdgeCases : cenários de erro que falham antes de qualquer chamada LLM
"""

from __future__ import annotations

import json
import subprocess
from argparse import Namespace
from pathlib import Path

import pytest

from pullnotes.adapters.filesystem import get_repository_name
from pullnotes.adapters.subprocess import run_git
from pullnotes.domain.services.aggregation import (
    build_convention_report,
    classify_commit,
    compute_importance,
    group_commits_by_type,
)
from pullnotes.domain.services.data_collection import get_commits
from pullnotes.domain.services.export import (
    create_output_structure,
    export_commits,
    export_convention_report,
)
from pullnotes.workflows.sync import run_workflow


# ---------------------------------------------------------------------------
# Helpers de repositório Git
# ---------------------------------------------------------------------------

def _init_git_repo(path: Path) -> None:
    """Inicializa repositório git com identidade de teste."""
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(path), "config", "user.name", "E2E Tester"],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(path), "config", "user.email", "e2e@test.com"],
        check=True, capture_output=True,
    )


def _commit(repo: Path, filename: str, content: str, message: str) -> None:
    """Escreve um arquivo e cria um commit real."""
    target = repo / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", filename],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", message],
        check=True, capture_output=True,
    )


def _ollama_available() -> bool:
    """Retorna True se o Ollama estiver acessível em localhost:11434."""
    try:
        import urllib.request
        with urllib.request.urlopen("http://localhost:11434", timeout=2) as resp:
            return resp.status < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def real_repo(tmp_path):
    """Repositório git real com commits convencionais e não-convencionais."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_git_repo(repo)
    _commit(repo, "README.md", "# Project\n", "feat: initial project setup")
    _commit(repo, "src/auth.py", "def login(user, pwd): pass\n", "feat: add login endpoint")
    _commit(repo, "src/auth.py", "def login(u, p): return u == 'admin'\n", "fix: password validation")
    _commit(repo, "docs/api.md", "# API\n## Endpoints\n", "docs: add API documentation")
    _commit(repo, "src/auth.py", "def login(u, p): return bool(p)\n", "refactor: simplify auth logic")
    _commit(repo, "misc.txt", "misc change\n", "updated some stuff")  # não-convencional
    return repo


@pytest.fixture
def e2e_config(tmp_path, sample_config):
    """Arquivo de config apontando output para diretório temporário."""
    cfg = dict(sample_config)
    cfg["output"] = {"dir": str(tmp_path / "output")}
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Marker para testes que requerem Ollama
# ---------------------------------------------------------------------------

ollama_required = pytest.mark.skipif(
    not _ollama_available(),
    reason="Ollama não está rodando em localhost:11434",
)


# ---------------------------------------------------------------------------
# TestRealGitPipeline — sem LLM, apenas Git + filesystem reais
# ---------------------------------------------------------------------------

class TestRealGitPipeline:
    """Pipeline completo de dados usando Git e filesystem reais, sem LLM."""

    def test_get_commits_retorna_commits_reais(self, real_repo):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)

        assert len(commits) == 6
        subjects = [c.subject for c in commits]
        assert "feat: initial project setup" in subjects
        assert "fix: password validation" in subjects
        assert "updated some stuff" in subjects

    def test_cada_commit_tem_sha_e_autor_corretos(self, real_repo):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)

        for c in commits:
            assert len(c.sha) == 40, f"SHA deve ter 40 chars: {c.sha!r}"
            assert c.author_name == "E2E Tester"
            assert c.author_email == "e2e@test.com"

    def test_commits_tem_diff_preenchido(self, real_repo):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)

        # O commit inicial pode ter diff vazio; os demais devem ter
        with_diff = [c for c in commits if c.diff.strip()]
        assert len(with_diff) >= 4

    def test_commits_tem_diff_anchors_populados(self, real_repo):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)

        with_anchors = [c for c in commits if c.diff_anchors and c.diff_anchors.files_changed]
        assert len(with_anchors) >= 3

    def test_diff_anchors_referenciam_arquivos_reais(self, real_repo):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)

        # O commit de auth.py deve referenciar o arquivo nos anchors
        auth_commits = [c for c in commits if "src/auth.py" in c.files]
        for c in auth_commits:
            if c.diff_anchors and c.diff_anchors.files_changed:
                assert "src/auth.py" in c.diff_anchors.files_changed

    def test_classificacao_de_commits_reais(self, real_repo, sample_config):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )

        by_subject = {c.subject: (c.change_type, c.is_conventional) for c in commits}
        assert by_subject["feat: initial project setup"] == ("feat", True)
        assert by_subject["feat: add login endpoint"] == ("feat", True)
        assert by_subject["fix: password validation"] == ("fix", True)
        assert by_subject["docs: add API documentation"] == ("docs", True)
        assert by_subject["refactor: simplify auth logic"] == ("refactor", True)
        assert by_subject["updated some stuff"] == ("other", False)

    def test_commit_nao_convencional_detectado(self, real_repo, sample_config):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )

        non_conv = [c for c in commits if not c.is_conventional]
        assert len(non_conv) == 1
        assert non_conv[0].subject == "updated some stuff"

    def test_pontuacao_de_importancia_retorna_valores_validos(self, real_repo, sample_config):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )
            c.importance_score, c.importance_band = compute_importance(c, sample_config)

        for c in commits:
            assert isinstance(c.importance_score, float)
            assert c.importance_band in {"low", "medium", "high", "critical"}

    def test_agrupamento_por_tipo_inclui_todos_os_tipos(self, real_repo, sample_config):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )
            c.importance_score, c.importance_band = compute_importance(c, sample_config)

        groups = dict(group_commits_by_type(commits, sample_config))
        assert "feat" in groups
        assert "fix" in groups
        assert "docs" in groups
        assert "refactor" in groups
        assert "other" in groups

    def test_relatorio_de_convencao_conta_commits_corretos(self, real_repo, sample_config):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )

        report = build_convention_report(commits)

        assert "Total commits: 6" in report
        assert "Others: 1" in report

    def test_export_de_commits_gera_json_valido(self, real_repo, tmp_path, sample_config):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )
            c.importance_score, c.importance_band = compute_importance(c, sample_config)

        paths = create_output_structure(tmp_path / "out", "e2e-repo")
        out_file = export_commits(commits, paths["utils"])

        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert len(data) == 6
        required_keys = {"sha", "subject", "change_type", "importance_band", "additions", "deletions"}
        for entry in data:
            assert required_keys <= entry.keys()

    def test_export_de_relatorio_de_convencao_cria_arquivo(self, real_repo, tmp_path, sample_config):
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )

        report = build_convention_report(commits)
        paths = create_output_structure(tmp_path / "out", "e2e-repo")
        out_file = export_convention_report(report, paths["utils"])

        assert out_file.exists()
        text = out_file.read_text(encoding="utf-8")
        assert "Total commits: 6" in text

    def test_estrutura_de_diretorios_de_saida_criada(self, tmp_path):
        paths = create_output_structure(tmp_path / "out", "meu-repo")

        assert paths["prs"].exists()
        assert paths["releases"].exists()
        assert paths["utils"].exists()

    def test_filtro_por_revision_range_retorna_subset(self, tmp_path, sample_config):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        _commit(repo, "a.py", "a = 1\n", "feat: feature alpha")
        subprocess.run(
            ["git", "-C", str(repo), "tag", "v1.0"],
            check=True, capture_output=True,
        )
        _commit(repo, "b.py", "b = 2\n", "feat: feature beta")
        _commit(repo, "c.py", "c = 3\n", "fix: fix gamma")

        commits = get_commits(repo, revision_range="v1.0..HEAD", since=None, until=None)
        subjects = [c.subject for c in commits]

        assert "feat: feature beta" in subjects
        assert "fix: fix gamma" in subjects
        assert "feat: feature alpha" not in subjects

    def test_filtro_since_retorna_apenas_commits_recentes(self, tmp_path):
        from datetime import date, timedelta

        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "x.py", "x = 1\n", "feat: commit de hoje")

        # git --since usa semântica exclusiva para a data exata;
        # usar ontem garante que commits feitos hoje sejam incluídos.
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        commits = get_commits(repo, revision_range=None, since=yesterday, until=None)

        assert len(commits) >= 1
        assert any("commit de hoje" in c.subject for c in commits)

    def test_get_repository_name_retorna_nome_do_diretorio(self, real_repo):
        name = get_repository_name(real_repo)
        assert name == "repo"

    def test_run_git_lanca_excecao_em_comando_invalido(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)

        with pytest.raises(RuntimeError):
            run_git(repo, ["log", "--flag-que-nao-existe-xyz"])

    def test_pipeline_completo_coleta_classifica_exporta(self, real_repo, tmp_path, sample_config):
        """Pipeline ponta a ponta: coleta Git → classifica → pontua → exporta."""
        # 1. Coleta
        commits = get_commits(real_repo, revision_range=None, since=None, until=None)
        assert len(commits) == 6

        # 2. Classifica
        for c in commits:
            c.change_type, c.is_conventional = classify_commit(
                c.subject, sample_config["commit_types"]
            )

        # 3. Pontua
        for c in commits:
            c.importance_score, c.importance_band = compute_importance(c, sample_config)

        # 4. Agrupa
        groups = dict(group_commits_by_type(commits, sample_config))
        assert "feat" in groups and len(groups["feat"]) == 2

        # 5. Relatório de convenção
        report = build_convention_report(commits)
        assert "Total commits: 6" in report

        # 6. Exporta
        paths = create_output_structure(tmp_path / "out", "e2e-repo")
        out_json = export_commits(commits, paths["utils"])
        out_report = export_convention_report(report, paths["utils"])

        assert out_json.exists()
        assert out_report.exists()
        data = json.loads(out_json.read_text(encoding="utf-8"))
        assert len(data) == 6


# ---------------------------------------------------------------------------
# TestFullWorkflowWithLLM — requer Ollama rodando
# ---------------------------------------------------------------------------

@ollama_required
class TestFullWorkflowWithLLM:
    """Testes de workflow completo com LLM real via Ollama.

    Pulados automaticamente se Ollama não estiver acessível em localhost:11434.
    """

    def _args(self, repo, config_file, output_dir, generate="pr", **overrides):
        defaults = Namespace(
            repo=str(repo),
            revision_range=None,
            since=None,
            until=None,
            config=str(config_file),
            generate=generate,
            version="v1.0.0",
            output_dir=str(output_dir),
            refresh_domain=True,  # evita chamada LLM de domain profile nos testes
            model="",
            no_llm=False,
            debug=False,
        )
        for k, v in overrides.items():
            setattr(defaults, k, v)
        return defaults

    def test_gera_pr_com_conteudo_markdown(self, real_repo, e2e_config, tmp_path):
        out = tmp_path / "output"
        args = self._args(real_repo, e2e_config, out, generate="pr")

        result = run_workflow(args)

        assert result == 0
        pr_files = [f for f in out.rglob("*.md") if "prs" in str(f)]
        assert len(pr_files) >= 1
        content = pr_files[0].read_text(encoding="utf-8")
        assert content.startswith("#")  # deve começar com título markdown

    def test_pr_contem_mudancas_dos_commits(self, real_repo, e2e_config, tmp_path):
        out = tmp_path / "output"
        args = self._args(real_repo, e2e_config, out, generate="pr")

        run_workflow(args)

        pr_files = [f for f in out.rglob("*.md") if "prs" in str(f)]
        content = pr_files[0].read_text(encoding="utf-8")
        # O PR deve mencionar funcionalidades ou ajustes (feat/fix)
        content_lower = content.lower()
        assert "funcionalidades" in content_lower or "ajustes" in content_lower or "feat" in content_lower

    def test_gera_release_com_conteudo_markdown(self, real_repo, e2e_config, tmp_path):
        out = tmp_path / "output"
        args = self._args(real_repo, e2e_config, out, generate="release")

        result = run_workflow(args)

        assert result == 0
        release_files = [f for f in out.rglob("*.md") if "releases" in str(f)]
        assert len(release_files) >= 1
        content = release_files[0].read_text(encoding="utf-8")
        assert "v1.0.0" in content

    def test_gera_pr_e_release_juntos(self, real_repo, e2e_config, tmp_path):
        out = tmp_path / "output"
        args = self._args(real_repo, e2e_config, out, generate="both")

        result = run_workflow(args)

        assert result == 0
        pr_files = [f for f in out.rglob("*.md") if "prs" in str(f)]
        release_files = [f for f in out.rglob("*.md") if "releases" in str(f)]
        assert len(pr_files) >= 1
        assert len(release_files) >= 1

    def test_workflow_cria_commit_json_com_dados_reais(self, real_repo, e2e_config, tmp_path):
        out = tmp_path / "output"
        args = self._args(real_repo, e2e_config, out, generate="pr")

        run_workflow(args)

        commit_jsons = list(out.rglob("commit.json"))
        assert len(commit_jsons) == 1
        data = json.loads(commit_jsons[0].read_text(encoding="utf-8"))
        assert len(data) == 6
        shas = {e["sha"] for e in data}
        assert len(shas) == 6  # todos SHAs únicos

    def test_workflow_cria_relatorio_de_convencao(self, real_repo, e2e_config, tmp_path):
        out = tmp_path / "output"
        args = self._args(real_repo, e2e_config, out, generate="pr")

        run_workflow(args)

        conv_files = list(out.rglob("conventions.md"))
        assert len(conv_files) == 1
        text = conv_files[0].read_text(encoding="utf-8")
        assert "Total commits: 6" in text

    def test_workflow_com_revision_range(self, tmp_path, e2e_config):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "a.py", "a = 1\n", "feat: feature alpha")
        subprocess.run(
            ["git", "-C", str(repo), "tag", "v1.0"],
            check=True, capture_output=True,
        )
        _commit(repo, "b.py", "b = 2\n", "feat: feature beta")
        _commit(repo, "c.py", "c = 3\n", "fix: fix gamma")

        out = tmp_path / "output"
        args = Namespace(
            repo=str(repo),
            revision_range="v1.0..HEAD",
            since=None, until=None,
            config=str(e2e_config),
            generate="pr",
            version="",
            output_dir=str(out),
            refresh_domain=True,
            model="",
            no_llm=False,
            debug=False,
        )

        result = run_workflow(args)
        assert result == 0

        commit_jsons = list(out.rglob("commit.json"))
        data = json.loads(commit_jsons[0].read_text(encoding="utf-8"))
        subjects = [d["subject"] for d in data]
        assert "feat: feature beta" in subjects
        assert "fix: fix gamma" in subjects
        assert "feat: feature alpha" not in subjects


# ---------------------------------------------------------------------------
# TestWorkflowEdgeCases — erros que ocorrem antes de qualquer chamada LLM
# ---------------------------------------------------------------------------

class TestWorkflowEdgeCases:
    """Casos de erro detectados antes das chamadas LLM — sem Ollama necessário."""

    def test_repositorio_inexistente_lanca_systemexit(self, tmp_path, e2e_config):
        args = Namespace(
            repo=str(tmp_path / "nao-existe"),
            revision_range=None, since=None, until=None,
            config=str(e2e_config),
            generate="pr", version="",
            output_dir="",
            refresh_domain=False, model="", no_llm=True, debug=False,
        )
        with pytest.raises(SystemExit):
            run_workflow(args)

    def test_range_sem_commits_lanca_systemexit(self, tmp_path, e2e_config):
        repo = tmp_path / "repo"
        repo.mkdir()
        _init_git_repo(repo)
        _commit(repo, "f.py", "x = 1\n", "feat: único commit")
        subprocess.run(
            ["git", "-C", str(repo), "tag", "v9.0"],
            check=True, capture_output=True,
        )

        args = Namespace(
            repo=str(repo),
            revision_range="v9.0..HEAD",
            since=None, until=None,
            config=str(e2e_config),
            generate="pr", version="",
            output_dir=str(tmp_path / "out"),
            refresh_domain=False, model="", no_llm=True, debug=False,
        )
        with pytest.raises(SystemExit, match="No commits"):
            run_workflow(args)

    def test_config_invalida_lanca_erro(self, tmp_path, real_repo):
        """Config sem campos obrigatórios é rejeitada antes do LLM."""
        bad_config = tmp_path / "bad_config.json"
        bad_config.write_text("{}", encoding="utf-8")

        args = Namespace(
            repo=str(real_repo),
            revision_range=None, since=None, until=None,
            config=str(bad_config),
            generate="pr", version="",
            output_dir=str(tmp_path / "out"),
            refresh_domain=False, model="", no_llm=True, debug=False,
        )
        with pytest.raises((SystemExit, KeyError, Exception)):
            run_workflow(args)
