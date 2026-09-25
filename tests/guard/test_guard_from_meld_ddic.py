"""Tests for Guard.from_meld_ddic_files()."""

from __future__ import annotations

from pathlib import Path

from aegis.guard.action import Action
from aegis.guard.guard import Guard
from aegis.guard.verdict import Decision, ReasonType


class TestGuardV2:
    def test_from_meld_ddic_files_builds_working_guard(self, tmp_path: Path) -> None:
        rules = tmp_path / "olson_v2.meld"
        rules.write_text(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (isa shareWeather MissionActionType)
            (belief-forbidden AgentA shareWeather Public tn)
            """,
            encoding="utf-8",
        )

        guard = Guard.from_meld_ddic_files([rules])
        verdict = guard.check(
            Action(action_type="shareWeather", agent_id="AgentA", context={"ddic_context": "Public"})
        )

        assert verdict.decision == Decision.FORBIDDEN
        assert verdict.reason_type == ReasonType.EXPLICIT_NORM

    def test_guard_v2_uses_cwa_for_known_action_without_active_belief(self, tmp_path: Path) -> None:
        rules = tmp_path / "olson_v2_empty.meld"
        rules.write_text(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (isa shareWeather MissionActionType)
            """,
            encoding="utf-8",
        )

        guard = Guard.from_meld_ddic_files([rules])
        verdict = guard.check(Action(action_type="shareWeather", agent_id="AgentA"))

        assert verdict.decision == Decision.FORBIDDEN
        assert verdict.reason_type == ReasonType.CWA_NO_PERMISSION

    def test_from_meld_files_auto_detects_v2_and_uses_ddic_mode(self, tmp_path: Path) -> None:
        """AEGIS-2315: ``from_meld_files`` does schema-version auto-detection.
        When all files declare ``(aegis-schema-version 2)`` the call is
        delegated to the v2 path and Verdicts surface ``evaluation_mode='ddic'``."""
        v2 = tmp_path / "auto_v2.meld"
        v2.write_text(
            """
            (aegis-schema-version 2)
            (case TestMt)
            (isa shareWeather MissionActionType)
            (belief-forbidden AgentA shareWeather Public tn)
            """,
            encoding="utf-8",
        )

        guard = Guard.from_meld_files([v2])
        verdict = guard.check(
            Action(
                action_type="shareWeather",
                agent_id="AgentA",
                context={"ddic_context": "Public"},
            )
        )

        assert verdict.evaluation_mode == "ddic"
        assert verdict.decision == Decision.FORBIDDEN

    def test_from_meld_files_rejects_mixed_v1_v2_explicitly(self, tmp_path: Path) -> None:
        """AEGIS-2315: mixing v1 and v2 .meld files in a single
        from_meld_files call raises MixedSchemaError. No implicit mixing."""
        from aegis.guard.guard import MixedSchemaError

        v1 = tmp_path / "mixed_v1.meld"
        v1.write_text(
            """
            (aegis-schema-version 1)
            (case A)
            (isa share ActionType)
            """,
            encoding="utf-8",
        )
        v2 = tmp_path / "mixed_v2.meld"
        v2.write_text(
            """
            (aegis-schema-version 2)
            (case B)
            (isa share ActionType)
            (belief-forbidden AgentA share Public tn)
            """,
            encoding="utf-8",
        )

        try:
            Guard.from_meld_files([v1, v2])
        except MixedSchemaError as exc:
            assert "Mixed schema versions" in str(exc)
            assert "mixed_v1.meld" in str(exc) or "v1" in str(exc)
            assert "mixed_v2.meld" in str(exc) or "v2" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("Mixed v1/v2 was silently accepted")

    def test_from_meld_files_rejects_v2_with_code_prevalence(self, tmp_path: Path) -> None:
        """AEGIS-2315: ``code_prevalence`` is a v1-only parameter; v2
        derives priorities from ``(priority A B)`` declarations. Passing
        both must surface as MixedSchemaError, not silent ignore."""
        from aegis.guard.guard import MixedSchemaError

        v2 = tmp_path / "with_prev.meld"
        v2.write_text(
            """
            (aegis-schema-version 2)
            (case TestMt)
            (isa share MissionActionType)
            """,
            encoding="utf-8",
        )

        try:
            Guard.from_meld_files([v2], code_prevalence=["SomeCode"])
        except MixedSchemaError as exc:
            assert "code_prevalence" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("v2 + code_prevalence silently accepted")

    def test_v2_path_fails_closed_on_v1_schema_file(self, tmp_path: Path) -> None:
        """The reverse direction: ``from_meld_ddic_files`` must reject v1
        syntax fast rather than treating it as belief-layer state."""
        from aegis.errors import MeldSyntaxError

        v1 = tmp_path / "v1_only.meld"
        v1.write_text(
            """
            (aegis-schema-version 1)
            (case TestMt)
            (isa shareWeather ActionType)
            """,
            encoding="utf-8",
        )

        try:
            Guard.from_meld_ddic_files([v1])
        except MeldSyntaxError as exc:
            assert "schema-version 2" in str(exc) or "schema version" in str(exc).lower()
        else:  # pragma: no cover
            raise AssertionError("v2 path silently accepted a v1 file")

    def test_unified_pipeline_surface_priority_defeat_in_chain(self, tmp_path: Path) -> None:
        """AEGIS-2314: the unified pipeline (production path used by
        Guard.check on a compiled v2 module) must include defeat events
        in justification_chain — not only the standalone adapter path.
        Earlier version of pipeline._justification_chain dropped the
        defeats; this test locks the parity in."""
        rules = tmp_path / "priority_chain.meld"
        rules.write_text(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (isa share MissionActionType)
            (before-or-equal t1 tn)
            (behavior-subsumes share share)
            (context-subsumes Top Top)
            (testimony-obligatory AgentA share Top t1)
            (testimony-forbidden AgentA share Top t1)
            (defeasible-rule Rlow
              :from (testimony-obligatory ?A ?B ?Phi ?T)
              :to   (belief-obligatory ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification ((testimony-obligatory ?A ?Z ?Psi ?Tx))
              :defeat-mode complete)
            (defeasible-rule Rhigh
              :from (testimony-forbidden ?A ?B ?Phi ?T)
              :to   (belief-forbidden ?A ?C ?Delta ?Tn)
              :when ((behavior-subsumes ?B ?C)
                     (context-subsumes ?Delta ?Phi)
                     (before-or-equal ?T ?Tn))
              :justification ((testimony-forbidden ?A ?Z ?Psi ?Tx))
              :defeat-mode complete)
            (priority Rhigh Rlow)
            """,
            encoding="utf-8",
        )

        guard = Guard.from_meld_ddic_files([rules])
        verdict = guard.check(
            Action(action_type="share", agent_id="AgentA", context={"ddic_context": "Top"})
        )

        defeat_steps = [s for s in verdict.justification_chain if s.startswith("defeat:")]
        assert defeat_steps, (
            f"unified pipeline must surface defeats; got {verdict.justification_chain}"
        )
        assert any("priority" in step for step in defeat_steps)
        assert any("Rhigh" in step for step in defeat_steps)

    def test_v2_verdict_carries_ddic_evaluation_mode(self, tmp_path: Path) -> None:
        """AEGIS-2309 #4: every Verdict from a v2 Guard surfaces
        ``evaluation_mode='ddic'`` for auditors and release-gate tools."""
        rules = tmp_path / "olson_v2_mode.meld"
        rules.write_text(
            """
            (aegis-schema-version 2)
            (case OlsonDDICMt)
            (isa shareWeather MissionActionType)
            (belief-forbidden AgentA shareWeather Public tn)
            """,
            encoding="utf-8",
        )

        guard = Guard.from_meld_ddic_files([rules])
        verdict = guard.check(
            Action(
                action_type="shareWeather",
                agent_id="AgentA",
                context={"ddic_context": "Public"},
            )
        )

        assert verdict.evaluation_mode == "ddic"
