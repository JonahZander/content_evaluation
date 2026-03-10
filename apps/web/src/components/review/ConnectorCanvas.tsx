import styles from "@/components/ReviewWorkbench.module.css";

interface ConnectorPath {
  id: string;
  path: string;
  color: string;
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
          strokeWidth="2.5"
          strokeOpacity="0.7"
          strokeLinecap="round"
        />
      ))}
    </svg>
  );
}
