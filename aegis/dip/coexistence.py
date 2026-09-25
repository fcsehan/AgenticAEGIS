"""DIP/Manual-Domain coexistence policy (D-015, AEGIS-3505).

Manual domains under ``aegis/domains/<name>/`` are hand-authored and reviewed.
DIP-generated domains must not silently overwrite them. The policy:

- Default DIP output goes to ``aegis/domains/dip-generated/<name>/``.
- Writing into ``aegis/domains/<name>/`` where a manual domain already lives
  is a *hard* conflict — refused unconditionally (no ``--force`` override).
- Writing into any directory that already contains ``.meld`` files is a
  *soft* conflict — refused unless ``force=True``.
- Empty or non-existent target directories are always allowed.

This module is enforced at pipeline entry (``run_pipeline``) so every caller
(CLI, library, future hosts) is covered.
"""

from __future__ import annotations

from pathlib import Path

MANUAL_DOMAIN_ROOT: Path = Path("aegis/domains")
DIP_GENERATED_ROOT: Path = Path("aegis/domains/dip-generated")

_MELD_GLOB = "*.meld"


class DomainCoexistenceError(Exception):
    """Raised when a DIP run would conflict with an existing domain."""


def default_output_dir(name: str) -> Path:
    """Return the default DIP output directory for a domain name.

    Always points into the dip-generated namespace, never into the
    manual-domain root.
    """
    return DIP_GENERATED_ROOT / name


def is_manual_domain(name: str, root: Path = MANUAL_DOMAIN_ROOT) -> bool:
    """True if a manually authored domain ``name`` exists under ``root``.

    A manual domain is identified by the presence of any ``.meld`` file
    directly inside ``root/<name>/``. The dip-generated namespace itself
    (``aegis/domains/dip-generated/...``) is excluded.
    """
    candidate = root / name
    if not candidate.is_dir():
        return False
    if _is_inside(candidate, DIP_GENERATED_ROOT.resolve()):
        return False
    return any(candidate.glob(_MELD_GLOB))


def validate_output_target(
    output_dir: Path,
    name: str,
    *,
    force: bool = False,
    manual_root: Path = MANUAL_DOMAIN_ROOT,
) -> None:
    """Validate that a DIP run can safely write to ``output_dir``.

    Hard conflict (always refused, ``force`` ignored):
        ``output_dir`` resolves to ``manual_root/<name>/`` and a manual
        domain already exists there.

    Soft conflict (refused unless ``force=True``):
        ``output_dir`` exists and contains any ``.meld`` file.

    Raises:
        DomainCoexistenceError: on either conflict class.
    """
    target = output_dir.resolve()
    manual_target = (manual_root / name).resolve()
    dip_root = DIP_GENERATED_ROOT.resolve()

    if target == manual_target and is_manual_domain(name, root=manual_root):
        raise DomainCoexistenceError(
            f"Refusing to write DIP-generated domain '{name}' into "
            f"'{output_dir}': a manual domain already exists at this path. "
            f"DIP-generated domains belong under '{DIP_GENERATED_ROOT}/'. "
            f"Use --output to choose a different target, or remove the "
            f"manual domain first if this overwrite is intended."
        )

    if (
        target.is_relative_to(manual_root.resolve())
        and not target.is_relative_to(dip_root)
        and target != manual_target
    ):
        # Writing inside aegis/domains/ but neither into the dip-generated
        # subtree nor into the manual <name> dir — e.g. a sibling path.
        # This is suspicious but not a hard conflict per se. Treat as soft.
        pass

    if output_dir.exists() and any(output_dir.glob(_MELD_GLOB)) and not force:
        raise DomainCoexistenceError(
            f"Refusing to overwrite '{output_dir}': existing .meld files "
            f"present. Pass force=True (--force on the CLI) to override."
        )


def _is_inside(path: Path, ancestor: Path) -> bool:
    try:
        path.resolve().relative_to(ancestor)
        return True
    except ValueError:
        return False
