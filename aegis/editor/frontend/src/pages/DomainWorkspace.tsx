import { PlanTestConsole } from "@/components/PlanTestConsole";
import { useEditorText } from "@/hooks/useEditorText";
import { DomainSettings } from "@/components/DomainSettings";
import type { NormFrame, Domain } from "@/types/domain";
import { requestJson } from "@/api/client";
import { PlanConstraintEditor } from "@/components/PlanConstraintEditor";
import { ScenarioPanel } from "@/components/ScenarioPanel";
import { SourceEditor } from "@/components/SourceEditor";
import { TestConsole } from "@/components/TestConsole";
import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  TreeStructure,
  Graph,
  Shield,
  CheckSquare,
  Plus,
  List,
} from "@phosphor-icons/react";
import { useDomainStore } from "@/store/domainStore";
import { useUiStore, type Panel } from "@/store/uiStore";
import { useValidation } from "@/hooks/useValidation";
import { Button, StatusBar } from "@/components/ui";
import { StructurePanel } from "@/components/StructurePanel";
import { HierarchyGraph } from "@/components/HierarchyGraph";
import { GovernancePanel } from "@/components/GovernancePanel";
import { ValidationStatus } from "@/components/ValidationStatus";
import { ConflictResolver } from "@/components/ConflictResolver";
import { RuleEditor } from "@/components/RuleEditor";

const panels: { id: Panel; icon: typeof TreeStructure; label: string }[] = [
  { id: "sources", icon: List, label: "MELD" },
  { id: "test", icon: CheckSquare, label: "Guard test" },
  { id: "structure", icon: TreeStructure, label: "Structure" },
  { id: "graph", icon: Graph, label: "Graph" },
  { id: "rules", icon: List, label: "Rules" },
  { id: "governance", icon: Shield, label: "Governance" },
  { id: "validation", icon: CheckSquare, label: "Validation" },
];

