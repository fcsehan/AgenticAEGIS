"""AEGIS-1210: Regelwerk-Governance (Draft/Review/Publish).

Git-based governance model for domain rule sets.
Domains go through: Draft → Review → Published → Archived.
The Guard loads ONLY Published versions.
"""

from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GovernanceError(Exception):
    """Error in the governance workflow."""


@dataclass
class VersionInfo:
    """A version of a domain."""

    tag: str
    version: str
    timestamp: str
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "version": self.version,
            "timestamp": self.timestamp,
            "message": self.message,
        }


@dataclass
class DomainGovernance:
    """Governance state for a single domain.

    Tracks the lifecycle state and version history.
    """

    domain_id: str
    status: str = "Draft"  # Draft | Review | Published | Archived
    current_version: str = "0.0.0"
    versions: list[VersionInfo] = field(default_factory=list)
    branch: str = ""
    reviewers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "domainId": self.domain_id,
            "status": self.status,
            "currentVersion": self.current_version,
            "versions": [v.to_dict() for v in self.versions],
            "branch": self.branch,
            "reviewers": self.reviewers,
        }


class GovernanceManager:
    """Manages domain governance workflows.

    Provides Draft/Review/Publish lifecycle backed by Git operations.

    Usage::

        mgr = GovernanceManager(repo_path=Path("./domains"))
        mgr.submit_for_review("ia_mission", "Add new intelligence rules")
        mgr.publish("ia_mission", "1.1.0", "Approved by compliance team")
    """

    def __init__(self, repo_path: Path) -> None:
        self._repo_path = repo_path
        self._domains: dict[str, DomainGovernance] = {}

    def get_or_create(self, domain_id: str) -> DomainGovernance:
        """Get or create governance state for a domain."""
        if domain_id not in self._domains:
            self._domains[domain_id] = DomainGovernance(domain_id=domain_id)
        return self._domains[domain_id]

    def submit_for_review(self, domain_id: str, message: str = "") -> DomainGovernance:
        """Move domain from Draft to Review.

        Creates a feature branch if Git is available.
        """
        gov = self.get_or_create(domain_id)
        if gov.status not in ("Draft", "Published"):
            raise GovernanceError(
                f"Cannot submit for review: domain is in state {gov.status!r}"
            )

        gov.status = "Review"
        branch_name = f"review/{domain_id}/{_timestamp_slug()}"
        gov.branch = branch_name

        if self._is_git_repo():
            self._git("checkout", "-b", branch_name)
            self._git("add", ".")
            self._git("commit", "-m", f"Submit {domain_id} for review: {message}")
            logger.info("Created review branch: %s", branch_name)

        return gov

    def approve(self, domain_id: str) -> DomainGovernance:
        """Approve a domain in Review state."""
        gov = self.get_or_create(domain_id)
        if gov.status != "Review":
            raise GovernanceError(
                f"Cannot approve: domain is in state {gov.status!r}, expected Review"
            )
        # Stay in Review until published
        return gov

    def publish(
        self,
        domain_id: str,
        version: str,
        message: str = "",
    ) -> DomainGovernance:
        """Publish a domain: merge to main, tag with version.

        Only domains in Review state can be published.
        """
        gov = self.get_or_create(domain_id)
        if gov.status != "Review":
            raise GovernanceError(
                f"Cannot publish: domain is in state {gov.status!r}, expected Review"
            )

        tag = f"{domain_id}/v{version}"
        timestamp = datetime.now(UTC).isoformat()

        vi = VersionInfo(
            tag=tag,
            version=version,
            timestamp=timestamp,
            message=message,
        )
        gov.versions.append(vi)
        gov.current_version = version
        gov.status = "Published"

        if self._is_git_repo():
            # Merge branch to current branch and tag
            if gov.branch:
                try:
                    self._git("checkout", "main")
                    self._git("merge", gov.branch, "--no-ff", "-m", f"Publish {tag}: {message}")
                except subprocess.CalledProcessError:
                    logger.warning("Git merge failed, continuing without merge")
            self._git("tag", "-a", tag, "-m", message or f"Publish {domain_id} v{version}")
            logger.info("Published %s as %s", domain_id, tag)

        return gov

    def rollback(self, domain_id: str, target_version: str) -> DomainGovernance:
        """Rollback a domain to a previous version.

        Creates a new commit (never force-push) that reverts to target.
        """
        gov = self.get_or_create(domain_id)

        # Find target version
        target = next(
            (v for v in gov.versions if v.version == target_version), None
        )
        if target is None:
            raise GovernanceError(
                f"Version {target_version} not found for domain {domain_id}"
            )

        if self._is_git_repo():
            target_tag = target.tag
            self._git(
                "revert", "--no-commit", f"{target_tag}..HEAD", "--", f"{domain_id}/"
            )
            self._git(
                "commit", "-m",
                f"Rollback {domain_id} to {target_version}",
            )
            logger.info("Rolled back %s to %s", domain_id, target_version)

        gov.current_version = target_version
        timestamp = datetime.now(UTC).isoformat()
        gov.versions.append(VersionInfo(
            tag=f"{domain_id}/v{target_version}-rollback",
            version=target_version,
            timestamp=timestamp,
            message=f"Rollback to {target_version}",
        ))

        return gov

    def get_history(self, domain_id: str) -> list[VersionInfo]:
        """Get version history for a domain."""
        gov = self.get_or_create(domain_id)
        return list(reversed(gov.versions))

    def _is_git_repo(self) -> bool:
        """Check if the repo path is a git repository."""
        try:
            self._git("rev-parse", "--git-dir")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    def _git(self, *args: str) -> str:
        """Run a git command in the repo directory."""
        result = subprocess.run(
            ["git", *args],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()


def _timestamp_slug() -> str:
    """Generate a timestamp slug for branch names."""
    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
