import styles from "@/components/ReviewWorkbench.module.css";
import type { ArtifactEvent } from "@/lib/types";

interface CommentRailProps {
  events: ArtifactEvent[];
}

function getEventSourceLabel(event: ArtifactEvent): string {
  const metadataModelName = typeof event.metadata.model_name === "string" ? event.metadata.model_name : null;
  const metadataProviderName = typeof event.metadata.provider_name === "string" ? event.metadata.provider_name : null;
  return event.model_name ?? metadataModelName ?? metadataProviderName ?? (event.event_type === "run" ? "run lifecycle" : "not recorded");
}

export function CommentRail({ events }: CommentRailProps) {
  return (
    <aside className={styles.commentPane}>
      <section className={styles.eventPanel}>
        <div className={styles.sectionTitle}>Run log</div>
        {events.length ? (
          events.map((event) => (
            <div key={event.id} className={styles.eventItem}>
              <div>
                <strong>{event.stage}</strong>
                <div>{event.message}</div>
              </div>
              <div className={styles.eventMeta}>
                {event.agent_name ?? "system"}
                <br />
                {getEventSourceLabel(event)}
              </div>
            </div>
          ))
        ) : (
          <div className={styles.emptyEventState}>No run events yet.</div>
        )}
      </section>
    </aside>
  );
}