export function DomainWorkspace() {
  const tx = useEditorText();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const domains = useDomainStore((s) => s.domains);
  const domain = domains.find((d) => d.id === id);
  const { activePanel, setActivePanel } = useUiStore();
  const [copyRule, setCopyRule] = useState(false);
  const [editingRule, setEditingRule] = useState<NormFrame | undefined>();
  const [ruleEditorOpen, setRuleEditorOpen] = useState(false);

  const { issues, errors, warnings } = useValidation(domain);


  if (!domain) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="text-center">
          <p className="text-slate-400"> {tx("Domain not found")} </p>
          <Button
            variant="secondary"
            className="mt-4"
            onClick={() => navigate("/")}
          >
            <ArrowLeft size={14} /> {tx("Back to Dashboard")}{" "}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col">
      {/* Top bar */}
      <header className="flex h-12 items-center justify-between border-b border-border px-4">
        <div className="flex items-center gap-3">
          <button
            aria-label={tx("Back to Dashboard")}
            onClick={() => navigate("/")}
            className="rounded p-1 text-slate-400 hover:text-slate-600"
          >
            <ArrowLeft size={16} />
          </button>
          <h1 className="text-sm font-semibold text-slate-800">
            {domain.name}
          </h1>
        </div>

        <div className="flex items-center gap-1">
          {panels.map(({ id: panelId, icon: Icon, label }) => (
            <button
              key={panelId}
              onClick={() => setActivePanel(panelId)}
              className={`flex items-center gap-1.5 rounded-sm px-2.5 py-1.5 text-xs transition-colors ${
                activePanel === panelId
                  ? "bg-accent-subtle text-accent"
                  : "text-slate-500 hover:bg-surface-tertiary hover:text-slate-700"
              }`}
              title={tx(label)}
            >
              <Icon size={14} />
              <span className="hidden sm:inline">{tx(label)}</span>
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate(`/domain/${domain.id}/authoring`)}
          >
            {" "}
            {tx("AI assistant")}{" "}
          </Button>
          {activePanel === "rules" && (
            <Button
              size="sm"
              onClick={() => {
                setCopyRule(false);
                setEditingRule(undefined);
                setRuleEditorOpen(true);
              }}
            >
              <Plus size={14} weight="bold" /> {tx("Add Rule")}{" "}
            </Button>
          )}
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 overflow-hidden">
        {activePanel === "structure" && <StructurePanel domain={domain} />}

        <main className="flex-1 overflow-auto">
          {activePanel === "sources" && (
            <>
              <DomainSettings domain={domain} />
              <SourceEditor key={domain.id} domainId={domain.id} />
            </>
          )}
          {activePanel === "test" && (
            <>
              <TestConsole
                key={`${domain.id}-${domain.revision}`}
                domainId={domain.id}
              />
              <PlanTestConsole
                key={`plan-${domain.id}-${domain.revision}`}
                domain={domain}
              />
              <ScenarioPanel key={domain.id} domainId={domain.id} />
            </>
          )}
          {activePanel === "graph" && (
            <HierarchyGraph
              domain={domain}
              onSelectRule={(rule) => {
                setCopyRule(false);
                setEditingRule(rule);
                setRuleEditorOpen(true);
              }}
            />
          )}

          {activePanel === "rules" && (
            <div className="p-4">
              {domain.rules.length === 0 ? (
                <p className="py-12 text-center text-sm text-slate-400">
                  {" "}
                  {tx(
                    "No rules defined yet. Add your first rule to get started.",
                  )}{" "}
                </p>
              ) : (
                <div className="flex flex-col gap-2">
                  {domain.rules.map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center gap-3 rounded-md border border-border bg-white p-3 text-sm"
                    >
                      <span
                        className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${
                          rule.modality === "OBLIGATORY"
                            ? "bg-blue-100 text-blue-700"
                            : rule.modality === "FORBIDDEN"
                              ? "bg-red-100 text-red-700"
                              : "bg-emerald-100 text-emerald-700"
                        }`}
                      >
                        {rule.modality}
                      </span>
                      <span className="text-xs text-slate-500">
                        {rule.agentRole}
                      </span>
                      <span className="flex-1 font-mono text-xs text-slate-800">
                        {rule.proposition}
                      </span>
                      <button
                        onClick={() => {
                          setCopyRule(false);
                          setEditingRule(rule);
                          setRuleEditorOpen(true);
                        }}
                      >
                        {" "}
                        {tx("Edit")}{" "}
                      </button>
                      <button
                        onClick={() => {
                          setCopyRule(true);
                          setEditingRule(rule);
                          setRuleEditorOpen(true);
                        }}
                      >
                        {tx("Duplicate")}
                      </button>
                      <button
                        onClick={async () => {
                          if (
                            !window.confirm(
                              "Remove this rule from the MELD draft?",
                            )
                          )
                            return;
                          try {
                            const saved = await requestJson<Domain>(
                              `/api/domains/${domain.id}/source-rules/${rule.id}/delete`,
                              {
                                method: "POST",
                                body: JSON.stringify({
                                  revision: domain.revision,
                                }),
                              },
                            );
                            useDomainStore
                              .getState()
                              .updateDomain(domain.id, saved);
                          } catch (e) {
                            window.alert(
                              e instanceof Error
                                ? e.message
                                : "Deletion failed",
                            );
                          }
                        }}
                      >
                        {" "}
                        {tx("Delete")}{" "}
                      </button>
                      <span className="text-[10px] text-slate-400">
                        s:{rule.specificity} {rule.defeasible ? "D" : "ND"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              <PlanConstraintEditor domain={domain} />
            </div>
          )}

          {activePanel === "governance" && <GovernancePanel domain={domain} />}

          {activePanel === "validation" && (
            <div className="flex flex-col gap-4 p-4">
              <ValidationStatus issues={issues} />
              {issues.map((issue) => (
                <button
                  key={`source-${issue.id}`}
                  className="rounded border p-2 text-left text-sm"
                  onClick={() => {
                    const rule = domain.rules.find(
                      (r) => r.id === issue.ruleId,
                    );
                    if (rule) {
                      setEditingRule(rule);
                      setCopyRule(false);
                      setRuleEditorOpen(true);
                    } else setActivePanel("sources");
                  }}
                >
                  {issue.message} — {tx("Open source")}
                </button>
              ))}
              {issues
                .filter((i) => i.relatedRuleId)
                .map((issue) => (
                  <ConflictResolver
                    key={issue.id}
                    issue={issue}
                    domain={domain}
                  />
                ))}
            </div>
          )}

          {activePanel === "structure" && (
            <div className="flex h-full items-center justify-center text-sm text-slate-400">
              {" "}
              {tx(
                "Select a structure element to edit its declaration and relationships.",
              )}{" "}
            </div>
          )}
        </main>
      </div>

      {/* Status bar */}
      <StatusBar errors={errors} warnings={warnings} />

      {/* Rule Editor */}
      <RuleEditor
        key={`${editingRule?.id ?? "new"}-${ruleEditorOpen}`}
        copy={copyRule}
        rule={editingRule}
        domain={domain}
        open={ruleEditorOpen}
        onClose={() => setRuleEditorOpen(false)}
      />
    </div>
  );
}
