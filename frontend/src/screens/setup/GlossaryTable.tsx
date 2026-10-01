// Glossary review (§12.7 step 2, D-094): include or exclude terms, edit a term, its kind and spoken
// forms, or add a term. Nothing is saved until "Confirm glossary".
import { useState } from "react";

import { Button, Chip } from "../../components";
import type { GlossaryKind, GlossaryTerm } from "./setupApi";
import styles from "./setup.module.css";

export interface TermRow extends GlossaryTerm {
  include: boolean;
  edited?: boolean;
  added?: boolean;
}

const KINDS: GlossaryKind[] = ["brand", "product", "ingredient", "technical", "value"];
export const MAX_TERM_CHARS = 100;
export const ADDED_SOURCE = "Added on /setup";

const splitForms = (text: string) =>
  text
    .split(",")
    .map((f) => f.trim().replace(/\s+/g, " "))
    .filter(Boolean);

interface Draft {
  term: string;
  kind: GlossaryKind;
  forms: string;
}

export function GlossaryTable({
  productId,
  rows,
  onChange,
}: {
  productId: string;
  rows: TermRow[];
  onChange: (rows: TermRow[]) => void;
}) {
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState<Draft>({ term: "", kind: "technical", forms: "" });
  const [error, setError] = useState<string | null>(null);

  const startEdit = (i: number, row: TermRow) => {
    setEditing(i);
    setDraft({ term: row.term, kind: row.kind, forms: row.spoken_forms.join(", ") });
    setError(null);
  };

  const cancel = () => {
    if (editing !== null && rows[editing]?.added && !rows[editing].term) onChange(rows.filter((_, j) => j !== editing));
    setEditing(null);
    setError(null);
  };

  const save = () => {
    if (editing === null) return;
    const term = draft.term.trim().replace(/\s+/g, " ");
    if (!term || term.length > MAX_TERM_CHARS) return setError(`A term needs 1 to ${MAX_TERM_CHARS} characters.`);
    if (rows.some((r, j) => j !== editing && r.term.toLowerCase() === term.toLowerCase()))
      return setError(`"${term}" is already in the list.`);
    const forms = splitForms(draft.forms).filter((f, k, all) => all.findIndex((x) => x.toLowerCase() === f.toLowerCase()) === k);
    if (forms.some((f) => f.length > MAX_TERM_CHARS)) return setError(`A spoken form needs at most ${MAX_TERM_CHARS} characters.`);
    const old = rows[editing];
    const changed = old.term !== term || old.kind !== draft.kind || old.spoken_forms.join("|") !== forms.join("|");
    onChange(
      rows.map((r, j) =>
        j === editing ? { ...r, term, kind: draft.kind, spoken_forms: forms, edited: r.edited || (changed && !r.added) } : r,
      ),
    );
    setEditing(null);
    setError(null);
  };

  const add = () => {
    onChange([...rows, { term: "", kind: "technical", spoken_forms: [], source_section: ADDED_SOURCE, include: true, added: true }]);
    setEditing(rows.length);
    setDraft({ term: "", kind: "technical", forms: "" });
    setError(null);
  };

  return (
    <>
      <table className={styles.table} data-testid={`setup-glossary-${productId}`}>
        <thead>
          <tr>
            <th>Include</th>
            <th>Term</th>
            <th>Kind</th>
            <th>Spoken forms</th>
            <th>Source section</th>
            <th aria-label="Actions" />
          </tr>
        </thead>
        <tbody>
          {rows.map((t, i) =>
            editing === i ? (
              <tr key={`edit-${i}`} className={styles.editRow}>
                <td />
                <td>
                  <input
                    className={styles.input}
                    aria-label="Term"
                    value={draft.term}
                    autoFocus
                    onChange={(e) => setDraft({ ...draft, term: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") save();
                      if (e.key === "Escape") cancel();
                    }}
                  />
                </td>
                <td>
                  <select
                    className={styles.input}
                    aria-label="Kind"
                    value={draft.kind}
                    onChange={(e) => setDraft({ ...draft, kind: e.target.value as GlossaryKind })}
                  >
                    {KINDS.map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                </td>
                <td>
                  <input
                    className={styles.input}
                    aria-label="Spoken forms"
                    placeholder="comma separated, e.g. hydra barrier cream"
                    value={draft.forms}
                    onChange={(e) => setDraft({ ...draft, forms: e.target.value })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") save();
                      if (e.key === "Escape") cancel();
                    }}
                  />
                </td>
                <td className={styles.muted}>{t.source_section}</td>
                <td className={styles.rowActions}>
                  <Button size="sm" variant="primary" onClick={save}>
                    Save term
                  </Button>
                  <Button size="sm" variant="ghost" onClick={cancel}>
                    Cancel
                  </Button>
                </td>
              </tr>
            ) : (
              <tr key={`${t.term}-${i}`} className={t.include ? undefined : styles.excluded}>
                <td>
                  <input
                    type="checkbox"
                    checked={t.include}
                    aria-label={`Include ${t.term}`}
                    onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, include: e.target.checked } : r)))}
                  />
                </td>
                <td className={styles.term}>
                  {t.term}
                  {t.added ? (
                    <Chip tone="accent" className={styles.termChip}>Added</Chip>
                  ) : t.edited ? (
                    <Chip tone="accent" className={styles.termChip}>Edited</Chip>
                  ) : null}
                </td>
                <td>
                  <Chip>{t.kind}</Chip>
                </td>
                <td className={styles.muted}>{t.spoken_forms.join(", ")}</td>
                <td className={styles.muted}>{t.source_section}</td>
                <td className={styles.rowActions}>
                  <Button size="sm" variant="ghost" disabled={editing !== null} aria-label={`Edit ${t.term}`} onClick={() => startEdit(i, t)}>
                    Edit
                  </Button>
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
      {error && (
        <p className={styles.errorText} role="alert">
          {error}
        </p>
      )}
      <Button size="sm" className={styles.addTerm} disabled={editing !== null} onClick={add}>
        Add term
      </Button>
    </>
  );
}
