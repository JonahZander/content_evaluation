import styles from "@/components/ReviewWorkbench.module.css";

interface ConnectorPath {
  id: string;
  path: string;
  color: string;
  active: boolean;
}

interface ConnectorCanvasProps {
  paths: ConnectorPath[];
}

export function ConnectorCanvas({ paths }: ConnectorCanvasProps) {
  return (
    <svg className={styles.connectorCanvas} data-testid="connector-canvas" aria-hidden="true">
      {paths.map((item) => (
        <path
          key={item.id}
          data-testid={`connector-${item.id}`}
          d={item.path}
          fill="none"
          stroke={item.color}
          strokeWidth={item.active ? "2.5" : "1.75"}
          strokeOpacity={item.active ? "0.92" : "0.55"}
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
}
