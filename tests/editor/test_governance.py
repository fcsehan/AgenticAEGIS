"""Tests for AEGIS-1210: Regelwerk-Governance."""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.editor.governance import GovernanceError, GovernanceManager


class TestGovernanceManager:
    def test_get_or_create(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        gov = mgr.get_or_create("test")
        assert gov.domain_id == "test"
        assert gov.status == "Draft"

    def test_submit_for_review(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        gov = mgr.submit_for_review("test", "Ready for review")
        assert gov.status == "Review"
        assert gov.branch.startswith("review/test/")

    def test_cannot_submit_review_from_review(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        mgr.submit_for_review("test")
        with pytest.raises(GovernanceError, match="Review"):
            mgr.submit_for_review("test")

    def test_publish(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        mgr.submit_for_review("test")
        gov = mgr.publish("test", "1.0.0", "First release")
        assert gov.status == "Published"
        assert gov.current_version == "1.0.0"
        assert len(gov.versions) == 1
        assert gov.versions[0].tag == "test/v1.0.0"

    def test_cannot_publish_from_draft(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        with pytest.raises(GovernanceError, match="Review"):
            mgr.publish("test", "1.0.0")

    def test_version_history(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        mgr.submit_for_review("test")
        mgr.publish("test", "1.0.0")

        # Re-submit for another version
        mgr.submit_for_review("test", "v1.1")
        mgr.publish("test", "1.1.0", "Update")

        history = mgr.get_history("test")
        assert len(history) == 2
        assert history[0].version == "1.1.0"
        assert history[1].version == "1.0.0"

    def test_rollback(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        mgr.submit_for_review("test")
        mgr.publish("test", "1.0.0", "v1")
        mgr.submit_for_review("test")
        mgr.publish("test", "2.0.0", "v2")

        gov = mgr.rollback("test", "1.0.0")
        assert gov.current_version == "1.0.0"
        assert len(gov.versions) == 3  # v1, v2, rollback

    def test_rollback_unknown_version(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        with pytest.raises(GovernanceError, match="not found"):
            mgr.rollback("test", "99.0.0")

    def test_to_dict(self, tmp_path: Path) -> None:
        mgr = GovernanceManager(tmp_path)
        mgr.get_or_create("test")
        mgr.submit_for_review("test")
        mgr.publish("test", "1.0.0")

        gov = mgr.get_or_create("test")
        d = gov.to_dict()
        assert d["domainId"] == "test"
        assert d["status"] == "Published"
        assert d["currentVersion"] == "1.0.0"
        assert len(d["versions"]) == 1
