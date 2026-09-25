"""Cross-domain Action-Substitution disambiguation invariants (AEGIS-2906).

These tests scan every hand-authored domain under ``aegis/domains/`` and
verify that the disambiguation metadata satisfies the structural
invariants documented in ``docs/_archive/MELD_SPEC.md`` § 3.4.1 and the
SUBSUMPTION_REVIEWER_CHECKLIST. They are intentionally permissive — a
domain without any disambiguation annotations passes vacuously — but
become load-bearing the moment AEGIS-2905 starts adding annotations.

The invariants:

1. Subsumption is bidirectional and acyclic across the entire domain
   set (already enforced per-domain by the MeldLoader; this test
   verifies it holds for every shipped domain).
2. ``notToBeConfusedWith`` is symmetric — if ``A`` is at risk of being
   confused with ``B``, the reverse direction is documented too.
3. Every action that appears in a ``notToBeConfusedWith`` declaration
   has an ``actionDescription``. Without a description the LLM has no
   basis for telling the two apart.

Plus property tests against the SubsumptionGraph minimum-element
selector that Epic 32 will consume.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from aegis.guard.guard import Guard
from aegis.guard.registry import ActionTypeRegistry, SubsumptionGraph

DOMAIN_ROOT = Path(__file__).parent.parent / "aegis" / "domains"

DOMAINS_TO_SCAN = [
    "iamission",
    "pharma",
    "sanctions",
    "legal",
    "devops",
    "ifc",
]


def _load_domain(name: str) -> ActionTypeRegistry:
    """Load all .meld files under aegis/domains/<name>/ and return the
    derived registry. Skip if the domain directory does not exist."""
    domain_dir = DOMAIN_ROOT / name
    if not domain_dir.is_dir():
        pytest.skip(f"domain {name!r} not present at {domain_dir}")
    meld_files = sorted(domain_dir.glob("*.meld"))
    if not meld_files:
        pytest.skip(f"no .meld files in {domain_dir}")
    guard = Guard.from_meld_files(meld_files)
    return guard._registry  # internal access for cross-domain tests


@pytest.mark.parametrize("domain", DOMAINS_TO_SCAN)
class TestPerDomainInvariants:
    """Each invariant is parametrised over the six bundled domains."""

    def test_subsumption_graph_acyclic(self, domain: str) -> None:
        """If the loader had let a cycle through, every domain load
        would already raise. This test is the visible regression
        guard for the cross-domain matrix."""
        registry = _load_domain(domain)
        # Reaching this line means the load (and its acyclicity check)
        # succeeded — assert by construction.
        assert registry.subsumption_graph() is not None

    def test_subsumption_relations_are_inverse(self, domain: str) -> None:
        """For every (narrowerThan A B) declared by an action's schema,
        the inverse (broaderThan B A) must be declared on B's schema."""
        registry = _load_domain(domain)
        for name in registry.action_types:
            schema = registry.get_schema(name)
            assert schema is not None
            for broader in schema.narrower_than:
                target = registry.get_schema(broader)
                assert target is not None, (
                    f"{domain}: {name} narrowerThan unknown {broader!r}"
                )
                assert name in target.broader_than, (
                    f"{domain}: ({broader} broaderThan {name}) is missing"
                )

    def test_confusables_are_symmetric(self, domain: str) -> None:
        """A `notToBeConfusedWith` pair is meaningful only when both
        actions know about the confusion. Asymmetric declarations lose
        the warning at the LLM-prompt level for one of the two
        directions."""
        registry = _load_domain(domain)
        for name in registry.action_types:
            schema = registry.get_schema(name)
            assert schema is not None
            for other in schema.confusables:
                target = registry.get_schema(other)
                if target is None:
                    pytest.fail(
                        f"{domain}: {name} declares notToBeConfusedWith "
                        f"unknown action {other!r}"
                    )
                assert name in target.confusables, (
                    f"{domain}: notToBeConfusedWith asymmetric — "
                    f"{name} knows about {other} but not vice versa"
                )

    def test_confusables_imply_description(self, domain: str) -> None:
        """An action listed in someone's notToBeConfusedWith without
        its own actionDescription gives the LLM nothing to disambiguate
        against. Either drop the warning or add the description."""
        registry = _load_domain(domain)
        for name in registry.action_types:
            schema = registry.get_schema(name)
            assert schema is not None
            if schema.confusables and not schema.description:
                pytest.fail(
                    f"{domain}: {name} has notToBeConfusedWith but no "
                    f"actionDescription — see SUBSUMPTION_REVIEWER_CHECKLIST."
                )


# ── Property tests for SubsumptionGraph minimum-element selection ──


def _random_dag_graph(n: int, edge_count: int, seed: int) -> SubsumptionGraph:
    """Build a SubsumptionGraph as a DAG by only allowing edges from a
    lower index to a higher one."""
    import random

    rng = random.Random(seed)
    edges: dict[str, list[str]] = {}
    for _ in range(edge_count):
        a = rng.randint(0, n - 2)
        b = rng.randint(a + 1, n - 1)
        edges.setdefault(f"A{a}", []).append(f"A{b}")
    return SubsumptionGraph(edges={k: tuple(v) for k, v in edges.items()})


@settings(deadline=500, suppress_health_check=[HealthCheck.too_slow], max_examples=60)
@given(
    n=st.integers(min_value=2, max_value=6),
    edge_count=st.integers(min_value=0, max_value=10),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_minimal_elements_is_antichain(n: int, edge_count: int, seed: int) -> None:
    """Property: the result of ``minimal_elements`` is an antichain —
    no two members are comparable under ``narrowerThan``."""
    graph = _random_dag_graph(n, edge_count, seed)
    candidates = frozenset(f"A{i}" for i in range(n))
    minima = graph.minimal_elements(candidates)
    for a in minima:
        for b in minima:
            if a == b:
                continue
            assert not graph.is_narrower_than(a, b), (
                f"{a} and {b} both reported as minimal but {a} narrowerThan {b}"
            )


@settings(deadline=500, suppress_health_check=[HealthCheck.too_slow], max_examples=60)
@given(
    n=st.integers(min_value=2, max_value=6),
    edge_count=st.integers(min_value=0, max_value=10),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_minimal_elements_is_non_empty_for_non_empty_input(
    n: int, edge_count: int, seed: int,
) -> None:
    """Property: in a finite DAG over a non-empty candidate set, at
    least one element must be minimal — otherwise we would have found
    a cycle (which the loader would have rejected)."""
    graph = _random_dag_graph(n, edge_count, seed)
    candidates = frozenset(f"A{i}" for i in range(n))
    assert graph.minimal_elements(candidates), (
        "expected at least one minimal element in a finite DAG"
    )


@settings(deadline=500, suppress_health_check=[HealthCheck.too_slow], max_examples=60)
@given(
    n=st.integers(min_value=2, max_value=6),
    edge_count=st.integers(min_value=0, max_value=10),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
def test_every_candidate_is_dominated_or_minimal(
    n: int, edge_count: int, seed: int,
) -> None:
    """Property: every candidate is either minimal or strictly narrower
    than some minimal element. There is no third class — the partition
    of the candidate set into ``minima`` and ``dominated`` is
    exhaustive."""
    graph = _random_dag_graph(n, edge_count, seed)
    candidates = frozenset(f"A{i}" for i in range(n))
    minima = graph.minimal_elements(candidates)
    for c in candidates:
        if c in minima:
            continue
        # Must be strictly narrower than at least one minimal.
        assert any(graph.is_narrower_than(m, c) for m in minima), (
            f"{c} is not minimal yet no minimum is narrower than it"
        )
