"""Tests for AEGIS-1201/1208: .meld Writer."""

from __future__ import annotations

from pathlib import Path

from aegis.editor.domain_model import CodeOfConductInfo, DomainInfo, Role, RuleInfo
from aegis.editor.meld_writer import export_domain, write_deontic_meld, write_ontology_meld


def _make_domain() -> DomainInfo:
    return DomainInfo(
        id="test",
        name="test_domain",
        roles=[
            Role(id="agentA", name="agentA"),
            Role(id="agentB", name="agentB"),
        ],
        codes=[
            CodeOfConductInfo(id="TestCode", name="TestCode"),
        ],
        rules=[
            RuleInfo(
                id="r1",
                code="TestCode",
                agent_role="agentA",
                modality="FORBIDDEN",
                proposition="share classified",
            ),
            RuleInfo(
                id="r2",
                code="TestCode",
                agent_role="agentB",
                modality="PERMITTED",
                proposition="read public",
            ),
            RuleInfo(
                id="r3",
                code="",
                agent_role="agentA",
                modality="FORBIDDEN",
                proposition="delete records",
                defeasible=False,
            ),
        ],
    )


class TestMeldWriter:
    def test_write_ontology(self, tmp_path: Path) -> None:
        domain = _make_domain()
        path = tmp_path / "ontology.meld"
        write_ontology_meld(domain, path)

        content = path.read_text()
        assert "(aegis-schema-version 1)" in content
        assert "case" in content
        assert "agentA" in content
        assert "agentB" in content
        assert "genlPreds" in content

    def test_write_deontic(self, tmp_path: Path) -> None:
        domain = _make_domain()
        path = tmp_path / "deontic.meld"
        write_deontic_meld(domain, path)

        content = path.read_text()
        assert "(aegis-schema-version 1)" in content
        assert "forbiddenToDo-WRT TestCode agentA" in content
        assert "permittedToDo-WRT TestCode agentB" in content
        # Moral axiom (no code)
        assert "forbiddenToDo agentA" in content

    def test_export_creates_two_files(self, tmp_path: Path) -> None:
        domain = _make_domain()
        files = export_domain(domain, tmp_path / "output")
        assert len(files) == 2
        assert all(f.exists() for f in files)
        assert any("Ontology" in f.name for f in files)
        assert any("Deontic" in f.name for f in files)
