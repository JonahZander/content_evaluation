import styles from "@/components/ReviewWorkbench.module.css";

interface ReviewHeroProps {
  overallScore: number;
  verdict: string;
}

export function ReviewHero({ overallScore, verdict }: ReviewHeroProps) {
  return (
    <section className={styles.hero}>
      <div className={styles.eyebrow}>Content Evaluation Workbench</div>
      <div className={styles.titleRow}>
        <div>
          <h1 className={styles.heroTitle}>Read the draft. Trace every agent judgment. Reply where it matters.</h1>
          <p className={styles.heroCopy}>
            The document stays on the left, the comment threads stay on the right, and every judgment remains tied to
            highlighted text. Export the full analysis as Markdown or JSON when the review is done.
          </p>
        </div>
        <aside className={styles.scorePanel}>
          <span className={styles.scoreLabel}>Overall evaluation</span>
          <strong className={styles.scoreValue}>{overallScore}</strong>
          <p className={styles.scoreCaption}>{verdict}</p>
        </aside>
      </div>
    </section>
  );
}
