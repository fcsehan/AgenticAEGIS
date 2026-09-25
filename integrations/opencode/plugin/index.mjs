// Copyright 2026 Frank Csehan. SPDX-License-Identifier: Apache-2.0
import { createGuardHooks, loadPlan } from "./core.mjs";

export default async function AegisPlugin({ directory }) {
  return createGuardHooks({
    directory,
    guardUrl: process.env.AEGIS_OPENCODE_GUARD_URL ?? "http://127.0.0.1:8000",
    agentId: process.env.AEGIS_OPENCODE_AGENT_ID ?? "opencodeAgent",
    auditPath: process.env.AEGIS_OPENCODE_AUDIT_PATH,
    timeoutMs: Number(process.env.AEGIS_OPENCODE_TIMEOUT_MS ?? 3000),
    plan: loadPlan(process.env.AEGIS_OPENCODE_PLAN),
  });
}
