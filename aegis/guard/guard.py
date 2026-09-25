"""Guard — the top-level entry point for action checking.

Guard.check(action) → Verdict.  This is the single function that
LLM agents call (via tool-use) to check whether an action is permitted.

Per D-005: KB snapshot at start of check(). Per-request JTMS.
Per D-004: All exceptions → UNDECIDABLE, never PERMITTED.
Per D-006: reload() for hot domain updates.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from aegis.audit.trail import AuditTrail
from aegis.deontic.norm_frame import NormFrame
from aegis.engine.ddic import DDICEngine
from aegis.engine.ddic_ir import DDICModule, compile_meld_module
from aegis.engine.inheritance import InheritanceGraph
from aegis.engine.normframe_compile import compile_norms_to_module
from aegis.errors import AuditWriteError, EvaluationError
from aegis.guard.action import Action
from aegis.guard.pipeline import EvaluationPipeline
from aegis.guard.plan import Plan
from aegis.guard.registry import ActionTypeRegistry
from aegis.guard.verdict import (
    CandidateVerdict,
    Decision,
    PlanVerdict,
    ReasonType,
    Verdict,
)
from aegis.hardening.permit import PermitStore
from aegis.kb.builtins import BuiltinEngine
from aegis.kb.knowledge_base import KnowledgeBase
from aegis.kb.meld_loader import (
    MeldLoader,
    check_disambiguation_graph,
    collect_disambiguation_edges,
    parse_meld,
    parse_meld_module,
)

logger = logging.getLogger(__name__)


class MixedSchemaError(ValueError):
    """Raised when ``from_meld_files`` is asked to load a mix of schema
    versions or an unsupported configuration of mode-specific parameters.

    Mixed v1 + v2 in a single Guard instance is forbidden by AEGIS-2315
    because the two strategies have incompatible normative semantics —
    v1 uses code-prevalence and specificity heuristics, v2 uses formal
    priority and Lex Posterior. Mixing them implicitly would silently
    favour one strategy and would not be auditable.
    """


def _detect_schema_version(path: Path) -> int | None:
    """Peek at a .meld file and return its declared schema version.

    Returns ``1`` or ``2`` when an ``(aegis-schema-version N)`` line is
    found, ``None`` when the file does not declare a version (which v1
    treats as implicit v1). Raises no exception for malformed files —
    the actual loader path will surface those.

    The detection is line-oriented and tolerant of whitespace and
    comments because we only need the version declaration, not a full
    parse.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        # Cheap but precise enough — full S-expression parser would be
        # overkill for the version peek.
        if line.startswith("(aegis-schema-version"):
            tokens = line.replace("(", " ").replace(")", " ").split()
            if len(tokens) >= 2 and tokens[0] == "aegis-schema-version":
                try:
                    return int(tokens[1])
                except ValueError:
                    return None
    return None


