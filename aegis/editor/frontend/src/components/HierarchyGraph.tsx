import { useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { Domain, NormFrame } from "@/types/domain";
import { useGraphLayout } from "@/hooks/useGraphLayout";
import { ObligationNode } from "./graph/ObligationNode";
import { RuleNode } from "./graph/RuleNode";
import { ConflictEdge } from "./graph/ConflictEdge";

const nodeTypes: NodeTypes = {
  obligation: ObligationNode,
  rule: RuleNode,
};

const edgeTypes: EdgeTypes = {
  conflict: ConflictEdge,
};

interface HierarchyGraphProps {
  domain: Domain;
  onSelectRule?: (rule: NormFrame) => void;
}

export function HierarchyGraph({ domain, onSelectRule }: HierarchyGraphProps) {
  const { rawNodes, rawEdges } = useMemo(() => {
    const nodes: Node[] = [];
    const edges: Edge[] = [];

    // Obligation type nodes
    for (const ot of domain.obligationTypes) {
      nodes.push({
        id: `ot-${ot.id}`,
        type: "obligation",
        position: { x: 0, y: 0 },
        data: { label: ot.name, description: ot.description },
      });
      for (const child of ot.children) {
        nodes.push({
          id: `ot-${child.id}`,
          type: "obligation",
          position: { x: 0, y: 0 },
          data: { label: child.name, description: child.description },
        });
        edges.push({
          id: `e-${ot.id}-${child.id}`,
          source: `ot-${ot.id}`,
          target: `ot-${child.id}`,
        });
      }
    }

    for (const ot of domain.obligationTypes) {
      if (ot.parentId)
        edges.push({
          id: `parent-${ot.id}`,
          source: `ot-${ot.parentId}`,
          target: `ot-${ot.id}`,
        });
    }
    for (const role of domain.roles) {
      nodes.push({
        id: `role-${role.id}`,
        type: "obligation",
        position: { x: 0, y: 0 },
        data: { label: role.name, description: role.description },
      });
      if (role.obligationType)
        edges.push({
          id: `role-parent-${role.id}`,
          source: `ot-${role.obligationType}`,
          target: `role-${role.id}`,
        });
    }
    for (const rule of domain.rules) {
      nodes.push({
        id: `rule-${rule.id}`,
        type: "rule",
        position: { x: 0, y: 0 },
        data: {
          label: `${rule.agentRole} / ${rule.code}`,
          modality: rule.modality,
          proposition: rule.proposition,
        },
      });
      const role = domain.roles.find((r) => r.name === rule.agentRole);
      if (role)
        edges.push({
          id: `role-rule-${rule.id}`,
          source: `role-${role.id}`,
          target: `rule-${rule.id}`,
        });
    }
    // Only declared structure is shown. Conflict decisions belong to the backend Guard.

    return { rawNodes: nodes, rawEdges: edges };
  }, [domain]);

  const { nodes, edges } = useGraphLayout(rawNodes, rawEdges);

  return (
    <div className="h-full w-full">
      <ReactFlow
        onNodeClick={(_, node) => {
          const rule = domain.rules.find((r) => `rule-${r.id}` === node.id);
          if (rule) onSelectRule?.(rule);
        }}
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#e2e8f0" gap={16} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
