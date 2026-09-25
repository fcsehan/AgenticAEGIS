"""AEGIS-1201/1208: .meld Writer.

Serializes domain data to MELD format.
Produces up to three files: ontology-Mt, ActionVocab-Mt, and deontic-rules-Mt.
"""

from __future__ import annotations

from pathlib import Path

from aegis.editor.domain_model import DomainInfo, RuleInfo

_MODALITY_TO_PREDICATE: dict[str, str] = {
    "OBLIGATORY": "oughtToDo-WRT",
    "FORBIDDEN": "forbiddenToDo-WRT",
    "PERMITTED": "permittedToDo-WRT",
}

_MODALITY_TO_AXIOM_PREDICATE: dict[str, str] = {
    "OBLIGATORY": "oughtToDo",
    "FORBIDDEN": "forbiddenToDo",
    "PERMITTED": "permittedToDo",
}


def write_ontology_meld(domain: DomainInfo, path: Path) -> None:
    """Write the ontology .meld file for a domain."""
    mt_name = f"{_pascal_case(domain.name)}OntologyMt"
    lines = [
        "(aegis-schema-version 1)",
        f"(case {mt_name})",
        "",
    ]

    # Role declarations
    if domain.roles:
        lines.append(";; ── Agent Roles ────────────────────────────────")
        for role in domain.roles:
            lines.append(f"(isa {role.name} {_pascal_case(domain.name)}Role)")
        lines.append(
            f"(genls {_pascal_case(domain.name)}Role IntelligentAgent)"
        )
        lines.append("")

    # Deontic infrastructure
    lines.extend([
        ";; ── Deontic Infrastructure ─────────────────────",
        "(genlPreds oughtToDo-WRT permittedToDo-WRT)",
        "(negationPreds oughtToDo forbiddenToDo)",
        "(negationPreds permittedToDo forbiddenToDo)",
        "(negationPreds permittedToDo-WRT forbiddenToDo-WRT)",
    ])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_action_vocab_meld(
    name: str,
    actions: list[tuple[str, tuple[str, ...]]],
    path: Path,
) -> None:
    """Write an ActionVocab .meld file.

    Args:
        name: Domain name (will be PascalCased).
        actions: List of (action_symbol, parameter_symbols) tuples.
        path: Output file path.
    """
    mt_name = f"{_pascal_case(name)}ActionVocabMt"
    lines = [
        "(aegis-schema-version 1)",
        f"(case {mt_name})",
        "",
        ";; ── Action Types ───────────────────────────────",
    ]

    for action_symbol, _ in actions:
        lines.append(f"(isa {action_symbol} ActionType)")

    lines.append("")
    lines.append(";; ── Action Parameters ──────────────────────────")

    for action_symbol, params in actions:
        for param in params:
            # Default type constraint is Thing (generic)
            lines.append(f"(actionParameter {action_symbol} {param} Thing)")

    lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_deontic_meld(domain: DomainInfo, path: Path) -> None:
    """Write the deontic rules .meld file for a domain."""
    mt_name = f"{_pascal_case(domain.name)}DeonticRulesMt"
    lines = [
        "(aegis-schema-version 1)",
        f"(case {mt_name})",
        "",
    ]

    # Group rules by code
    by_code: dict[str, list[RuleInfo]] = {}
    axioms: list[RuleInfo] = []
    for rule in domain.rules:
        if rule.code:
            by_code.setdefault(rule.code, []).append(rule)
        else:
            axioms.append(rule)

    for code_name, code_rules in sorted(by_code.items()):
        lines.append(f";; ── {code_name} ──────────────────────────────")
        for rule in code_rules:
            predicate = _MODALITY_TO_PREDICATE.get(rule.modality, "permittedToDo-WRT")
            proposition = _format_proposition(rule.proposition)
            lines.append(
                f"({predicate} {code_name} {rule.agent_role} ({proposition}))"
            )
        lines.append("")

    if axioms:
        lines.append(";; ── Moral Axioms (non-defeasible) ──────────────")
        for rule in axioms:
            predicate = _MODALITY_TO_AXIOM_PREDICATE.get(rule.modality, "forbiddenToDo")
            proposition = _format_proposition(rule.proposition)
            lines.append(f"({predicate} {rule.agent_role} ({proposition}))")
        lines.append("")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_domain(domain: DomainInfo, output_dir: Path) -> list[Path]:
    """Export a domain as two .meld files.

    Returns the list of written file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    name = _pascal_case(domain.name)

    ontology_path = output_dir / f"{name}OntologyMt.meld"
    deontic_path = output_dir / f"{name}DeonticRulesMt.meld"

    write_ontology_meld(domain, ontology_path)
    write_deontic_meld(domain, deontic_path)

    return [ontology_path, deontic_path]


def _pascal_case(s: str) -> str:
    """Convert a string to PascalCase."""
    return "".join(word.capitalize() for word in s.replace("-", "_").split("_"))


def _format_proposition(prop: str) -> str:
    """Format a proposition string for MELD output."""
    # Already formatted as space-separated atoms
    return prop.strip()
