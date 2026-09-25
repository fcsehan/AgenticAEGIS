import { useEditorText } from "@/hooks/useEditorText";
import { requestJson } from "@/api/client";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { useLLMProviders, type LLMProvider } from "@/hooks/useLLMProviders";

interface ProviderSelectorProps {
  selectedProviderId: string;
  selectedModelId: string;
  onProviderChange: (providerId: string) => void;
  onModelChange: (modelId: string) => void;
}

const typeColors = {
  local: "bg-blue-100 text-blue-700",
  remote: "bg-violet-100 text-violet-700",
};

export function ProviderSelector({
  selectedProviderId,
  selectedModelId,
  onProviderChange,
  onModelChange,
}: ProviderSelectorProps) {
  const tx = useEditorText();
  const { t } = useTranslation("authoring");
  const [capability, setCapability] = useState("");
  useEffect(() => {
    setCapability("");
  }, [selectedProviderId, selectedModelId]);
  const [testing, setTesting] = useState(false);
  const { providers, loading, fetchProviders, refreshProviders } =
    useLLMProviders();

  useEffect(() => {
    fetchProviders();
  }, [fetchProviders]);

  const selectedProvider = providers.find((p) => p.id === selectedProviderId);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-800">
          {t("selectProvider")}
        </h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={refreshProviders}
          disabled={loading}
        >
          {t("refreshProviders")}
        </Button>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {providers.map((provider) => (
          <ProviderCard
            key={provider.id}
            provider={provider}
            selected={provider.id === selectedProviderId}
            onSelect={() => {
              onProviderChange(provider.id);
              onModelChange("");
              setCapability("");
              if (provider.models.length > 0) {
                onModelChange(provider.models[0]!.id);
              }
            }}
          />
        ))}
      </div>

      <Link to="/settings/providers"> {tx("Configure providers")} </Link>
      {selectedProvider && selectedProvider.models.length > 0 && (
        <div>
          <label
            htmlFor="provider-model"
            className="block text-sm font-medium text-slate-700 mb-1.5"
          >
            {t("selectModel")}
          </label>
          <select
            id="provider-model"
            className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            value={selectedModelId}
            onChange={(e) => onModelChange(e.target.value)}
          >
            {selectedProvider.models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <label className="block">
        {" "}
        {tx("Model ID (manual entry supported)")}{" "}
        <input
          className="block w-full rounded border p-2"
          value={selectedModelId}
          onChange={(e) => {
            onModelChange(e.target.value);
            setCapability("");
          }}
        />
      </label>
      <Button
        disabled={testing || !selectedProviderId || !selectedModelId}
        onClick={async () => {
          setTesting(true);
          setCapability("");
          try {
            const result = await requestJson<{
              passed: boolean;
              detail: string;
            }>(`/api/llm/profiles/${selectedProviderId}/capability`, {
              method: "POST",
              body: JSON.stringify({ model: selectedModelId }),
            });
            setCapability(result.detail);
          } catch (e) {
            setCapability(
              e instanceof Error ? e.message : "Check failed",
            );
          } finally {
            setTesting(false);
          }
        }}
      >
        {testing ? tx("Checking…") : tx("Test tool calling")}
      </Button>
      {capability && <p role="status">{capability}</p>}
    </div>
  );
}

function ProviderCard({
  provider,
  selected,
  onSelect,
}: {
  provider: LLMProvider;
  selected: boolean;
  onSelect: () => void;
}) {
  const tx = useEditorText();
  const { t } = useTranslation("authoring");

  return (
    <Card
      interactive={true}
      className={`relative ${
        selected ? "ring-2 ring-indigo-500 border-indigo-500" : ""
      } ${!provider.available ? "opacity-50" : ""}`}
      onClick={onSelect}
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold text-sm text-slate-900">
            {provider.name}
          </p>
          <span
            className={`inline-block mt-1 rounded-full px-2 py-0.5 text-xs font-medium ${
              typeColors[provider.type]
            }`}
          >
            {provider.type === "local"
              ? t("providerLocal")
              : t("providerRemote")}
          </span>
        </div>
        {!provider.available && (
          <span className="text-xs text-slate-400">
            {t("providerUnavailable")}
          </span>
        )}
      </div>
      {provider.available && (
        <p className="mt-2 text-xs text-slate-500">
          {provider.models.length} {tx("model(s)")}{" "}
        </p>
      )}
      {provider.error && (
        <p className="mt-1 text-xs text-red-500 truncate">{provider.error}</p>
      )}
    </Card>
  );
}
