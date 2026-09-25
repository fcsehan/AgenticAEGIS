"""DIP coverage analysis and reference testing.

Provides two verification capabilities:

1. Coverage analysis: which articles/paragraphs produced rules, which didn't
2. Reference testing: run predefined test actions against a generated domain
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aegis.dip.models import (
    CompilationResult,
    NormativeChunk,
    NormativeDocument,
    NormativeStatement,
)

logger = logging.getLogger(__name__)


# ── Coverage Analysis ───────────────────────────────────────────────


@dataclass
class ArticleCoverage:
    """Coverage info for a single article."""

    number: str
    title: str
    total_paragraphs: int = 0
    chunks_produced: int = 0
    statements_extracted: int = 0
    rules_compiled: int = 0
    rules_flagged: int = 0
    skipped_reason: str = ""


@dataclass
class CoverageReport:
    """Coverage report for a full DIP run."""

    articles: list[ArticleCoverage] = field(default_factory=list)
    total_articles: int = 0
    articles_with_rules: int = 0
    articles_without_rules: int = 0
    coverage_ratio: float = 0.0

    def summary(self) -> str:
        return (
            f"Coverage: {self.articles_with_rules}/{self.total_articles} articles "
            f"({self.coverage_ratio:.0%}) produced rules"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_articles": self.total_articles,
            "articles_with_rules": self.articles_with_rules,
            "articles_without_rules": self.articles_without_rules,
            "coverage_ratio": self.coverage_ratio,
            "articles": [
                {
                    "number": a.number,
                    "title": a.title,
                    "paragraphs": a.total_paragraphs,
                    "chunks": a.chunks_produced,
                    "statements": a.statements_extracted,
                    "rules": a.rules_compiled,
                    "flagged": a.rules_flagged,
                    "skipped_reason": a.skipped_reason,
                }
                for a in self.articles
            ],
        }


def analyze_coverage(
    doc: NormativeDocument,
    chunks: list[NormativeChunk],
    statements: list[NormativeStatement],
    results: list[CompilationResult],
) -> CoverageReport:
    """Analyze per-article coverage of the DIP pipeline."""
    # Count per article
    chunk_counts: dict[str, int] = {}
    for c in chunks:
        # Extract article number from ref like "Art. 5(1)"
        art_num = _extract_article_num(c.article_ref)
        chunk_counts[art_num] = chunk_counts.get(art_num, 0) + 1

    stmt_counts: dict[str, int] = {}
    for s in statements:
        art_num = _extract_article_num(s.source_article)
        stmt_counts[art_num] = stmt_counts.get(art_num, 0) + 1

    rule_counts: dict[str, int] = {}
    flag_counts: dict[str, int] = {}
    for r in results:
        if r.success:
            art_num = _extract_article_num(r.source_article)
            rule_counts[art_num] = rule_counts.get(art_num, 0) + 1
            if r.flagged:
                flag_counts[art_num] = flag_counts.get(art_num, 0) + 1

    articles: list[ArticleCoverage] = []
    for art in doc.articles:
        num = art.number
        para_count = len(art.paragraphs) or (1 if art.full_text else 0)
        chunks_n = chunk_counts.get(num, 0)
        stmts_n = stmt_counts.get(num, 0)
        rules_n = rule_counts.get(num, 0)
        flagged_n = flag_counts.get(num, 0)

        skipped = ""
        if chunks_n == 0:
            skipped = "no normative chunks (filtered as organizational/definition)"
        elif stmts_n == 0:
            skipped = "no statements extracted by LLM"
        elif rules_n == 0:
            skipped = "all rules failed compilation"

        articles.append(ArticleCoverage(
            number=num,
            title=art.title,
            total_paragraphs=para_count,
            chunks_produced=chunks_n,
            statements_extracted=stmts_n,
            rules_compiled=rules_n,
            rules_flagged=flagged_n,
            skipped_reason=skipped,
        ))

    with_rules = sum(1 for a in articles if a.rules_compiled > 0)
    total = len(articles)

    return CoverageReport(
        articles=articles,
        total_articles=total,
        articles_with_rules=with_rules,
        articles_without_rules=total - with_rules,
        coverage_ratio=with_rules / total if total > 0 else 0.0,
    )


def _extract_article_num(ref: str) -> str:
    """Extract article number from reference like 'Art. 5(1)' → '5'."""
    import re
    m = re.search(r"(\d+(?:\.\d+)*)", ref)
    return m.group(1) if m else ref


# ── Reference Testing ───────────────────────────────────────────────


@dataclass
class ReferenceTestCase:
    """A single test case: action + expected verdict."""

    action_type: str
    agent_id: str
    expected_verdict: str  # "PERMITTED" | "FORBIDDEN" | "UNDECIDABLE"
    description: str = ""
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass
class ReferenceTestResult:
    """Result of running a single reference test."""

    test: ReferenceTestCase
    actual_verdict: str
    passed: bool
    justification: list[str] = field(default_factory=list)


@dataclass
class ReferenceTestReport:
    """Report from running all reference tests."""

    results: list[ReferenceTestResult] = field(default_factory=list)
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0

    def summary(self) -> str:
        return (
            f"Reference tests: {self.passed}/{self.total} passed, "
            f"{self.failed} failed, {self.skipped} skipped"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "results": [
                {
                    "action_type": r.test.action_type,
                    "agent_id": r.test.agent_id,
                    "expected": r.test.expected_verdict,
                    "actual": r.actual_verdict,
                    "passed": r.passed,
                    "description": r.test.description,
                }
                for r in self.results
            ],
        }


def load_reference_tests(path: Path) -> list[ReferenceTestCase]:
    """Load reference test cases from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    tests = []
    for entry in data:
        tests.append(ReferenceTestCase(
            action_type=entry["action_type"],
            agent_id=entry["agent_id"],
            expected_verdict=entry["expected_verdict"],
            description=entry.get("description", ""),
            parameters=entry.get("parameters", {}),
        ))
    return tests


def run_reference_tests(
    guard: object,  # Guard — typed as object to avoid import
    tests: list[ReferenceTestCase],
) -> ReferenceTestReport:
    """Run reference tests against a Guard instance."""
    from aegis.guard.action import Action
    from aegis.guard.guard import Guard

    assert isinstance(guard, Guard)

    results: list[ReferenceTestResult] = []
    for test in tests:
        try:
            action = Action(
                action_type=test.action_type,
                agent_id=test.agent_id,
                proposition=test.parameters,
            )
            verdict = guard.check(action)
            actual = verdict.decision.value
            passed = actual == test.expected_verdict
            results.append(ReferenceTestResult(
                test=test,
                actual_verdict=actual,
                passed=passed,
                justification=list(verdict.justification_chain),
            ))
        except Exception as e:
            results.append(ReferenceTestResult(
                test=test,
                actual_verdict=f"ERROR: {e}",
                passed=False,
            ))

    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)

    return ReferenceTestReport(
        results=results,
        total=total,
        passed=passed,
        failed=failed,
    )
