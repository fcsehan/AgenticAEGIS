import { useState } from "react";
import { useSessionDraft } from "@/hooks/useSessionDraft";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";

interface RuleDescriptionFormProps {
  draftKey?: string;
  roles: string[];
  actionTypes: string[];
  generating: boolean;
  onGenerate: (
    description: string,
    roles: string[],
    actionTypes: string[],
  ) => void;
}

export function RuleDescriptionForm({
  draftKey = "authoring",
  roles,
  actionTypes,
  generating,
  onGenerate,
}: RuleDescriptionFormProps) {
  const { t } = useTranslation("authoring");
  const [description, setDescription, recoveryError] = useSessionDraft(
    `description:${draftKey}`,
    "",
  );
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [selectedActions, setSelectedActions] = useState<string[]>([]);

  const handleSubmit = () => {
    if (!description.trim()) return;
    onGenerate(description, selectedRoles, selectedActions);
  };

  return (
    <div className="space-y-5">
      {recoveryError && <p role="alert">{recoveryError}</p>}
      <div>
        <label className="block text-sm font-semibold text-slate-800 mb-1.5">
          {t("describeRules")}
        </label>
        <textarea
          className="block w-full rounded-md border border-slate-300 bg-white px-3 py-2.5 text-sm shadow-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 min-h-[200px] resize-y font-normal"
          placeholder={t("describeRulesPlaceholder")}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>

      {roles.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            {t("filterRoles")}
          </label>
          <div className="flex flex-wrap gap-2">
            {roles.map((role) => (
              <button
                key={role}
                type="button"
                onClick={() =>
                  setSelectedRoles((prev) =>
                    prev.includes(role)
                      ? prev.filter((r) => r !== role)
                      : [...prev, role],
                  )
                }
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  selectedRoles.includes(role)
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                    : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {role}
              </button>
            ))}
          </div>
        </div>
      )}

      {actionTypes.length > 0 && (
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1.5">
            {t("filterActions")}
          </label>
          <div className="flex flex-wrap gap-2">
            {actionTypes.map((action) => (
              <button
                key={action}
                type="button"
                onClick={() =>
                  setSelectedActions((prev) =>
                    prev.includes(action)
                      ? prev.filter((a) => a !== action)
                      : [...prev, action],
                  )
                }
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  selectedActions.includes(action)
                    ? "border-indigo-500 bg-indigo-50 text-indigo-700"
                    : "border-slate-300 bg-white text-slate-600 hover:bg-slate-50"
                }`}
              >
                {action}
              </button>
            ))}
          </div>
        </div>
      )}

      <Button
        onClick={handleSubmit}
        disabled={generating || !description.trim()}
        size="lg"
        className="w-full"
      >
        {generating ? t("generating") : t("generateRules")}
      </Button>
    </div>
  );
}
