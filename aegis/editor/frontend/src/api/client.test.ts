import { afterEach, describe, expect, it, vi } from "vitest";
import { api, editorFetch } from "./client";
import { parseVerdict } from "./contracts";

afterEach(() => vi.unstubAllGlobals());
describe("real editor client boundary", () => {
  it("sends the editor write header and preserves server failure", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Revision changed" }), {
        status: 409,
      }),
    );
    vi.stubGlobal("fetch", fetch);
    await expect(
      editorFetch("/api/example", { method: "PUT", body: "{}" }),
    ).rejects.toThrow("Revision changed");
    expect(fetch.mock.calls[0]?.[1].headers.get("X-Aegis-Editor")).toBe("1");
  });
  it("rejects incomplete project payloads instead of claiming success", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          new Response(JSON.stringify({ domains: [] }), { status: 200 }),
        ),
    );
    await expect(api.openProject("/workspace")).rejects.toThrow(
      "Invalid project response",
    );
  });
  it("does not convert transport errors or malformed data into UNDECIDABLE", () => {
    expect(() => parseVerdict({ error: "offline" })).toThrow(
      "Invalid Guard verdict",
    );
    expect(() =>
      parseVerdict({ decision: "PERMITTED", justificationChain: [] }),
    ).toThrow();
    expect(
      parseVerdict({
        decision: "UNDECIDABLE",
        reasonType: "NO_JURISDICTION",
        revision: "abc",
        justificationChain: [],
      }).decision,
    ).toBe("UNDECIDABLE");
  });
});