class Guard:
    """The AEGIS Guard — ethical action checker.

    Usage::

        guard = Guard.from_meld_files([Path("domain/ontology.meld"), ...])
        verdict = guard.check(Action(
            action_type="shareIntelligence",
            agent_id="agent-007",
            proposition={"dataClassification": "classified"},
        ))
    """

    def __init__(
        self,
        kb: KnowledgeBase,
        norms: list[NormFrame],
        registry: ActionTypeRegistry,
        ddic: DDICEngine,
        *,
        module: DDICModule | None = None,
        inheritance: InheritanceGraph | None = None,
        enrichers: list[Callable[[Action], Action]] | None = None,
        audit_trail: AuditTrail | None = None,
        permit_store: PermitStore | None = None,
        normalize: bool = False,
    ) -> None:
        self._kb = kb
        self._norms = norms
        self._registry = registry
        self._ddic = ddic
        self._module = module
        self._inheritance = inheritance
        self._enrichers = enrichers or []
        self._audit_trail = audit_trail
        self._permit_store = permit_store
        self._normalize = normalize

    @classmethod
    def from_meld_files(
        cls,
        paths: list[Path],
        *,
        code_prevalence: list[str] | None = None,
        enrichers: list[Callable[[Action], Action]] | None = None,
        audit_trail: AuditTrail | None = None,
        permit_store: PermitStore | None = None,
    ) -> Guard:
        """Build a Guard from .meld files with auto-detected schema version.

        Per AEGIS-2315 (Mixed-Mode Loading Policy):

        - All files declare ``(aegis-schema-version 1)`` (or omit the line) →
          v1 6-step resolution strategy on a compiled DDICModule.
        - All files declare ``(aegis-schema-version 2)`` → delegated to
          ``from_meld_ddic_files`` (DDIC forward-chaining with priority +
          Lex Posterior).
        - Any file mixes versions, or different files declare different
          versions in the same call → ``MixedSchemaError`` (fail-closed,
          no implicit version mixing).

        ``code_prevalence`` is honoured for the v1 path. The v2 path
        derives prevalence from ``(priority A B)`` declarations and
        therefore ignores ``code_prevalence``; passing it together with
        v2 files raises a ``MixedSchemaError`` as well, to surface the
        configuration mistake.

        Raises:
            LoadError: If any .meld file fails to load (D-004).
            MixedSchemaError: On schema-version mixing or unsupported
                mode-flag combinations.
        """
        versions = [_detect_schema_version(p) for p in paths]
        unique = {v for v in versions if v is not None}
        if len(unique) > 1:
            details = ", ".join(f"{p.name}=v{v}" for p, v in zip(paths, versions, strict=True))
            raise MixedSchemaError(
                f"Mixed schema versions in a single from_meld_files call: {details}. "
                "Split into separate Guard instances or unify the .meld files."
            )

        # Default: treat absent schema-version as v1 (back-compat).
        version = next(iter(unique), 1)

        if version == 2:
            if code_prevalence is not None:
                raise MixedSchemaError(
                    "code_prevalence is a v1-only parameter; v2 derives "
                    "priorities from (priority ...) declarations. Either "
                    "load these files via from_meld_ddic_files or remove "
                    "code_prevalence."
                )
            return cls.from_meld_ddic_files(
                paths,
                enrichers=enrichers,
                audit_trail=audit_trail,
                permit_store=permit_store,
            )

        kb = KnowledgeBase()
        loader = MeldLoader(kb)

        for path in paths:
            loader.load_file(path)

        # AEGIS-2902: enforce Subsumption consistency at load time so any
        # malformed narrowerThan/broaderThan annotation aborts the build
        # rather than silently allowing it through to Epic 32 evaluation.
        loader.validate_disambiguation_graph()
        declared_prevalence = loader.code_prevalence
        if declared_prevalence is not None:
            if code_prevalence is not None:
                raise ValueError("MELD codePrevalence cannot be overridden by a Python argument")
            code_prevalence = declared_prevalence

        kb.freeze()

        # Build reasoner and inheritance graph
        reasoner = BuiltinEngine(kb)
        reasoner.compute()
        inheritance = InheritanceGraph(reasoner)

        # Assign specificity to norms
        norms = _assign_specificity(loader.norms, inheritance)

        # Build registry and engine
        registry = ActionTypeRegistry.from_kb(kb)
        ddic = DDICEngine(inheritance, code_prevalence=code_prevalence)

        # Compile v1 norms to unified DDICModule. AEGIS-2705 (Epic 27):
        # plan-constraints flow through the loader and are attached to
        # the module here so Guard.plan_check (Phase 3+) can see them.
        module = compile_norms_to_module(
            norms,
            kb,
            code_prevalence=code_prevalence,
            plan_constraints=loader.plan_constraints,
        )

        return cls(
            kb=kb,
            norms=norms,
            registry=registry,
            ddic=ddic,
            module=module,
            inheritance=inheritance,
            enrichers=enrichers,
            audit_trail=audit_trail,
            permit_store=permit_store,
        )

    @classmethod
    def from_meld_ddic_files(
        cls,
        paths: list[Path],
        *,
        enrichers: list[Callable[[Action], Action]] | None = None,
        audit_trail: AuditTrail | None = None,
        permit_store: PermitStore | None = None,
    ) -> Guard:
        """Build a Guard from MELD v2-DDIC files."""
        kb = KnowledgeBase()
        modules: list[DDICModule] = []
        narrower: list[tuple[str, str, str]] = []
        broader: list[tuple[str, str, str]] = []

        for path in paths:
            text = path.read_text(encoding="utf-8")
            assertions = parse_meld(text, str(path))
            _assert_raw_meld_facts(kb, assertions, file=str(path))
            modules.append(compile_meld_module(parse_meld_module(text, file=str(path))))
            n, b = collect_disambiguation_edges(assertions, file=str(path))
            narrower.extend(n)
            broader.extend(b)

        # AEGIS-2902: validate Subsumption-Konsistenz across all loaded
        # v2 files before the Guard accepts the configuration.
        check_disambiguation_graph(narrower, broader)

        kb.freeze()

        reasoner = BuiltinEngine(kb)
        reasoner.compute()
        inheritance = InheritanceGraph(reasoner)
        registry = ActionTypeRegistry.from_kb(kb)
        ddic = DDICEngine(inheritance)

        return cls(
            kb=kb,
            norms=[],
            registry=registry,
            ddic=ddic,
            module=_merge_ddic_modules(modules),
            inheritance=inheritance,
            enrichers=enrichers,
            audit_trail=audit_trail,
            permit_store=permit_store,
        )

    def check(self, action: Action) -> Verdict:
        """Check whether *action* is permitted.

        Per D-005: snapshots KB reference at start.
        Per D-004: all exceptions → UNDECIDABLE.
        Per AEGIS-2309 #4: every Verdict carries ``evaluation_mode``.

        Returns:
            A Verdict — never raises to the caller.
        """
        # D-006: snapshot the KB reference for this request
        kb = self._kb  # noqa: F841 — atomic snapshot
        eval_mode = self._evaluation_mode()

        try:
            if self._module is not None:
                # Unified path: module dispatches internally by resolution_strategy
                pipeline = EvaluationPipeline.from_module(
                    module=self._module,
                    registry=self._registry,
                    inheritance=self._inheritance,
                    enrichers=self._enrichers,
                    normalize=self._normalize,
                )
            else:
                # Fallback: no module compiled (reload scenario)
                pipeline = EvaluationPipeline(
                    ddic=self._ddic,
                    registry=self._registry,
                    norms=self._norms,
                    enrichers=self._enrichers,
                    normalize=self._normalize,
                )
            verdict = pipeline.run(action)

            # AEGIS-1504: Issue permit token on PERMITTED
            if verdict.decision == Decision.PERMITTED and self._permit_store is not None:
                token = self._permit_store.issue(action)
                verdict = Verdict(
                    decision=verdict.decision,
                    reason_type=verdict.reason_type,
                    justification_chain=verdict.justification_chain,
                    norms_applied=verdict.norms_applied,
                    action_type=verdict.action_type,
                    agent_id=verdict.agent_id,
                    permit_token_id=token.token_id,
                    evaluation_mode=eval_mode,
                )
            else:
                verdict = replace(verdict, evaluation_mode=eval_mode)

            self._try_audit(action, verdict)
            return verdict

        except EvaluationError as e:
            logger.error("Evaluation error: %s", e)
            return Verdict(
                decision=Decision.UNDECIDABLE,
                reason_type=ReasonType.INTERNAL_ERROR,
                justification_chain=(f"EvaluationError: {e}",),
                action_type=action.action_type,
                agent_id=action.agent_id,
                evaluation_mode=eval_mode,
            )
        except Exception as e:
            logger.exception("Unexpected error in Guard.check()")
            verdict = Verdict(
                decision=Decision.UNDECIDABLE,
                reason_type=ReasonType.INTERNAL_ERROR,
                justification_chain=(f"Unexpected error: {e}",),
                action_type=action.action_type,
                agent_id=action.agent_id,
                evaluation_mode=eval_mode,
            )
            self._try_audit(action, verdict)
            return verdict

    def _evaluation_mode(self) -> str:
        """Identifier for the resolution strategy this Guard runs.

        Returns ``"ddic"`` for v2 forward-chaining, ``"legacy"`` for the
        v1 6-step algorithm on a compiled module, or ``"v1_legacy"`` when
        no module is compiled and direct DDICEngine fallback is used.
        Surfaced into every Verdict (AEGIS-2309 #4).
        """
        if self._module is not None:
            return self._module.resolution_strategy
        return "v1_legacy"

    def plan_check(self, plan: Plan) -> PlanVerdict:
        """Evaluate a plan as a whole (AEGIS-2710, Epic 27).

        Delegates to ``PlanPipeline.run`` which combines:

        - Per-step ``Guard.check`` calls (preserves CWA, MISSING_CONTEXT,
          INVALID_ACTION semantics — backward-compat by construction).
        - Core ``evaluate_plan_module`` for sequence/aggregate/timing/
          precondition + obligation coverage.
        - Aggregation table → ``PlanDecision``.

        ``Guard.check`` remains unchanged. ``Plan.from_action(action)``
        round-trips through this method preserving the action-level
        verdict at ``per_step_verdicts[0]``.
        """
        from aegis.guard.plan_pipeline import PlanPipeline
        return PlanPipeline(self).run(plan)

    def check_candidates(
        self,
        actions: list[Action],
        *,
        user_intent: str | None = None,
    ) -> CandidateVerdict:
        """Evaluate multiple candidate actions and return the narrowest
        PERMITTED one (Epic 32, AEGIS-3203 + AEGIS-3204).

        Decision rules:

        - Empty input list → ``CandidateVerdict`` whose ``chosen`` is
          ``UNDECIDABLE`` with reason ``NO_CANDIDATES``.
        - All candidates FORBIDDEN → ``chosen`` is the first FORBIDDEN
          verdict with reason ``ALL_CANDIDATES_FORBIDDEN`` so the caller
          gets a consistent FORBIDDEN signal; per-candidate verdicts are
          preserved for audit.
        - At least one PERMITTED → pick the *minimum* element under the
          ``narrowerThan`` partial order from the registry's
          ``SubsumptionGraph``. Multiple incomparable minima are
          tie-broken by lexicographic action-type sort and the chosen
          verdict's reason is set to ``MULTIPLE_MINIMAL_CANDIDATES`` so
          the situation is visible to auditors.
        - Mixed (some PERMITTED, some not) → only PERMITTED candidates
          enter the narrowness comparison.

        Backward compatibility: ``check_candidates([a]).chosen`` produces
        the same Verdict as ``check(a)`` modulo the reason annotation.

        ``user_intent`` is reserved for future Audit-Trail threading
        (Epic 30, AEGIS-3001..3003) and currently ignored by the
        evaluator. Captured here so call-sites do not need to change
        when Epic 30 lands.
        """
        if not actions:
            empty_verdict = Verdict(
                decision=Decision.UNDECIDABLE,
                reason_type=ReasonType.NO_CANDIDATES,
                justification_chain=("Guard.check_candidates: empty input",),
                evaluation_mode=self._evaluation_mode(),
            )
            self._try_audit_candidates([], [], empty_verdict, (), user_intent=user_intent)
            return CandidateVerdict(chosen=empty_verdict)

        verdicts: list[tuple[str, Verdict]] = [(a.action_type, self.check(a)) for a in actions]

        permitted = [(name, v, action) for (name, v), action in zip(verdicts, actions, strict=True)
                     if v.decision == Decision.PERMITTED]
        if not permitted:
            first_verdict = verdicts[0][1]
            chosen = replace(
                first_verdict,
                decision=Decision.FORBIDDEN,
                reason_type=ReasonType.ALL_CANDIDATES_FORBIDDEN,
                justification_chain=tuple(
                    f"{name}: {v.decision.value}/{v.reason_type.value}"
                    for name, v in verdicts
                ),
            )
            per_candidate_verdicts = [v for _, v in verdicts]
            self._try_audit_candidates(
                actions, per_candidate_verdicts, chosen, (), user_intent=user_intent,
            )
            return CandidateVerdict(
                chosen=chosen,
                per_candidate=tuple(verdicts),
            )

        graph = self._registry.subsumption_graph()
        permitted_names = frozenset(name for name, _, _ in permitted)
        minimal = graph.minimal_elements(permitted_names)
        # Deterministic tie-break: lexicographic sort.
        chosen_name = sorted(minimal)[0]
        # Pull the corresponding verdict.
        chosen_verdict = next(v for name, v, _ in permitted if name == chosen_name)

        if len(minimal) > 1:
            chosen_verdict = replace(
                chosen_verdict,
                reason_type=ReasonType.MULTIPLE_MINIMAL_CANDIDATES,
                justification_chain=chosen_verdict.justification_chain + (
                    f"multiple_minimal: {sorted(minimal)} → tie-break={chosen_name}",
                ),
            )

        per_candidate_verdicts = [v for _, v in verdicts]
        minimal_tuple = tuple(sorted(minimal))
        self._try_audit_candidates(
            actions, per_candidate_verdicts, chosen_verdict,
            minimal_tuple, user_intent=user_intent,
        )
        return CandidateVerdict(
            chosen=chosen_verdict,
            per_candidate=tuple(verdicts),
            minimal_candidates=minimal_tuple,
        )

    def _try_audit_candidates(
        self,
        actions: list[Action],
        per_candidate_verdicts: list[Verdict],
        chosen: Verdict,
        minimal_candidates: tuple[str, ...],
        *,
        user_intent: str | None,
    ) -> None:
        """Best-effort audit logging for check_candidates. Non-fatal per
        D-004 — an audit failure must not break the verdict path."""
        if self._audit_trail is None:
            return
        try:
            self._audit_trail.log_candidate_evaluation(
                actions,
                per_candidate_verdicts,
                chosen,
                minimal_candidates,
                user_intent=user_intent,
            )
        except (AuditWriteError, OSError) as e:
            logger.error("Audit write failed for CANDIDATE_EVALUATION: %s", e)

    def _try_audit(self, action: Action, verdict: Verdict) -> None:
        """Attempt to write an audit entry. Non-fatal per D-004."""
        if self._audit_trail is None:
            return
        try:
            self._audit_trail.log(action, verdict)
        except AuditWriteError as e:
            logger.error("Audit write failed (non-fatal): %s", e)

    def reload(self, new_kb: KnowledgeBase, new_norms: list[NormFrame]) -> None:
        """Atomically swap to a new KB (D-006).

        Laufende requests continue with the old KB.
        New requests will use the new KB.
        """
        self._kb = new_kb
        self._norms = new_norms
        self._module = None
        # Rebuild registry for new KB
        self._registry = ActionTypeRegistry.from_kb(new_kb)

        if self._audit_trail is not None:
            try:
                self._audit_trail.log_event("DOMAIN_RELOAD", {
                    "microtheories": list(new_kb.microtheories),
                    "norm_count": len(new_norms),
                })
            except AuditWriteError as e:
                logger.error("Audit write failed on reload (non-fatal): %s", e)


