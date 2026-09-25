"""CodeOfConduct — a named collection of norms with prevalence ordering.

Each domain provides one or more codes of conduct.  Codes have a
prevalence rank that determines which code wins in cross-code conflicts.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from aegis.deontic.norm_frame import NormFrame


@dataclass
class CodeOfConduct:
    """A named set of deontic norms.

    Attributes:
        name: Code identifier (e.g. ``"IAMissionCode"``).
        norms: NormFrames belonging to this code.
        parent: Optional parent code (for inheritance).
        prevalence: Prevalence rank (lower = higher priority).
    """

    name: str
    norms: list[NormFrame] = field(default_factory=list)
    parent: CodeOfConduct | None = None
    prevalence: int = 0

    def all_norms(self) -> list[NormFrame]:
        """Return all norms including inherited from parent."""
        result = list(self.norms)
        if self.parent is not None:
            result.extend(self.parent.all_norms())
        return result

    def add_norm(self, norm: NormFrame) -> None:
        """Add a norm to this code."""
        self.norms.append(norm)

    def __repr__(self) -> str:
        parent_name = self.parent.name if self.parent else None
        return (
            f"CodeOfConduct({self.name!r}, norms={len(self.norms)}, "
            f"prevalence={self.prevalence}, parent={parent_name!r})"
        )
