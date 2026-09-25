import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { useSessionDraft } from "./useSessionDraft";
import { useProjectStore } from "@/store/projectStore";
beforeEach(() => {
  sessionStorage.clear();
  useProjectStore.getState().closeProject();
});
it("recovers unsaved text after leaving and reopening the editor", () => {
  const first = renderHook(() => useSessionDraft("source", ""));
  act(() => first.result.current[1]("unsaved normative source"));
  first.unmount();
  const reopened = renderHook(() => useSessionDraft("source", ""));
  expect(reopened.result.current[0]).toBe("unsaved normative source");
});
it("keeps different draft scopes separate", () => {
  const first = renderHook(() => useSessionDraft("domain-one", ""));
  act(() => first.result.current[1]("first"));
  const second = renderHook(() => useSessionDraft("domain-two", ""));
  expect(second.result.current[0]).toBe("");
});
it("does not copy a mounted draft into a new project scope", () => {
  const hook = renderHook(() => useSessionDraft("same-domain", ""));
  act(() => hook.result.current[1]("original project draft"));
  act(() =>
    useProjectStore
      .getState()
      .setProject({
        path: "/second",
        name: "Second",
        domains: [],
        meldFiles: [],
        loadedAt: "",
      }),
  );
  expect(hook.result.current[0]).toBe("");
  act(() => hook.result.current[1]("second project draft"));
  act(() => useProjectStore.getState().closeProject());
  expect(hook.result.current[0]).toBe("original project draft");
});
