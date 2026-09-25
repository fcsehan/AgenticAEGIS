import {
  useCallback,
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { useProjectStore } from "@/store/projectStore";

/** Recovery copy in this browser tab, never authoritative MELD or release evidence. */
export function useSessionDraft<T>(
  name: string,
  initial: T,
): [T, Dispatch<SetStateAction<T>>, string, () => void] {
  const project = useProjectStore((s) => s.project?.path ?? "no-project");
  const key = `aegis-draft:${project}:${name}`;
  const read = (storageKey: string) => {
    try {
      const saved = sessionStorage.getItem(storageKey);
      return saved ? (JSON.parse(saved) as T) : initial;
    } catch {
      return initial;
    }
  };
  const [error, setError] = useState("");
  const [state, setState] = useState(() => ({ key, value: read(key) }));
  useEffect(() => {
    if (state.key !== key) {
      setState({ key, value: read(key) });
      return;
    }
    try {
      sessionStorage.setItem(key, JSON.stringify(state.value));
      setError("");
    } catch {
      setError(
        "Browser recovery unavailable. Save changes before closing.",
      );
    }
  }, [key, state]);
  const setValue: Dispatch<SetStateAction<T>> = useCallback(
    (next) => {
      setState((current) => ({
        key,
        value:
          typeof next === "function"
            ? (next as (previous: T) => T)(
                current.key === key ? current.value : read(key),
              )
            : next,
      }));
    },
    [key],
  );
  return [
    state.key === key ? state.value : initial,
    setValue,
    error,
    () => sessionStorage.removeItem(key),
  ];
}
