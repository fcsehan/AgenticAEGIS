"""ConductRegistry — register and look up codes of conduct.

Populated from the KB (extracted codes from .meld).
"""

from __future__ import annotations

from aegis.conduct.code_of_conduct import CodeOfConduct
from aegis.deontic.norm_frame import NormFrame
from aegis.kb.knowledge_base import KnowledgeBase


class ConductRegistry:
    """Registry of all loaded codes of conduct."""

    def __init__(self) -> None:
        self._codes: dict[str, CodeOfConduct] = {}

    def register(self, code: CodeOfConduct) -> None:
        """Register a code of conduct."""
        self._codes[code.name] = code

    def get(self, name: str) -> CodeOfConduct | None:
        """Return the named code, or None."""
        return self._codes.get(name)

    def get_applicable(self, agent: str) -> list[CodeOfConduct]:
        """Return all codes that have norms applicable to *agent*,
        sorted by prevalence (highest priority first)."""
        applicable = [
            code
            for code in self._codes.values()
            if any(n.matches_agent(agent) for n in code.all_norms())
        ]
        return sorted(applicable, key=lambda c: c.prevalence)

    def all_norms(self) -> list[NormFrame]:
        """Return all norms from all registered codes."""
        result: list[NormFrame] = []
        for code in self._codes.values():
            result.extend(code.all_norms())
        return result

    def prevalence_order(self) -> list[str]:
        """Return code names in prevalence order (highest priority first)."""
        codes = sorted(self._codes.values(), key=lambda c: c.prevalence)
        return [c.name for c in codes]

    @classmethod
    def from_kb(cls, kb: KnowledgeBase, norms: list[NormFrame]) -> ConductRegistry:
        """Build registry from KB and extracted norms.

        Groups norms by their ``code`` field into CodeOfConduct instances.
        """
        registry = cls()

        # Group norms by code
        by_code: dict[str, list[NormFrame]] = {}
        for norm in norms:
            if norm.code:
                by_code.setdefault(norm.code, []).append(norm)

        # Create codes with prevalence = insertion order (can be overridden)
        for i, (code_name, code_norms) in enumerate(by_code.items()):
            code = CodeOfConduct(
                name=code_name,
                norms=code_norms,
                prevalence=i,
            )
            registry.register(code)

        return registry

    @property
    def codes(self) -> list[str]:
        return list(self._codes)

    def __len__(self) -> int:
        return len(self._codes)
