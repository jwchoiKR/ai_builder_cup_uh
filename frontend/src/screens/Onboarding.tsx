// Product onboarding: rebuilt from scratch (the old page was removed).
import { Eyebrow, HubLink } from "../components";
import styles from "./onboarding/onboarding.module.css";

export function Onboarding() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <Eyebrow>
          <HubLink sessionId={null} /> · PRODUCT ONBOARDING
        </Eyebrow>
      </header>
    </div>
  );
}

export default Onboarding;
