// Viewer chat identity (§12.5): display name asked once, random author id; stored in localStorage
// under `ls.viewer.name` / `ls.viewer.id`. Every access is wrapped in try/catch.
export const NAME_KEY = "ls.viewer.name";
export const ID_KEY = "ls.viewer.id";

export interface ViewerIdentity {
  authorId: string;
  name: string;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function randomId(): string {
  try {
    if (typeof crypto !== "undefined" && "randomUUID" in crypto) return `v_${crypto.randomUUID().slice(0, 12)}`;
  } catch {
    /* fall through */
  }
  return `v_${Math.random().toString(36).slice(2, 14)}`;
}

export function readIdentity(): ViewerIdentity | null {
  try {
    const s = storage();
    const name = s?.getItem(NAME_KEY)?.trim();
    const id = s?.getItem(ID_KEY)?.trim();
    return name && id ? { authorId: id, name } : null;
  } catch {
    return null;
  }
}

/** Saves the name (and an id if none yet). Works in memory when storage is unavailable. */
export function saveIdentity(name: string): ViewerIdentity {
  const clean = name.trim().slice(0, 40);
  let id: string | null = null;
  try {
    const s = storage();
    id = s?.getItem(ID_KEY) ?? null;
    if (!id) {
      id = randomId();
      s?.setItem(ID_KEY, id);
    }
    s?.setItem(NAME_KEY, clean);
  } catch {
    /* storage unavailable: keep the identity for this page only */
  }
  return { authorId: id ?? randomId(), name: clean };
}
