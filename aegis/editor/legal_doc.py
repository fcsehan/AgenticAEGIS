"""AEGIS-1405: Legal Documentation Generator.

Generates a human-readable Markdown document of a complete domain rule set —
for lawyers, compliance officers, and auditors.
Main body uses natural language only; MELD source text is confined to the appendix.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from aegis.editor.domain_model import DomainInfo, RuleInfo

_MODALITY_LABELS: dict[str, dict[str, str]] = {
    "en": {
        "OBLIGATORY": "Obligation",
        "FORBIDDEN": "Prohibition",
        "PERMITTED": "Permission",
    },
}

_SECTION_HEADERS: dict[str, dict[str, str]] = {
    "en": {
        "overview": "Domain Overview",
        "roles": "Roles & Responsibilities",
        "codes": "Codes of Conduct",
        "obligations": "Obligations",
        "prohibitions": "Prohibitions",
        "permissions": "Permissions",
        "axioms": "Moral Axioms (Non-Defeasible)",
        "conflicts": "Conflict Resolutions",
        "tests": "Test Results",
        "appendix": "Appendix: MELD Source",
        "generated": "Generated",
        "version": "Version",
        "status": "Status",
        "rule_count": "Total Rules",
        "role_count": "Roles",
        "code_count": "Codes of Conduct",
        "prevalence": "Prevalence",
        "rules_header": "Rules",
        "no_tests": "No test results available.",
        "defeasible_note": "This rule can be overridden by more specific norms.",
        "non_defeasible_note": "This rule is a moral axiom and cannot be overridden.",
    },
}


class LegalDocGenerator:
    """Generates a human-readable legal document for a domain.

    Usage::

        gen = LegalDocGenerator(domain, locale="en")
        markdown = gen.generate()
        # Optionally include test results and conflict data
        markdown = gen.generate(
            test_results=[...],
            conflicts=[...],
            meld_source="(oughtToDo-WRT ...)",
        )
    """

    def __init__(self, domain: DomainInfo, *, locale: str = "en") -> None:
        self._domain = domain
        self._locale = locale if locale in _SECTION_HEADERS else "en"
        self._h = _SECTION_HEADERS[self._locale]
        self._ml = _MODALITY_LABELS[self._locale]

    def generate(
        self,
        *,
        test_results: list[dict[str, Any]] | None = None,
        conflicts: list[dict[str, Any]] | None = None,
        meld_source: str = "",
    ) -> str:
        """Generate the complete legal document as Markdown."""
        sections: list[str] = []

        sections.append(self._overview())
        sections.append(self._roles_section())
        sections.append(self._codes_section())
        sections.append(self._rules_by_category())
        sections.append(self._axioms_section())

        if conflicts:
            sections.append(self._conflicts_section(conflicts))

        if test_results:
            sections.append(self._tests_section(test_results))
        else:
            sections.append(f"## {self._h['tests']}\n\n{self._h['no_tests']}\n")

        if meld_source:
            sections.append(self._appendix(meld_source))

        return "\n\n".join(sections) + "\n"

    def _overview(self) -> str:
        d = self._domain
        timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        lines = [
            f"# {d.name}",
            "",
            f"## {self._h['overview']}",
            "",
            "| | |",
            "|---|---|",
            f"| **{self._h['status']}** | {d.status} |",
            f"| **{self._h['rule_count']}** | {len(d.rules)} |",
            f"| **{self._h['role_count']}** | {len(d.roles)} |",
            f"| **{self._h['code_count']}** | {len(d.codes)} |",
            f"| **{self._h['generated']}** | {timestamp} |",
        ]
        if d.description:
            lines.insert(2, f"*{d.description}*")
            lines.insert(3, "")
        return "\n".join(lines)

    def _roles_section(self) -> str:
        lines = [f"## {self._h['roles']}", ""]
        if not self._domain.roles:
            lines.append("*—*")
            return "\n".join(lines)
        for role in self._domain.roles:
            desc = f" — {role.description}" if role.description else ""
            header = self._h["rules_header"].lower()
            lines.append(
                f"- **{role.name}**{desc} ({role.rule_count} {header})"
            )
        return "\n".join(lines)

    def _codes_section(self) -> str:
        lines = [f"## {self._h['codes']}", ""]
        if not self._domain.codes:
            lines.append("*—*")
            return "\n".join(lines)
        sorted_codes = sorted(self._domain.codes, key=lambda c: c.prevalence, reverse=True)
        for code in sorted_codes:
            desc = f" — {code.description}" if code.description else ""
            lines.append(f"- **{code.name}**{desc} ({self._h['prevalence']}: {code.prevalence})")
        return "\n".join(lines)

    def _rules_by_category(self) -> str:
        """Group defeasible rules by modality."""
        groups: dict[str, list[RuleInfo]] = {
            "OBLIGATORY": [],
            "FORBIDDEN": [],
            "PERMITTED": [],
        }
        for rule in self._domain.rules:
            if rule.defeasible and rule.modality in groups:
                groups[rule.modality].append(rule)

        sections: list[str] = []
        category_map = {
            "OBLIGATORY": "obligations",
            "FORBIDDEN": "prohibitions",
            "PERMITTED": "permissions",
        }

        for modality, header_key in category_map.items():
            rules = groups[modality]
            lines = [f"## {self._h[header_key]}", ""]
            if not rules:
                lines.append("*—*")
            else:
                for rule in rules:
                    lines.append(self._format_rule_natural(rule))
            sections.append("\n".join(lines))

        return "\n\n".join(sections)

    def _axioms_section(self) -> str:
        axioms = [r for r in self._domain.rules if not r.defeasible]
        lines = [f"## {self._h['axioms']}", ""]
        if not axioms:
            lines.append("*—*")
            return "\n".join(lines)
        for rule in axioms:
            lines.append(self._format_rule_natural(rule, is_axiom=True))
        return "\n".join(lines)

    def _format_rule_natural(self, rule: RuleInfo, *, is_axiom: bool = False) -> str:
        """Format a single rule in natural language."""
        modality_label = self._ml.get(rule.modality, rule.modality)
        agent = rule.agent_role if rule.agent_role != "*" else "Any agent"
        code_part = f" (under {rule.code})" if rule.code else ""

        line = f"- **{modality_label}**: {agent} — {rule.proposition}{code_part}"
        if is_axiom:
            line += f"  \n  *{self._h['non_defeasible_note']}*"
        return line

    def _conflicts_section(self, conflicts: list[dict[str, Any]]) -> str:
        lines = [f"## {self._h['conflicts']}", ""]
        for c in conflicts:
            a = c.get("normA", {})
            b = c.get("normB", {})
            resolution = c.get("resolution", "Unresolved")
            resolved = c.get("resolved", False)
            status = "✓" if resolved else "✗"
            lines.append(
                f"- {status} {a.get('modality', '?')} vs {b.get('modality', '?')} "
                f"on `{a.get('proposition', '?')}` — Resolution: {resolution}"
            )
        return "\n".join(lines)

    def _tests_section(self, test_results: list[dict[str, Any]]) -> str:
        lines = [f"## {self._h['tests']}", ""]
        lines.append("| Rule | Action | Expected | Actual | Status |")
        lines.append("|------|--------|----------|--------|--------|")
        for t in test_results:
            expected = t.get("expected", "?")
            actual = t.get("actual", "?")
            status = "✓" if expected == actual else "✗"
            lines.append(
                f"| {t.get('rule', '—')} | {t.get('action', '—')} "
                f"| {expected} | {actual} | {status} |"
            )
        return "\n".join(lines)

    def _appendix(self, meld_source: str) -> str:
        lines = [
            f"## {self._h['appendix']}",
            "",
            "```lisp",
            meld_source.strip(),
            "```",
        ]
        return "\n".join(lines)
