import { levenshtein } from "./levenshtein";

describe("levenshtein", () => {
  it("returns 0 for identical strings", () => {
    expect(levenshtein("hello", "hello")).toBe(0);
  });

  it("returns length of other string when one is empty", () => {
    expect(levenshtein("", "abc")).toBe(3);
    expect(levenshtein("abc", "")).toBe(3);
  });

  it("returns 0 for two empty strings", () => {
    expect(levenshtein("", "")).toBe(0);
  });

  it("counts single substitution", () => {
    expect(levenshtein("cat", "bat")).toBe(1);
  });

  it("counts single insertion", () => {
    expect(levenshtein("cat", "cats")).toBe(1);
  });

  it("counts single deletion", () => {
    expect(levenshtein("cats", "cat")).toBe(1);
  });

  it("handles completely different strings", () => {
    expect(levenshtein("abc", "xyz")).toBe(3);
  });

  it("handles case-sensitive comparison", () => {
    expect(levenshtein("ABC", "abc")).toBe(3);
  });

  it("handles realistic typo: 'Field Agnet' → 'Field Agent'", () => {
    // transposition = 2 edits in Levenshtein (not Damerau)
    expect(levenshtein("agnet", "agent")).toBe(2);
  });

  it("handles realistic typo: single-char substitution in role name", () => {
    expect(levenshtein("Safety Monitr", "Safety Monitor")).toBe(1);
  });
});
