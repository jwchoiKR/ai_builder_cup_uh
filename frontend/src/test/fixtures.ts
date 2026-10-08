// Builders for client-side test data (shapes mirror backend/app/models/session.py).
import type {
  Alert,
  Answer,
  Catalog,
  Comment,
  Message,
  PdCard,
  PrompterItem,
  QuestionGroup,
  Segment,
  Session,
  StateSnapshot,
} from "../app/types";

export const T0 = 1_790_000_000_000;
export const CREAM = "cream_hydra_barrier";
export const AMPOULE = "ampoule_deep_hydration";

export function session(over: Partial<Session> = {}): Session {
  return {
    session_id: "ses_000001",
    runsheet_id: "daon_skincare_demo",
    title: "DAON LAB · Skincare session",
    status: "live",
    started_at: T0,
    ended_at: null,
    current_segment_id: "seg_000001",
    active_promo_id: null,
    promo_started_at: null,
    pinned_notice: null,
    glossary_version: 0,
    doc_version: 0,
    settings_snapshot: {},
    pre_covered: {},
    switch: { last_commit: null },
    cue: null,
    pd_card: null,
    host_slots: [],
    active_promos: [],
    created_at: T0 - 1000,
    ...over,
  };
}

export function segment(over: Partial<Segment> = {}): Segment {
  return {
    segment_id: "seg_000001",
    product_id: CREAM,
    order: 1,
    started_at: T0,
    ended_at: null,
    start_reason: "session_start",
    planned_duration_sec: 900,
    covered_point_ids: [],
    ...over,
  };
}

export function group(over: Partial<QuestionGroup> = {}): QuestionGroup {
  return {
    group_id: "grp_000001",
    product_id: CREAM,
    intent: "suitability",
    condition_slots: { person_type: "oily" },
    canonical_question: "Is it suitable for oily skin?",
    member_comment_ids: ["cm_000001"],
    unique_author_ids: ["u_raj"],
    first_at: T0 + 1000,
    last_at: T0 + 1000,
    route: "HOST",
    route_reason: "intent",
    status: "ready",
    answer_id: null,
    host_slot: "none",
    on_host_since: null,
    pinned_by_operator_at: null,
    recalled_at: null,
    host_verbal_answer_transcript_id: null,
    host_confirmed: false,
    published_message_id: null,
    closed_reason: null,
    score: 1,
    version: 1,
    ...over,
  };
}

export function answer(over: Partial<Answer> = {}): Answer {
  return {
    answer_id: "ans_000001",
    group_id: "grp_000001",
    text: "Yes. It has a lightweight gel-cream texture.",
    citations: [{ passage_id: "DL-CR-01#frequently-asked-questions#is-it-suitable-for-oily-skin", quote: "Yes.", section: "Frequently asked questions" }],
    origin: "ai",
    verified: true,
    verify_errors: [],
    cache_key: null,
    needs_human: false,
    created_at: T0 + 2000,
    ...over,
  };
}

export function comment(over: Partial<Comment> = {}): Comment {
  return {
    comment_id: "cm_000001",
    author_id: "u_raj",
    author_name: "Raj",
    text: "Is it OK for oily skin?",
    received_at: T0 + 1000,
    source: "script",
    visibility: "visible",
    hide_category: null,
    kind: "question",
    analysis_id: null,
    group_id: "grp_000001",
    ...over,
  };
}

export function message(over: Partial<Message> = {}): Message {
  return {
    message_id: "msg_000001",
    kind: "ai_answer",
    text: "It is S$36.00.",
    group_id: "grp_000001",
    reply_to_comment_ids: ["cm_000001"],
    reply_to_author_names: ["Raj"],
    citations: [],
    state: "published",
    created_at: T0 + 3000,
    publish_at: null,
    published_at: T0 + 3000,
    idempotency_key: "ai_answer:grp_000001",
    ...over,
  };
}

export function alert(over: Partial<Alert> = {}): Alert {
  return {
    alert_id: "al_000001",
    kind: "compliance",
    status: "active",
    transcript_id: "tr_000001",
    product_id: CREAM,
    rule_id: "ASEAN-3-SKIN-AGEING",
    severity: "HIGH",
    span: "your wrinkles will disappear overnight",
    say_instead: "Helps keep skin hydrated for up to 24 hours in our in-house test.",
    unverified: false,
    field: null,
    stated_value: null,
    correct_value: null,
    passage_id: null,
    quote: null,
    created_at: T0 + 5000,
    shown_at: T0 + 5000,
    host_rendered_at: null,
    escalated_at: null,
    resolved_at: null,
    corrected_by_transcript_id: null,
    corrected_text: null,
    dismissed_reason: null,
    ...over,
  };
}

