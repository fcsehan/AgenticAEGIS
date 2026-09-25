"""End-to-end test for AEGIS-2705 (Epic 27).

Loads a v1 .meld file containing plan-constraints through the full
``Guard.from_meld_files`` pipeline and verifies that
``guard._module.plan_constraints`` carries the compiled DDIC IR.

This test acts as the integration shim between the loader (AEGIS-2704)
and the IR (AEGIS-2703): if either side regresses the contract, this
test fails loudly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aegis.engine.ddic_ir import DDICLayer, DDICMode, PlanConstraintKind
from aegis.guard.guard import Guard


def _write_meld(directory: Path, name: str, content: str) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.fixture
def domain_with_plan_constraints(tmp_path: Path) -> list[Path]:
    """A minimal v1 domain that exercises all four plan-constraint
    predicates plus a normal deontic rule."""
    ontology = _write_meld(
        tmp_path,
        "ontology.meld",
        "(case OpsOntologyMt)\n(isa runTests SoftwareAction)\n(isa deploy SoftwareAction)\n",
    )
    rules = _write_meld(
        tmp_path,
        "rules.meld",
        """
        (case OpsRulesMt)
        (oughtToDo opsAgent runTests)
        (obligateSequence runTests deploy)
        (forbidAggregate deploy 3)
        (obligateWithin alert immediate)
        (requirePrecondition deploy (testStatus passed))
        """,
    )
    return [ontology, rules]


class TestEndToEndV1PlanConstraintLoad:
    def test_module_carries_all_four_kinds(
        self, domain_with_plan_constraints: list[Path],
    ) -> None:
        guard = Guard.from_meld_files(domain_with_plan_constraints)
        kinds = {c.kind for c in guard._module.plan_constraints}
        assert kinds == {
            PlanConstraintKind.OBLIGATE_SEQUENCE,
            PlanConstraintKind.FORBID_AGGREGATE,
            PlanConstraintKind.OBLIGATE_WITHIN,
            PlanConstraintKind.REQUIRE_PRECONDITION,
        }

    def test_source_ref_includes_filename(
        self, domain_with_plan_constraints: list[Path],
    ) -> None:
        guard = Guard.from_meld_files(domain_with_plan_constraints)
        for c in guard._module.plan_constraints:
            assert "rules.meld" in c.source_ref
            assert ":" in c.source_ref

    def test_resolution_strategy_unchanged(
        self, domain_with_plan_constraints: list[Path],
    ) -> None:
        guard = Guard.from_meld_files(domain_with_plan_constraints)
        # Adding plan-constraints must NOT switch the v1 path to v2.
        assert guard._module.resolution_strategy == "legacy"

    def test_normal_norms_still_extracted(
        self, domain_with_plan_constraints: list[Path],
    ) -> None:
        guard = Guard.from_meld_files(domain_with_plan_constraints)
        # The single (oughtToDo opsAgent runTests) norm survives.
        assert len(guard._module.formulas) == 1

    def test_require_precondition_lives_on_belief(
        self, domain_with_plan_constraints: list[Path],
    ) -> None:
        guard = Guard.from_meld_files(domain_with_plan_constraints)
        precond = next(
            c for c in guard._module.plan_constraints
            if c.kind == PlanConstraintKind.REQUIRE_PRECONDITION
        )
        assert precond.layer == DDICLayer.BELIEF
        assert precond.mode == DDICMode.OBLIGATORY


class TestEndToEndPlanFreeBackwardCompat:
    """A v1 domain WITHOUT plan-constraints still loads and produces an
    empty plan_constraints tuple — this is the by-construction
    backward-compatibility property."""

    def test_loader_with_no_plan_constraints(self, tmp_path: Path) -> None:
        ontology = _write_meld(
            tmp_path,
            "ontology.meld",
            "(case OpsOntologyMt)\n(isa runTests SoftwareAction)\n",
        )
        rules = _write_meld(
            tmp_path,
            "rules.meld",
            "(case OpsRulesMt)\n(oughtToDo opsAgent runTests)\n",
        )
        guard = Guard.from_meld_files([ontology, rules])
        assert guard._module.plan_constraints == ()
        assert guard._module.require_obligation_coverage is False
