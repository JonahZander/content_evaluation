import styles from "@/components/ReviewWorkbench.module.css";

export function ReviewHero() {
  return (
    <section className={styles.hero}>
      <div className={styles.eyebrow}>Content Evaluation</div>
      <h1 className={styles.heroTitle}>Analysis workbench</h1>
    </section>
  );
}
