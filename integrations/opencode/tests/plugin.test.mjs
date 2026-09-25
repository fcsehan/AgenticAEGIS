import test from "node:test";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { mkdtempSync, readFileSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createGuardHooks, fingerprint, mapAction } from "../plugin/core.mjs";

async function fixture(t, respond) {
  const directory = mkdtempSync(join(tmpdir(), "aegis-plugin-"));
  const requests = [];
  const server = createServer(async (req, res) => {
    let text = "";
    for await (const chunk of req) text += chunk;
    const body = JSON.parse(text);
    requests.push(body);
    const result = await respond(body, req.url);
    if (res.destroyed) return;
    res.writeHead(result.status ?? 200, { "Content-Type": "application/json" });
    res.end(JSON.stringify(result.body));
  });
  await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    rmSync(directory, { recursive: true, force: true });
  });
  const auditPath = join(directory, "audit.jsonl");
  const config = { directory, agentId: "opencodeAgent", guardUrl: `http://127.0.0.1:${server.address().port}`, auditPath, timeoutMs: 100 };
  return { directory, config, requests, records: () => readFileSync(auditPath, "utf8").trim().split("\n").map(JSON.parse) };
}

function verdict(body, decision = "PERMITTED") {
  return { body: { decision, reason_type: "EXPLICIT_NORM", justification_chain: ["fixture"], action_type: body.action_type, agent_id: body.agent_id } };
}
const input = { tool: "write", sessionID: "s", callID: "c" };
const output = (directory, path = "allowed.txt") => ({ args: { filePath: join(directory, path), content: "example" } });

test("permitted call has correlated decision and execution hashes", async t => {
  const f = await fixture(t, b => verdict(b));
  const hooks = createGuardHooks(f.config);
  const out = output(f.directory);
  await hooks["tool.execute.before"](input, out);
  await hooks["tool.execute.after"]({ ...input, args: out.args }, { output: "written" });
  const records = f.records();
  assert.equal(records[1].arguments_sha256, records[2].arguments_sha256);
  assert.equal(records[1].verdict.decision, "PERMITTED");
});

for (const decision of ["FORBIDDEN", "UNDECIDABLE"]) {
  test(`${decision} blocks and retains the verdict`, async t => {
    const f = await fixture(t, b => verdict(b, decision));
    const hooks = createGuardHooks(f.config);
    await assert.rejects(hooks["tool.execute.before"](input, output(f.directory)), new RegExp(decision));
    assert.equal(f.records()[1].verdict.decision, decision);
    assert.equal(f.records().at(-1).event, "blocked");
  });
}

for (const kind of ["http", "malformed", "mismatch", "timeout"]) {
  test(`${kind} guard failure blocks`, async t => {
    const f = await fixture(t, async body => {
      if (kind === "timeout") await new Promise(resolve => setTimeout(resolve, 250));
      if (kind === "http") return { status: 503, body: {} };
      if (kind === "malformed") return { body: { decision: "PERMITTED" } };
      if (kind === "mismatch") return verdict({ ...body, agent_id: "anotherAgent" });
      return verdict(body);
    });
    const hooks = createGuardHooks(f.config);
    await assert.rejects(hooks["tool.execute.before"](input, output(f.directory)), /GUARD_ERROR/);
  });
}

test("mutated arguments receive a fresh check; no permission cache reuse", async t => {
  const f = await fixture(t, b => verdict(b, b.proposition.path === "protected.txt" ? "FORBIDDEN" : "PERMITTED"));
  const hooks = createGuardHooks(f.config);
  const first = output(f.directory);
  await hooks["tool.execute.before"](input, first);
  await hooks["tool.execute.after"]({ ...input, args: first.args }, { output: "written" });
  await assert.rejects(hooks["tool.execute.before"]({ ...input, callID: "next" }, output(f.directory, "protected.txt")), /FORBIDDEN/);
  assert.equal(f.requests.length, 2);
  assert.notEqual(f.requests[0].context.arguments_sha256, f.requests[1].context.arguments_sha256);
});

