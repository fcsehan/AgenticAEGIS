import { renderHook, act } from "@testing-library/react";
import { useRuleWizard } from "./useRuleWizard";
import type { NormFrame } from "@/types/domain";

/** Helper: advance wizard to a given step with all prerequisites filled. */
function advanceTo(result: { current: ReturnType<typeof useRuleWizard> }, step: number) {
  if (step >= 1) {
    act(() => result.current.update({ modality: "FORBIDDEN" }));
  }
  if (step >= 2) {
    act(() => result.current.next()); // 1 → 2
    act(() => result.current.update({ agentRole: "Agent", code: "c1" }));
  }
  if (step >= 3) {
    act(() => result.current.next()); // 2 → 3
    act(() => result.current.update({ proposition: "do-harm" }));
  }
  if (step >= 4) {
    act(() => result.current.next()); // 3 → 4
  }
}

describe("useRuleWizard", () => {
  it("starts at step 1 with empty data", () => {
    const { result } = renderHook(() => useRuleWizard());
    expect(result.current.step).toBe(1);
    expect(result.current.totalSteps).toBe(4);
    expect(result.current.isFirstStep).toBe(true);
    expect(result.current.isLastStep).toBe(false);
    expect(result.current.data.modality).toBeNull();
  });

  it("cannot proceed from step 1 without selecting modality", () => {
    const { result } = renderHook(() => useRuleWizard());
    expect(result.current.canProceed).toBe(false);

    act(() => result.current.next());
    expect(result.current.step).toBe(1); // didn't advance
  });

  it("advances to step 2 after selecting modality", () => {
    const { result } = renderHook(() => useRuleWizard());
    act(() => result.current.update({ modality: "FORBIDDEN" }));
    expect(result.current.canProceed).toBe(true);

    act(() => result.current.next());
    expect(result.current.step).toBe(2);
  });

  it("cannot proceed from step 2 without agentRole and code", () => {
    const { result } = renderHook(() => useRuleWizard());
    advanceTo(result, 2);
    // Remove agentRole+code to test the guard
    act(() => result.current.update({ agentRole: "", code: "" }));
    expect(result.current.canProceed).toBe(false);

    act(() => result.current.update({ agentRole: "Agent" }));
    expect(result.current.canProceed).toBe(false); // still need code

    act(() => result.current.update({ code: "c1" }));
    expect(result.current.canProceed).toBe(true);
  });

  it("cannot proceed from step 3 without proposition", () => {
    const { result } = renderHook(() => useRuleWizard());
    advanceTo(result, 3);
    // Clear proposition to test the guard
    act(() => result.current.update({ proposition: "" }));
    expect(result.current.step).toBe(3);
    expect(result.current.canProceed).toBe(false);

    act(() => result.current.update({ proposition: "report-safety" }));
    expect(result.current.canProceed).toBe(true);
  });

  it("step 4 always allows proceeding", () => {
    const { result } = renderHook(() => useRuleWizard());
    advanceTo(result, 4);
    expect(result.current.step).toBe(4);
    expect(result.current.isLastStep).toBe(true);
    expect(result.current.canProceed).toBe(true);
  });

  it("back() goes to previous step, minimum step 1", () => {
    const { result } = renderHook(() => useRuleWizard());
    advanceTo(result, 2);
    expect(result.current.step).toBe(2);

    act(() => result.current.back());
    expect(result.current.step).toBe(1);

    act(() => result.current.back());
    expect(result.current.step).toBe(1); // stays at 1
  });

  it("reset() returns to step 1 with initial data", () => {
    const { result } = renderHook(() => useRuleWizard());
    advanceTo(result, 3);
    act(() => result.current.reset());
    expect(result.current.step).toBe(1);
    expect(result.current.data.modality).toBeNull();
    expect(result.current.data.proposition).toBe("");
  });

  it("toNormFrame() returns null when modality is not set", () => {
    const { result } = renderHook(() => useRuleWizard());
    expect(result.current.toNormFrame()).toBeNull();
  });

  it("toNormFrame() returns a valid NormFrame", () => {
    const { result } = renderHook(() => useRuleWizard());
    act(() => {
      result.current.update({
        modality: "FORBIDDEN",
        agentRole: "Agent",
        code: "c1",
        proposition: "  do-harm  ",
        specificity: 3,
        defeasible: false,
      });
    });
    const frame = result.current.toNormFrame("test-id");
    expect(frame).not.toBeNull();
    expect(frame!.id).toBe("test-id");
    expect(frame!.modality).toBe("FORBIDDEN");
    expect(frame!.proposition).toBe("do-harm"); // trimmed
    expect(frame!.specificity).toBe(3);
    expect(frame!.defeasible).toBe(false);
  });

  it("initializes from existing rule when provided", () => {
    const existing: NormFrame = {
      id: "n1",
      code: "c2",
      agentRole: "Commander",
      modality: "OBLIGATORY",
      proposition: "authorize",
      specificity: 2,
      defeasible: true,
    };
    const { result } = renderHook(() => useRuleWizard(existing));
    expect(result.current.data.modality).toBe("OBLIGATORY");
    expect(result.current.data.agentRole).toBe("Commander");
    expect(result.current.data.code).toBe("c2");
    expect(result.current.data.proposition).toBe("authorize");
    expect(result.current.canProceed).toBe(true); // step 1, modality is set
  });
});
