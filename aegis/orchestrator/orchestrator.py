"""AgentOrchestrator — AEGIS-1004.

Controls the full LLM cycle: User Prompt → LLM → tool_use → Guard → Verdict → LLM reacts.
Enforces that the LLM can ONLY act through the ActionExecutor.

If the LLM generates text instead of a tool call → NO action is executed.
If the LLM tries to describe an action in natural language → NO action is executed.
The ONLY path to action execution is: LLM calls aegis_check → Guard permits → executor runs.

This is the structural enforcement of I5 (Non-Bypassability).

Supports any OpenAI-compatible chat API (LM Studio, vLLM, OpenAI, Anthropic via adapter).
"""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from typing import Any

from aegis.api.executor import ActionExecutor
from aegis.guard.action import Action
from aegis.guard.verdict import Decision
from aegis.hardening.action_catalog import ActionCatalog
from aegis.hardening.output_guard import OutputFilter
from aegis.hardening.refusal import RefusalRegistry
from aegis.hardening.taint import TaintTracker
from aegis.orchestrator.result import OrchestratorResult

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """Orchestrates the LLM ↔ Guard interaction cycle.

    The Orchestrator owns the conversation loop and enforces that:
    1. Actions ONLY happen through aegis_check tool calls
    2. Text-only responses are passed to the user (no action taken)
    3. FORBIDDEN triggers a rejection loop (max_rejections attempts)
    4. UNDECIDABLE triggers escalation to the user
    5. The loop always terminates

    Usage::

        orchestrator = AgentOrchestrator(
            executor=guarded_executor,
            base_url="http://localhost:1234/v1",
            model="qwen/qwen3.8-27b",
            system_prompt="You are an intelligence agent...",
        )
        result = orchestrator.run("Share intel with the commander.")
    """

    def __init__(
        self,
        executor: ActionExecutor,
        base_url: str,
        model: str,
        system_prompt: str,
        *,
        max_rejections: int = 3,
        max_tokens: int = 2000,
        temperature: float = 0,
        timeout: int = 120,
        output_guard: OutputFilter | None = None,
        refusal_registry: RefusalRegistry | None = None,
        action_catalog: ActionCatalog | None = None,
    ) -> None:
        self._executor = executor
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._system_prompt = system_prompt
        self._max_rejections = max_rejections
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._timeout = timeout
        self._output_guard = output_guard
        self._refusal_registry = refusal_registry or RefusalRegistry()
        self._action_catalog = action_catalog

    def run(self, user_message: str) -> OrchestratorResult:
        """Run the full orchestration cycle for a user message.

        Returns an OrchestratorResult with all actions, verdicts,
        and the final LLM response.
        """
        result = OrchestratorResult()
        tool_schema = self._executor.as_tool()

        # AEGIS-1506: Per-request taint tracker
        taint_tracker = TaintTracker()

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_message},
        ]

        rejection_count = 0

        for iteration in range(self._max_rejections + 2):  # +2 for initial + final
            # Call LLM
            response = self._chat(messages, tool_schema)
            assistant_msg = response["choices"][0]["message"]

            # Parse tool calls from the response
            tool_calls = self._extract_tool_calls(assistant_msg)

            if not tool_calls:
                # LLM generated text only — NO action executed.
                # This is the key enforcement: text responses cannot bypass the Guard.
                text = assistant_msg.get("content", "") or ""
                logger.info(
                    "LLM responded with text only (no tool call). "
                    "No action executed. Iteration %d.",
                    iteration,
                )
                # AEGIS-1502/1506: Check output before delivering
                text = self._check_output(text, result, taint_tracker)
                result.final_response = text
                messages.append({"role": "assistant", "content": text})
                break

            # Process each tool call through the ActionExecutor
            for tc in tool_calls:
                action = Action(
                    action_type=tc.get("action_type", ""),
                    agent_id=tc.get("agent_id", ""),
                    proposition=tc.get("proposition", {}),
                    context=tc.get("context", {}),
                )
                result.actions_proposed.append(action)

                exec_result = self._executor.execute(action)
                result.verdicts.append(exec_result.verdict)

                if exec_result.executed:
                    result.actions_executed.append(action)

            # Get the last verdict to determine next step
            last_verdict = result.verdicts[-1]

            if last_verdict.decision == Decision.PERMITTED:
                # Action was executed — get LLM's confirmation response
                messages.append(assistant_msg)
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "decision": "PERMITTED",
                                "explanation": last_verdict.explain(),
                                "executed": True,
                            }
                        ),
                        "tool_call_id": "aegis_check_0",
                    }
                )
                # Get final response
                final_response = self._chat(messages, tool_schema, tool_choice="auto")
                text = final_response["choices"][0]["message"].get("content", "") or ""
                # AEGIS-1502/1506: Check output before delivering
                text = self._check_output(text, result, taint_tracker)
                result.final_response = text
                break

            elif last_verdict.decision == Decision.FORBIDDEN:
                rejection_count += 1
                result.rejection_count = rejection_count

                if rejection_count > self._max_rejections:
                    # Max rejections reached — escalate
                    result.escalated = True
                    result.final_response = (
                        f"Action forbidden after {rejection_count} attempts. "
                        f"{self._refusal_registry.render_for_user(last_verdict)} "
                        f"Escalating to human operator."
                    )
                    logger.info(
                        "Max rejections (%d) reached. Escalating.",
                        self._max_rejections,
                    )
                    break

                # Feed FORBIDDEN verdict back to LLM for retry (AEGIS-1503)
                messages.append(assistant_msg)
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "decision": "FORBIDDEN",
                                "explanation": last_verdict.explain_safe(),
                                "executed": False,
                                "suggestion": self._refusal_registry.render_for_llm(last_verdict),
                            }
                        ),
                        "tool_call_id": "aegis_check_0",
                    }
                )
                logger.info(
                    "FORBIDDEN (attempt %d/%d). Feeding back to LLM.",
                    rejection_count,
                    self._max_rejections,
                )

            elif last_verdict.decision == Decision.UNDECIDABLE:
                # Escalate immediately — the Guard cannot evaluate this
                result.escalated = True
                messages.append(assistant_msg)
                messages.append(
                    {
                        "role": "tool",
                        "content": json.dumps(
                            {
                                "decision": "UNDECIDABLE",
                                "explanation": last_verdict.explain_safe(),
                                "executed": False,
                            }
                        ),
                        "tool_call_id": "aegis_check_0",
                    }
                )
                # Get escalation response
                final_response = self._chat(messages, tool_schema, tool_choice="auto")
                text = final_response["choices"][0]["message"].get("content", "") or ""
                text = self._check_output(text, result, taint_tracker)
                result.final_response = text
                break
        else:
            # Loop exhausted without resolution
            result.escalated = True
            result.final_response = "Orchestration loop exhausted. Escalating."

        result.messages = messages
        return result

    # ── Output Safety (AEGIS-1502/1506) ─────────────────────────

    def _check_output(
        self,
        text: str,
        result: OrchestratorResult,
        taint_tracker: TaintTracker,
    ) -> str:
        """Check and sanitize LLM output text before delivery."""
        if self._output_guard is None:
            return text

        # AEGIS-1706: Use taint-aware check for classification enforcement
        check = self._output_guard.check_with_taint(text, taint_tracker)
        if not check.safe:
            result.output_sanitized = True
            result.output_violations = check.violations
            return check.redacted_text

        return text

    # ── LLM Communication ────────────────────────────────────────

    def _chat(
        self,
        messages: list[dict[str, Any]],
        tool_schema: dict[str, Any],
        *,
        tool_choice: str = "required",
    ) -> dict[str, Any]:
        """Send a chat completion request to the LLM."""
        # Build OpenAI-compatible tool definition
        tool_def = {
            "type": "function",
            "function": tool_schema,
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "tools": [tool_def],
            "tool_choice": tool_choice,
            "max_tokens": self._max_tokens,
            "temperature": self._temperature,
        }
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self._base_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self._timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read())
            return result

    # ── Tool Call Extraction ─────────────────────────────────────

    def _extract_tool_calls(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool call arguments from LLM response.

        Handles:
        1. Standard OpenAI tool_calls array
        2. Qwen3.5 XML-in-reasoning format
        """
        results: list[dict[str, Any]] = []

        # Standard format
        if message.get("tool_calls"):
            for tc in message["tool_calls"]:
                fn = tc.get("function", {})
                raw = fn.get("arguments", "{}")
                args = json.loads(raw) if isinstance(raw, str) else raw
                if args.get("action_type"):
                    results.append(args)
            return results

        # Qwen3.5 XML format in reasoning_content or content
        for field in ("reasoning_content", "content"):
            text = message.get(field, "") or ""
            if "<function=aegis_check>" in text:
                results.extend(self._parse_xml_tool_calls(text))
                if results:
                    return results

        return results

    @staticmethod
    def _parse_xml_tool_calls(text: str) -> list[dict[str, Any]]:
        """Parse Qwen3.5 XML-style tool calls."""
        results: list[dict[str, Any]] = []
        pattern = r"<function=aegis_check>(.*?)</function>"
        for match in re.finditer(pattern, text, re.DOTALL):
            block = match.group(1)
            params: dict[str, str] = {}
            for pm in re.finditer(r"<parameter=(\w+)>\s*(.*?)\s*</parameter>", block, re.DOTALL):
                params[pm.group(1)] = pm.group(2).strip()

            action_type = params.get("action_type", "")
            if not action_type:
                continue

            prop_str = params.get("proposition", "{}")
            try:
                proposition = json.loads(prop_str)
            except json.JSONDecodeError:
                proposition = {}

            results.append(
                {
                    "action_type": action_type,
                    "agent_id": params.get("agent_id", ""),
                    "proposition": proposition,
                }
            )
        return results