test("shared arguments and the enclosing output cannot change after checking", async t => {
  const f = await fixture(t, b => verdict(b));
  const hooks = createGuardHooks(f.config);
  const out = output(f.directory);
  await hooks["tool.execute.before"](input, out);
  assert.throws(() => { out.args.filePath = "protected.txt"; }, TypeError);
  assert.throws(() => { out.args = {}; }, TypeError);
});

test("unknown tools remain blocked even if a sidecar returns permission", async t => {
  const f = await fixture(t, b => verdict(b));
  const hooks = createGuardHooks(f.config);
  await assert.rejects(hooks["tool.execute.before"]({ ...input, tool: "bash" }, { args: { command: "true" } }), /UNMODELED_TOOL/);
});

test("path traversal and symlinks outside the workspace block", async t => {
  const f = await fixture(t, b => verdict(b));
  symlinkSync(tmpdir(), join(f.directory, "escape"));
  for (const path of ["../outside.txt", "escape/outside.txt"]) {
    assert.throws(() => mapAction(f.directory, "opencodeAgent", "write", { filePath: join(f.directory, path) }), /outside/);
  }
});

test("a changed declared step blocks before contacting the guard", async t => {
  const f = await fixture(t, b => verdict(b));
  const hooks = createGuardHooks({ ...f.config, plan: { steps: [{ tool: "write", args: output(f.directory).args }] } });
  await assert.rejects(hooks["tool.execute.before"](input, output(f.directory, "protected.txt")), /differs/);
  assert.equal(f.requests.length, 0);
});

test("plan rejection prevents any individual action approval", async t => {
  const f = await fixture(t, () => ({ body: { plan_decision: "FORBIDDEN", reason_summary: "aggregate", violations: [], per_step_verdicts: [] } }));
  const out = output(f.directory);
  const hooks = createGuardHooks({ ...f.config, plan: { steps: [{ tool: "write", args: out.args }] } });
  await assert.rejects(hooks["tool.execute.before"](input, out), /Plan FORBIDDEN/);
  assert.equal(f.requests.length, 1);
});

test("unwritable audit prevents initialization", async t => {
  const f = await fixture(t, b => verdict(b));
  assert.throws(() => createGuardHooks({ ...f.config, auditPath: f.directory }));
});

test("a declared plan advances only after completion and cannot be replayed", async t => {
  const f = await fixture(t, (b, endpoint) => endpoint === "/v1/plan_check"
    ? { body: { plan_decision: "PERMITTED", reason_summary: "approved", violations: [], per_step_verdicts: [] } }
    : verdict(b));
  const out = output(f.directory);
  const hooks = createGuardHooks({ ...f.config, plan: { steps: [{ tool: "write", args: out.args }] } });
  await hooks["tool.execute.before"](input, out);
  await assert.rejects(hooks["tool.execute.before"]({ ...input, callID: "parallel" }, output(f.directory)), /Concurrent/);
  // A rejected duplicate must not remove the original pending execution.
  await assert.rejects(hooks["tool.execute.before"](input, output(f.directory)), /Duplicate/);
  await hooks["tool.execute.after"]({ ...input, args: out.args }, { output: "written" });
  await assert.rejects(hooks["tool.execute.before"]({ ...input, callID: "replay" }, output(f.directory)), /differs/);
  assert.equal(f.requests.length, 2);
});

test("after hook rejects a different argument payload", async t => {
  const f = await fixture(t, b => verdict(b));
  const hooks = createGuardHooks(f.config);
  await hooks["tool.execute.before"](input, output(f.directory));
  await assert.rejects(hooks["tool.execute.after"]({ ...input, args: output(f.directory, "protected.txt").args }, { output: "changed" }), /mismatch/);
  assert.ok(!f.records().some(r => r.event === "executed"));
});

test("fingerprints are independent of object property order", () => {
  assert.equal(fingerprint({ a: 1, b: 2 }), fingerprint({ b: 2, a: 1 }));
});
