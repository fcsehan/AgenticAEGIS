import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import type { PreCondition, ReleaseResult } from "@/hooks/useAuthoringWizard";

interface ReleaseGateProps {
  preconditions: PreCondition[];
  canRelease: boolean;
  onFetchPreconditions: () => void;
  onFetchLegalDoc: (locale: string) => void;
  onRelease: (version: string, message: string) => Promise<ReleaseResult>;
  legalDocMarkdown: string;
}

export function ReleaseGate({
  preconditions,
  canRelease,
  onFetchPreconditions,
  onFetchLegalDoc,
  onRelease,
  legalDocMarkdown,
}: ReleaseGateProps) {
  const { t } = useTranslation("authoring");
  const [version, setVersion] = useState("1.0.0");
  const [message, setMessage] = useState("");
  const [releasing, setReleasing] = useState(false);
  const [result, setResult] = useState<ReleaseResult | null>(null);
  const docLocale = "en";

  useEffect(() => {
    onFetchPreconditions();
  }, [onFetchPreconditions]);

  const handleRelease = async () => {
    setReleasing(true);
    try {
      const res = await onRelease(version, message);
      setResult(res);
    } finally {
      setReleasing(false);
    }
  };

  const handleExportDoc = () => {
    onFetchLegalDoc(docLocale);
  };

  // Download legal doc as file
  const handleDownloadDoc = () => {
    if (!legalDocMarkdown) return;
    const blob = new Blob([legalDocMarkdown], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `legal-doc-${docLocale}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (result?.success) {
    return (
      <Card className="text-center py-8 space-y-3">
        <div className="text-4xl">✓</div>
        <p className="text-lg font-semibold text-emerald-800">
          {t("releaseSuccess")}
        </p>
        <p className="text-sm text-slate-600">
          {t("version")}: {result.version}
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary */}
      <div>
        <h3 className="text-sm font-semibold text-slate-800 mb-3">
          {t("summary")}
        </h3>
        <p className="text-sm text-slate-600">
          {canRelease ? t("allPreconditionsMet") : t("preconditionsNotMet")}
        </p>
      </div>

      {/* Preconditions Checklist */}
      <div>
        <h3 className="text-sm font-semibold text-slate-800 mb-3">
          {t("preconditions")}
        </h3>
        <div className="space-y-2">
          {preconditions.map((pc) => (
            <div
              key={pc.id}
              className={`flex items-center gap-3 rounded-md border px-4 py-3 ${
                pc.satisfied
                  ? "border-emerald-200 bg-emerald-50"
                  : "border-red-200 bg-red-50"
              }`}
            >
              <span
                className={`text-lg font-bold ${pc.satisfied ? "text-emerald-600" : "text-red-500"}`}
              >
                {pc.satisfied ? "✓" : "✕"}
              </span>
              <div className="flex-1">
                <p
                  className={`text-sm font-medium ${pc.satisfied ? "text-emerald-800" : "text-red-800"}`}
                >
                  {pc.label}
                </p>
                <p className="text-xs text-slate-500">{pc.detail}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Legal Document Export */}
      <div className="space-y-3">
        <h3 className="text-sm font-semibold text-slate-800">
          {t("exportLegalDoc")}
        </h3>
        <div className="flex items-center gap-3">
          <Button variant="secondary" size="sm" onClick={handleExportDoc}>
            Generate
          </Button>
          {legalDocMarkdown && (
            <Button variant="ghost" size="sm" onClick={handleDownloadDoc}>
              Download .md
            </Button>
          )}
        </div>
      </div>

      {/* Release Controls */}
      <div className="space-y-3 border-t border-slate-200 pt-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              {t("version")}
            </label>
            <input
              type="text"
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              value={version}
              onChange={(e) => setVersion(e.target.value)}
              placeholder="1.0.0"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">
              {t("releaseMessage")}
            </label>
            <input
              type="text"
              className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
            />
          </div>
        </div>
        <Button
          size="lg"
          className="w-full"
          disabled={!canRelease || releasing}
          onClick={handleRelease}
        >
          {releasing ? "Releasing..." : t("releaseForProduction")}
        </Button>
        {result?.error && (
          <p className="text-sm text-red-600">{result.error}</p>
        )}
      </div>
    </div>
  );
}
