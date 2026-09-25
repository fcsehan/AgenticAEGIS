import { getBezierPath, type EdgeProps } from "@xyflow/react";

export function ConflictEdge(props: EdgeProps) {
  const [edgePath] = getBezierPath(props);

  return (
    <g>
      <path
        d={edgePath}
        fill="none"
        stroke="#f59e0b"
        strokeWidth={2}
        strokeDasharray="6 3"
        className="animated"
      />
      <text>
        <textPath
          href={`#${props.id}`}
          startOffset="50%"
          textAnchor="middle"
          className="fill-amber-600 text-[10px]"
        >
          conflict
        </textPath>
      </text>
    </g>
  );
}
