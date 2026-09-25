"""Tests for AEGIS-1503: Safe Refusal Templates."""

from __future__ import annotations

from aegis.guard.verdict import Decision, ReasonType, Verdict
from aegis.hardening.refusal import RefusalRegistry


class TestRefusalRegistry:
    def test_every_reason_type_has_template(self) -> None:
        """All ReasonType values must have a registered template."""
        registry = RefusalRegistry()
        for rt in ReasonType:
            template = registry.get(rt)
            assert template is not None
            assert template.user_message
            assert template.llm_feedback

    def test_user_message_never_contains_norm_sources(self) -> None:
        """User-facing messages must not leak norm names."""
        registry = RefusalRegistry()
        for rt in ReasonType:
            verdict = Verdict(
                decision=Decision.FORBIDDEN,
                reason_type=rt,
                norms_applied=("IAMissionCode:shareIntelligence:42",),
                action_type="shareIntelligence",
                agent_id="agent-007",
            )
            msg = registry.render_for_user(verdict)
            assert "IAMissionCode" not in msg
            assert "shareIntelligence" not in msg
            assert ":42" not in msg

    def test_deterministic_output(self) -> None:
        """Same input should produce same output."""
        registry = RefusalRegistry()
        verdict = Verdict(
            decision=Decision.FORBIDDEN,
            reason_type=ReasonType.EXPLICIT_NORM,
            action_type="shareIntelligence",
            agent_id="agent-007",
        )
        msg1 = registry.render_for_user(verdict)
        msg2 = registry.render_for_user(verdict)
        assert msg1 == msg2

    def test_llm_feedback_differs_from_user_message(self) -> None:
        """LLM feedback should be more detailed than user message."""
        registry = RefusalRegistry()
        for rt in ReasonType:
            template = registry.get(rt)
            assert template.llm_feedback != template.user_message

    def test_render_for_user_forbidden(self) -> None:
        registry = RefusalRegistry()
        verdict = Verdict(
            decision=Decision.FORBIDDEN,
            reason_type=ReasonType.MORAL_AXIOM,
            action_type="deleteIntelligence",
            agent_id="agent-007",
        )
        msg = registry.render_for_user(verdict)
        assert "prohibited" in msg.lower() or "not permitted" in msg.lower()

    def test_render_for_llm_includes_guidance(self) -> None:
        registry = RefusalRegistry()
        verdict = Verdict(
            decision=Decision.UNDECIDABLE,
            reason_type=ReasonType.NO_JURISDICTION,
            action_type="unknownAction",
            agent_id="agent-007",
        )
        msg = registry.render_for_llm(verdict)
        assert "escalate" in msg.lower() or "human" in msg.lower()
