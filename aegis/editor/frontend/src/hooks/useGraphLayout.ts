import { useMemo } from "react";
import dagre from "dagre";
import type { Node, Edge } from "@xyflow/react";

const NODE_WIDTH = 200;
const NODE_HEIGHT = 60;

/** Compute a top-down dagre layout for React Flow nodes and edges. */
export function useGraphLayout(nodes: Node[], edges: Edge[]) {
  return useMemo(() => {
    if (nodes.length === 0) return { nodes: [], edges };

    const g = new dagre.graphlib.Graph();
    g.setDefaultEdgeLabel(() => ({}));
    g.setGraph({ rankdir: "TB", nodesep: 40, ranksep: 60 });

    for (const node of nodes) {
      g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
    }
    for (const edge of edges) {
      g.setEdge(edge.source, edge.target);
    }

    dagre.layout(g);

    const layoutedNodes = nodes.map((node) => {
      const pos = g.node(node.id);
      return {
        ...node,
        position: {
          x: pos.x - NODE_WIDTH / 2,
          y: pos.y - NODE_HEIGHT / 2,
        },
      };
    });

    return { nodes: layoutedNodes, edges };
  }, [nodes, edges]);
}
