// Copyright 2026 Frank Csehan. SPDX-License-Identifier: Apache-2.0
import { appendFileSync, readFileSync, realpathSync, existsSync } from "node:fs";
import { resolve, relative, dirname, basename, isAbsolute, sep } from "node:path";
import { createHash } from "node:crypto";

export function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export function fingerprint(value) {
  return createHash("sha256").update(canonical(value)).digest("hex");
}

function freeze(value) {
  if (value && typeof value === "object") {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
}

function localPath(directory, path) {
  if (typeof path !== "string" || !path) throw new Error("Missing filePath");
  const root = realpathSync(directory);
  const absolute = resolve(root, path);
  // Resolve existing ancestors, including symlinks, for new files too.
  let ancestor = absolute;
  const tail = [];
  while (!existsSync(ancestor)) {
    tail.unshift(basename(ancestor));
    const parent = dirname(ancestor);
    if (parent === ancestor) throw new Error("Cannot resolve filePath");
    ancestor = parent;
  }
  const target = resolve(realpathSync(ancestor), ...tail);
  const name = relative(root, target);
  if (!name || name === ".." || name.startsWith(`..${sep}`) || isAbsolute(name)) {
    throw new Error("filePath is outside the configured workspace");
  }
  return name.split(sep).join("/");
}

export function mapAction(directory, agent, tool, args) {
  const types = { read: "readFile", write: "modifyFile", edit: "modifyFile" };
  const type = types[tool];
  return {
    action_type: type ?? "unmodeledOpenCodeTool",
    agent_id: agent,
    proposition: type ? { path: localPath(directory, args.filePath) } : { tool },
    context: { tool, arguments_sha256: fingerprint(args) },
  };
}

export function createGuardHooks({ directory, guardUrl, agentId, auditPath, timeoutMs = 3000, plan }) {
  const url = new URL(guardUrl);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname)) {
    throw new Error("This integration requires a loopback HTTP guard");
  }
  if (!agentId || !auditPath || !Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    throw new Error("Invalid AEGIS configuration");
  }
  const pending = new Map();
  let cursor = 0;
  let planApproved = false;
  let checkingPlan = false;
  const declared = plan ? JSON.parse(JSON.stringify(plan)) : undefined;
  if (declared && (!Array.isArray(declared.steps) || !declared.steps.length)) {
    throw new Error("A declared plan must contain steps");
  }

  function audit(event, data) {
    // Audit failure blocks before execution. Records contain hashes, not file content.
    appendFileSync(auditPath, JSON.stringify({ timestamp: new Date().toISOString(), event, ...data }) + "\n", { mode: 0o600 });
  }

  async function request(endpoint, payload, planRequest = false) {
    try {
      const response = await fetch(new URL(endpoint, url), {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload), signal: AbortSignal.timeout(timeoutMs), redirect: "error",
      });
      if (!response.ok) throw new Error(`Guard HTTP ${response.status}`);
      const verdict = await response.json();
      const decision = verdict[planRequest ? "plan_decision" : "decision"];
      if (!["PERMITTED", "FORBIDDEN", "UNDECIDABLE"].includes(decision)) throw new Error("Invalid guard verdict");
      if (planRequest) {
        if (typeof verdict.reason_summary !== "string" || !Array.isArray(verdict.violations) || !Array.isArray(verdict.per_step_verdicts)) throw new Error("Incomplete plan verdict");
      } else if (typeof verdict.reason_type !== "string" || !Array.isArray(verdict.justification_chain) || verdict.action_type !== payload.action_type || verdict.agent_id !== payload.agent_id) {
        throw new Error("Incomplete or mismatched action verdict");
      }
      return verdict;
    } catch (error) {
      return planRequest
        ? { plan_decision: "UNDECIDABLE", reason_summary: `GUARD_ERROR: ${error.message}`, violations: [], per_step_verdicts: [] }
        : { decision: "UNDECIDABLE", reason_type: "GUARD_ERROR", justification_chain: [error.message] };
    }
  }

  audit("initialized", { directory, agent_id: agentId, plan_sha256: declared ? fingerprint(declared) : null });
  return {
    async "tool.execute.before"(input, output) {
      const key = `${input.sessionID}:${input.callID}`;
      const argsHash = fingerprint(output.args);
      // Freeze the shared argument object before awaiting the sidecar. No permission cache.
      freeze(output);
      const record = { session_id: input.sessionID, call_id: input.callID, tool: input.tool, arguments_sha256: argsHash };
      let reserved = false;
      try {
        if (pending.has(key)) throw new Error("Duplicate in-flight call");
        // Fail closed even if a domain accidentally grants the unknown action type.
        if (!["read", "write", "edit"].includes(input.tool)) {
          const action = mapAction(directory, agentId, input.tool, output.args);
          const verdict = await request("/v1/check", action);
          audit("decision", { ...record, action, verdict });
          throw new Error(`UNMODELED_TOOL (${verdict.decision})`);
        }
        const action = mapAction(directory, agentId, input.tool, output.args);
        if (declared) {
          if (checkingPlan || pending.size) throw new Error("Concurrent execution is outside the declared sequential plan");
          const step = declared.steps[cursor];
          if (!step || step.tool !== input.tool || canonical(step.args) !== canonical(output.args)) throw new Error("Tool call differs from the declared plan");
          if (!planApproved) {
            checkingPlan = true;
            try {
              const payload = {
                plan_id: declared.plan_id ?? fingerprint(declared), initial_state: declared.initial_state ?? {},
                steps: declared.steps.map((s, i) => ({
                  ...mapAction(directory, agentId, s.tool, s.args), step_id: `step:${i}`,
                  scheduled_duration_s: s.duration_s ?? 0, post_state: s.post_state ?? {},
                })),
              };
              if (declared.steps.some(s => !["read", "write", "edit"].includes(s.tool))) throw new Error("Plan contains an unmodeled tool");
              const verdict = await request("/v1/plan_check", payload, true);
              audit("plan_decision", { ...record, plan_sha256: fingerprint(declared), verdict });
              if (verdict.plan_decision !== "PERMITTED") throw new Error(`Plan ${verdict.plan_decision}: ${verdict.reason_summary}`);
              planApproved = true;
            } finally { checkingPlan = false; }
          }
        }
        // Reserve before awaiting, preventing concurrent planned steps.
        pending.set(key, { ...record, action });
        reserved = true;
        const verdict = await request("/v1/check", action);
        audit("decision", { ...record, action, verdict });
        if (verdict.decision !== "PERMITTED") throw new Error(`${verdict.decision}: ${verdict.reason_type}`);
      } catch (error) {
        if (reserved) pending.delete(key);
        audit("blocked", { ...record, reason: error.message });
        throw new Error(`[AEGIS] ${error.message}`);
      }
    },
    async "tool.execute.after"(input, output) {
      const key = `${input.sessionID}:${input.callID}`;
      const record = pending.get(key);
      if (!record || record.arguments_sha256 !== fingerprint(input.args)) throw new Error("[AEGIS] Execution record mismatch");
      audit("executed", { ...record, output_sha256: fingerprint(output.output) });
      pending.delete(key);
      if (declared) cursor++;
    },
  };
}

export function loadPlan(path) {
  return path ? JSON.parse(readFileSync(path, "utf8")) : undefined;
}