/** D-423: the cream's prompter items as the server builds them (backend/app/logic/prompter.py prompter_items) */
export function creamItems(sale = false, cautions = ["Do not apply to broken or damaged skin."]): PrompterItem[] {
  const item = (section: string, kind: PrompterItem["kind"], key: string, text: string, more: Partial<PrompterItem> = {}) =>
    ({ id: `DL-CR-01#prompter#${key}`, key, product_id: CREAM, section, kind, text, ...more });
  const P = "Price & offers";
  return [
    ...(sale
      ? [item(P, "price", "sale-price-promo_time_sale_10", "Time sale price: S$32.40", { label: "TIME SALE", value: "S$32.40", main: true }),
        item(P, "price", "live-price", "Live price: S$36.00", { label: "Live price", value: "S$36.00" })]
      : [item(P, "price", "live-price", "Live price: S$36.00", { label: "LIVE PRICE", value: "S$36.00", main: true }),
        item(P, "price", "list-price", "List price: S$48.00", { label: "List price", value: "S$48.00" })]),
    sale
      ? item(P, "set", "set-set_cream_ampoule-promo_time_sale_10", "Set Hydra Barrier Cream + Deep Hydration Ampoule set: S$55.80",
        { label: "Cream + Ampoule set", value: "S$55.80" })
      : item(P, "set", "set-set_cream_ampoule", "Set Hydra Barrier Cream + Deep Hydration Ampoule set: S$62.00",
        { label: "Cream + Ampoule set", value: "S$62.00" }),
    item("Ingredients", "ingredient", "ingredient-panthenol", "Panthenol: 5%", { name: "Panthenol", value: "5%" }),
    item("Ingredients", "ingredient", "ingredient-squalane", "Squalane: 3%", { name: "Squalane", value: "3%" }),
    item("Ingredients", "ingredient", "ingredient-ceramide_np", "Ceramide NP: 1%", { name: "Ceramide NP", value: "1%" }),
    ...cautions.map((c, i) => item("Cautions", "caution", `caution-${i + 1}`, c)),
  ];
}

export function snapshot(over: Partial<StateSnapshot> = {}): StateSnapshot {
  return {
    last_seq: 10,
    server_time: T0 + 10_000,
    session: session(),
    segments: [segment()],
    prompter: { product_id: CREAM, segment_id: "seg_000001", covered_point_ids: [], required_total: 2,
      required_covered: 0, items: creamItems() },
    groups: [],
    answers: {},
    host_slots: [],
    comments: [],
    messages: [],
    metrics: {},
    ...over,
  };
}

export const catalog: Catalog = {
  brand: "DAON LAB",
  currency: "SGD",
  currency_symbol: "S$",
  products: [
    {
      product_id: CREAM, code: "DL-CR-01", name: "Hydra Barrier Cream", short_name: "the cream", eyebrow: "THE EVERYDAY ESSENTIAL",
      tagline: "", doc: "DAON_LAB_Hydra_Barrier_Cream.pdf", volume: "50 mL", list_price: 48, live_price: 36, hero_badge: "", aliases: [],
      key_facts: { volume: "50 mL", panthenol: "5%", squalane: "3%", ceramide_np: "1%" },
      cautions: ["Do not apply to broken or damaged skin."],
      avoid_saying: [{ say_not: "Heals eczema", say: "Helps relieve the feeling of dryness." }],
      prompter_points: [
        { point_id: "cr-p1", text: "Lightweight gel-cream. Absorbs quickly.", required: false },
        { point_id: "cr-p2", text: "Ceramide NP 1%, panthenol 5%, squalane 3%.", required: true },
        { point_id: "cr-p3", text: "Helps keep skin hydrated for up to 24 hours (in-house test).", required: true },
      ],
      approved_claims: [], not_approved_claims: [], list_price_display: "S$48.00", live_price_display: "S$36.00",
    },
    {
      product_id: AMPOULE, code: "DL-AM-01", name: "Deep Hydration Ampoule", short_name: "the ampoule", eyebrow: "NEXT IN YOUR ROUTINE",
      tagline: "", doc: "DAON_LAB_Deep_Hydration_Ampoule.pdf", volume: "30 mL", list_price: 42, live_price: 32, hero_badge: "", aliases: [],
      key_facts: {},
      prompter_points: [{ point_id: "am-p1", text: "4% niacinamide, clearly stated.", required: true }],
      approved_claims: [], not_approved_claims: [], list_price_display: "S$42.00", live_price_display: "S$32.00",
    },
  ],
  set_offers: [
    {
      set_id: "set_cream_ampoule", name: "Hydra Barrier Cream + Deep Hydration Ampoule set", short_name: "Cream + Ampoule set",
      product_ids: [CREAM, AMPOULE], live_price: 62, live_price_display: "S$62.00",
    },
  ],
  promos: [
    {
      promo_id: "promo_time_sale_10", kind: "time_sale", title: "Time sale: extra 10% off", duration_sec: 600,
      applies_to: [CREAM, AMPOULE, "set_cream_ampoule"], discount_pct_off_live_price: 10,
      promo_prices: { [CREAM]: 32.4, [AMPOULE]: 28.8, set_cream_ampoule: 55.8 },
      promo_prices_display: { [CREAM]: "S$32.40", [AMPOULE]: "S$28.80", set_cream_ampoule: "S$55.80" },
      viewer_text: "TIME SALE", host_text: "TIME SALE", changes_prices: true,
    },
  ],
  runsheets: [
    {
      runsheet_id: "daon_skincare_demo", title: "DAON LAB · Skincare session", brand: "DAON LAB", language: "en", market: "SG",
      items: [
        { order: 1, product_id: CREAM, planned_duration_sec: 900, required_point_ids: ["cr-p2", "cr-p3"] },
        { order: 2, product_id: AMPOULE, planned_duration_sec: 600, required_point_ids: ["am-p1"] },
      ],
      promo_ids: ["promo_time_sale_10"],
    },
  ],
};

export function pdCard(over: Partial<PdCard> = {}): PdCard {
  return {
    card_id: "card_000001",
    kind: "answer_question",
    say: "Yes. Apply sunscreen after the cream, then makeup.",
    detail: "Raj: Can I use it under makeup?",
    ref_id: "grp_000001",
    created_at: T0,
    hold_until: T0 + 15_000,
    status: "active",
    source: "ai",
    ...over,
  };
}
