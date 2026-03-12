import styles from "@/components/ReviewWorkbench.module.css";
import type { ArtifactEvent } from "@/lib/types";

interface CommentRailProps {
  events: ArtifactEvent[];
}

function getEventSourceLabel(event: ArtifactEvent): string {
  const metadataModelName = typeof event.metadata.model_name === "string" ? event.metadata.model_name : null;
  const metadataProviderName = typeof event.metadata.provider_name === "string" ? event.metadata.provider_name : null;
  return (
    event.model_name ??
    event.provider_name ??
    metadataModelName ??
    metadataProviderName ??
    (event.event_type === "run" ? "run lifecycle" : "not recorded")
  );
}

function getAttemptLabel(event: ArtifactEvent): string | null {
  if (!event.attempt) {
    return null;
  }
  if (event.max_attempts) {
    return `Attempt ${event.attempt} of ${event.max_attempts}`;
  }
  return `Attempt ${event.attempt}`;
}

export function CommentRail({ events }: CommentRailProps) {
  return (
    <section className={styles.eventPanel}>
      <div className={styles.sectionTitle}>Run log</div>
      {events.length ? (
        events.map((event) => (
          <article key={event.id} className={styles.eventItem} data-testid={`run-event-${event.id}`}>
            <div className={styles.eventBody}>
              <strong>{event.agent_name ?? event.stage}</strong>
              <div>{event.message}</div>
            </div>
            <div className={styles.eventMeta}>
              <span className={styles.pill}>{event.status}</span>
              <span>{getAttemptLabel(event) ?? (event.agent_name ? event.stage : "run")}</span>
              <span>{getEventSourceLabel(event)}</span>
            </div>
          </article>
        ))
      ) : (
        <div className={styles.emptyEventState}>No run events yet.</div>
      )}
    </section>
  );
}
