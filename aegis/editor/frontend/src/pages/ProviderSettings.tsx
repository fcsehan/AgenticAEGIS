import { useUnsavedChanges } from "@/hooks/useUnsavedChanges";
import { useEditorText } from "@/hooks/useEditorText";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { requestJson } from "@/api/client";

interface Profile {
  id: string;
  name: string;
  protocol: "openai" | "anthropic";
  type: "local" | "remote";
  baseUrl: string;
  secretEnv: string;
  enabled: boolean;
  allowPrivate: boolean;
  model: string;
  temperature: number;
  maxTokens: number;
  timeout: number;
}
interface Settings {
  schemaVersion: 1;
  revision: number;
  defaultProfile: string;
  profiles: Profile[];
  credentialStatus?: Record<string, boolean>;
}
interface Probe {
  available: boolean;
  error?: string;
  testedAt: string;
  models: { id: string; name: string }[];
}
const inputClass =
  "w-full rounded border border-slate-300 bg-white p-2 text-sm";

export function ProviderSettings() {
  const tx = useEditorText();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  useUnsavedChanges(dirty);
  const [results, setResults] = useState<Record<string, Probe>>({});
  useEffect(() => {
    requestJson<Settings>("/api/llm/settings")
      .then(setSettings)
      .catch((e: Error) => setError(e.message));
  }, []);
  useEffect(() => {
    const before = (event: BeforeUnloadEvent) => {
      if (dirty) event.preventDefault();
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [dirty]);
  const change = (id: string, patch: Partial<Profile>) => {
    setSettings(
      (s) =>
        s && {
          ...s,
          profiles: s.profiles.map((p) =>
            p.id === id ? { ...p, ...patch } : p,
          ),
        },
    );
    setDirty(true);
    setNotice("");
    setResults({});
  };
  async function save() {
    if (!settings) return;
    setBusy(true);
    setError("");
    try {
      const { credentialStatus: _status, ...body } = settings;
      setSettings(
        await requestJson<Settings>("/api/llm/settings", {
          method: "PUT",
          body: JSON.stringify(body),
        }),
      );
      setDirty(false);
      setNotice(
        tx("Saved. Settings persist across backend restarts."),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : tx("Save failed"));
    } finally {
      setBusy(false);
    }
  }
  async function probe(id: string) {
    setBusy(true);
    setError("");
    try {
      const result = await requestJson<Probe>(`/api/llm/profiles/${id}/probe`, {
        method: "POST",
      });
      setResults((r) => ({ ...r, [id]: result }));
    } catch (e) {
      setError(
        e instanceof Error ? e.message : tx("Connection failed"),
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-4xl space-y-5 p-8">
      <Link to="/"> {tx("← Projects")} </Link>
      <h1 className="text-2xl font-semibold">
        {" "}
        {tx("Inference providers and models")}{" "}
      </h1>
      <p>
        {" "}
        {tx(
          "Configure local servers, API endpoints and models for rule generation. localhost refers to the backend machine. Install and load models in the inference service.",
        )}{" "}
      </p>
      {error && (
        <p role="alert" className="text-red-700">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!settings ? (
        <p> {tx("Loading settings…")} </p>
      ) : (
        <>
          <label className="block">
            {" "}
            {tx("Default provider")}{" "}
            <select
              className={inputClass}
              value={settings.defaultProfile}
              onChange={(e) => {
                setSettings({ ...settings, defaultProfile: e.target.value });
                setDirty(true);
              }}
            >
              <option value=""> {tx("No default")} </option>
              {settings.profiles
                .filter((p) => p.enabled)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </select>
          </label>
          {settings.profiles.map((p) => (
            <fieldset key={p.id} className="space-y-3 rounded border p-4">
              <legend className="px-2 font-semibold">{p.name}</legend>
              <div className="grid gap-4 sm:grid-cols-2">
                <label>
                  {" "}
                  {tx("Name")}{" "}
                  <input
                    className={inputClass}
                    value={p.name}
                    onChange={(e) => change(p.id, { name: e.target.value })}
                  />
                </label>
                <label>
                  {" "}
                  {tx("API protocol")}{" "}
                  <select
                    className={inputClass}
                    value={p.protocol}
                    onChange={(e) =>
                      change(p.id, {
                        protocol: e.target.value as Profile["protocol"],
                      })
                    }
                  >
                    <option value="openai">
                      {" "}
                      {tx("OpenAI compatible (LM Studio / Ollama / vLLM)")}{" "}
                    </option>
                    <option value="anthropic">Anthropic Messages</option>
                  </select>
                </label>
                <label>
                  {" "}
                  {tx("Base URL")}{" "}
                  <input
                    className={inputClass}
                    value={p.baseUrl}
                    onChange={(e) => change(p.id, { baseUrl: e.target.value })}
                  />
                </label>
                <label>
                  {" "}
                  {tx("Location")}{" "}
                  <select
                    className={inputClass}
                    value={p.type}
                    onChange={(e) =>
                      change(p.id, { type: e.target.value as Profile["type"] })
                    }
                  >
                    <option value="local">
                      {" "}
                      {tx("Local / private network")}{" "}
                    </option>
                    <option value="remote">
                      {" "}
                      {tx("External API (HTTPS)")}{" "}
                    </option>
                  </select>
                </label>
                <label>
                  {" "}
                  {tx("Secret: backend environment variable")}{" "}
                  <input
                    className={inputClass}
                    value={p.secretEnv}
                    placeholder={tx("e.g. MY_INFERENCE_API_KEY")}
                    onChange={(e) =>
                      change(p.id, { secretEnv: e.target.value })
                    }
                  />
                  <small>
                    {" "}
                    {tx("Enter the variable name, never the key value.")}{" "}
                    {settings.credentialStatus?.[p.id]
                      ? tx("Credential configured.")
                      : ""}
                  </small>
                </label>
                <label>
                  {" "}
                  {tx("Model ID")}{" "}
                  <input
                    className={inputClass}
                    list={`models-${p.id}`}
                    value={p.model}
                    onChange={(e) => change(p.id, { model: e.target.value })}
                  />
                  <datalist id={`models-${p.id}`}>
                    {results[p.id]?.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name}
                      </option>
                    ))}
                  </datalist>
                </label>
              </div>
              <label className="mr-4">
                <input
                  type="checkbox"
                  checked={p.enabled}
                  onChange={(e) => change(p.id, { enabled: e.target.checked })}
                />{" "}
                {tx("Enabled")}{" "}
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={p.allowPrivate}
                  onChange={(e) =>
                    change(p.id, { allowPrivate: e.target.checked })
                  }
                />{" "}
                {tx("Allow loopback / private LAN access")}{" "}
              </label>
              <details>
                <summary> {tx("Advanced inference parameters")} </summary>
                <div className="grid gap-3 sm:grid-cols-3">
                  <label>
                    {" "}
                    {tx("Temperature")}{" "}
                    <input
                      className={inputClass}
                      type="number"
                      min="0"
                      max="2"
                      step="0.1"
                      value={p.temperature}
                      onChange={(e) =>
                        change(p.id, { temperature: Number(e.target.value) })
                      }
                    />
                  </label>
                  <label>
                    {" "}
                    {tx("Maximum output tokens")}{" "}
                    <input
                      className={inputClass}
                      type="number"
                      min="1"
                      max="131072"
                      value={p.maxTokens}
                      onChange={(e) =>
                        change(p.id, { maxTokens: Number(e.target.value) })
                      }
                    />
                  </label>
                  <label>
                    {" "}
                    {tx("Timeout (seconds)")}{" "}
                    <input
                      className={inputClass}
                      type="number"
                      min="1"
                      max="300"
                      value={p.timeout}
                      onChange={(e) =>
                        change(p.id, { timeout: Number(e.target.value) })
                      }
                    />
                  </label>
                </div>
                <p>
                  {" "}
                  {tx(
                    "Context windows and model loading are managed by the inference service.",
                  )}{" "}
                </p>
              </details>
              <div className="flex gap-4">
                <button
                  disabled={busy || dirty || !p.enabled}
                  onClick={() => probe(p.id)}
                >
                  {" "}
                  {tx("Check connection and models")}{" "}
                </button>
                <button
                  onClick={() => {
                    if (window.confirm(`Profil „${p.name}“ entfernen?`)) {
                      setSettings({
                        ...settings,
                        defaultProfile:
                          settings.defaultProfile === p.id
                            ? ""
                            : settings.defaultProfile,
                        profiles: settings.profiles.filter(
                          (x) => x.id !== p.id,
                        ),
                      });
                      setDirty(true);
                    }
                  }}
                >
                  {" "}
                  {tx("Remove profile")}{" "}
                </button>
              </div>
              {results[p.id] && (
                <p role="status">
                  {results[p.id]?.available
                    ? `Reachable · ${results[p.id]?.models.length} models · Tool calling not yet checked`
                    : results[p.id]?.error}{" "}
                  · {results[p.id]?.testedAt ?? "not tested"}
                </p>
              )}
            </fieldset>
          ))}
          <div className="flex gap-4">
            <button
              onClick={() => {
                setSettings({
                  ...settings,
                  profiles: [
                    ...settings.profiles,
                    {
                      id: crypto.randomUUID(),
                      name: "Custom provider",
                      protocol: "openai",
                      type: "local",
                      baseUrl: "http://localhost:1234/v1",
                      secretEnv: "",
                      enabled: true,
                      allowPrivate: true,
                      model: "",
                      temperature: 0,
                      maxTokens: 4000,
                      timeout: 120,
                    },
                  ],
                });
                setDirty(true);
              }}
            >
              {" "}
              {tx("Add provider")}{" "}
            </button>
            <button
              className="rounded bg-indigo-700 px-4 py-2 text-white disabled:opacity-50"
              disabled={busy || !dirty}
              onClick={save}
            >
              {busy ? tx("Please wait…") : tx("Save settings")}
            </button>
          </div>
          {dirty && (
            <p role="status">
              {" "}
              {tx(
                "Unsaved changes. Save before testing the connection.",
              )}{" "}
            </p>
          )}
        </>
      )}
    </main>
  );
}
