"""WRTEngine — evaluate norms "with respect to" specific codes.

The WRT pattern is the core of AEGIS's domain-specific evaluation:
  (oughtToDo-WRT IAMissionCode agent proposition)

The WRT evaluator collects norms from applicable codes and feeds them
to the DDIC engine with the correct prevalence ordering.
"""

from __future__ import annotations

from typing import Any

from aegis.conduct.registry import ConductRegistry
from aegis.deontic.norm_frame import NormFrame
from aegis.deontic.norm_status import NormStatus
from aegis.engine.ddic import DDICEngine


class WRTEngine:
    """Evaluate propositions with respect to registered codes.

    Usage::

        evaluator = WRTEngine(registry, ddic)
        status = evaluator.evaluate(
            proposition=("shareIntelligence", ...),
            agent="intelligenceAgent",
        )
    """

    def __init__(
        self,
        registry: ConductRegistry,
        ddic: DDICEngine,
    ) -> None:
        self._registry = registry
        self._ddic = ddic

    def evaluate(
        self,
        proposition: tuple[Any, ...],
        agent: str,
        context: dict[str, Any] | None = None,
    ) -> NormStatus:
        """Evaluate *proposition* for *agent* across all applicable codes.

        Collects norms from all codes applicable to the agent and
        evaluates them through DDIC with cross-code prevalence.
        """
        # Collect all applicable norms
        applicable_codes = self._registry.get_applicable(agent)
        all_norms: list[NormFrame] = []
        for code in applicable_codes:
            all_norms.extend(code.all_norms())

        return self._ddic.evaluate(
            proposition=proposition,
            agent=agent,
            norms=all_norms,
            context=context,
        )

    def evaluate_wrt(
        self,
        code_name: str,
        proposition: tuple[Any, ...],
        agent: str,
        context: dict[str, Any] | None = None,
    ) -> NormStatus:
        """Evaluate *proposition* WRT a specific code of conduct."""
        code = self._registry.get(code_name)
        if code is None:
            return NormStatus(
                modality=None,
                reason="unknown_code",
                justification_chain=(f"Code not found: {code_name!r}",),
            )

        return self._ddic.evaluate(
            proposition=proposition,
            agent=agent,
            norms=code.all_norms(),
            context=context,
        )
