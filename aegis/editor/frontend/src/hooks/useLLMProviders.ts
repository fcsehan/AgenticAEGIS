import { editorFetch } from "@/api/client";
import { useState, useCallback } from "react";

export interface ModelInfo {
  id: string;
  name: string;
  contextLength: number | null;
}

export interface LLMProvider {
  id: string;
  name: string;
  type: "local" | "remote";
  baseUrl: string;
  available: boolean;
  models: ModelInfo[];
  error?: string;
}

export function useLLMProviders() {
  const [providers, setProviders] = useState<LLMProvider[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchProviders = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await editorFetch("/api/llm/providers");
      const data: LLMProvider[] = await resp.json();
      setProviders(data);
    } catch {
      setProviders([]);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshProviders = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await editorFetch("/api/llm/providers/refresh", {
        method: "POST",
      });
      const data: LLMProvider[] = await resp.json();
      setProviders(data);
    } catch {
      // Keep existing providers on error
    } finally {
      setLoading(false);
    }
  }, []);

  return { providers, loading, fetchProviders, refreshProviders };
}