def _assign_specificity(norms: list[NormFrame], inheritance: InheritanceGraph) -> list[NormFrame]:
    """Create new NormFrames with specificity derived from the inheritance graph."""
    result: list[NormFrame] = []
    for norm in norms:
        specificity = inheritance.specificity_of(norm.agent_pattern)
        if specificity != norm.specificity:
            norm = NormFrame(
                code=norm.code,
                agent_pattern=norm.agent_pattern,
                modality=norm.modality,
                proposition=norm.proposition,
                specificity=specificity,
                defeasible=norm.defeasible,
                source=norm.source,
            )
        result.append(norm)
    return result


def _assert_raw_meld_facts(
    kb: KnowledgeBase,
    assertions: list[tuple[object, ...]],
    *,
    file: str,
) -> None:
    current_mt: str | None = None
    for assertion in assertions:
        predicate = assertion[0] if assertion else None
        if predicate == "case":
            if len(assertion) != 2:
                continue
            current_mt = str(assertion[1])
            if kb.get_mt(current_mt) is None:
                kb.create_mt(current_mt)
            continue
        if predicate == "aegis-schema-version":
            continue
        if current_mt is None:
            raise EvaluationError(f"No microtheory declared while loading {file}")
        kb.assert_fact(assertion, current_mt)


def _merge_ddic_modules(modules: list[DDICModule]) -> DDICModule:
    formulas = tuple(formula for module in modules for formula in module.formulas)
    relations = tuple(relation for module in modules for relation in module.relations)
    defaults = tuple(rule for module in modules for rule in module.defaults)
    defeasible_rules = tuple(rule for module in modules for rule in module.defeasible_rules)
    priorities = tuple(edge for module in modules for edge in module.priorities)
    metadata = tuple(item for module in modules for item in module.metadata)
    # AEGIS-2703 (Epic 27): plan-level extension. Plan constraints
    # union by concatenation; obligation-coverage flag combines via OR
    # so a single coverage-required submodule turns the whole merged
    # module's flag on.
    plan_constraints = tuple(
        c for module in modules for c in module.plan_constraints
    )
    require_obligation_coverage = any(
        m.require_obligation_coverage for m in modules
    )
    return DDICModule(
        formulas=formulas,
        relations=relations,
        defaults=defaults,
        defeasible_rules=defeasible_rules,
        priorities=priorities,
        metadata=metadata,
        plan_constraints=plan_constraints,
        require_obligation_coverage=require_obligation_coverage,
    )
