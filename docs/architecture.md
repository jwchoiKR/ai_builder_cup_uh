# Agent architecture

**In one sentence:** there is no main or orchestrator agent. The backend code orchestrates: an event-driven pipeline, one runtime per broadcast session. It calls six single-purpose LLM agents, each once per input. Each agent returns one JSON object checked against a schema.

| | |
|---|---|
| **Orchestration** | Backend code (FastAPI, one `SessionRuntime` per session). Every step order, retry, route and publish decision is code. |
| **Agents** | 6 single-call agents: one request, one validated JSON reply, a fixed deadline. Agents have no tools, no memory between calls and no loops, and they never call each other. |
| **Between agents** | Code passes outputs on. Examples: triage output → grouping and routing → composer input; judge output → alerts, prompter, switch. |
| **Guards** | Deterministic checks before and after the agents: prefilter, reflex, `verify_answer`, the correction check, the switch state machine, the publish decision. |

## 1. System overview

```mermaid
flowchart LR
  subgraph IN["Inputs"]
    MIC["Host microphone"]
    CMT["Viewer comments"]
    PDF["Product sheet PDFs"]
  end
  subgraph BE["Backend code: the orchestrator (one runtime per session)"]
    STTC["Speech-to-Text client (audio WebSocket)"]
    UP["Utterance pipeline"]
    CP["Comment pipeline"]
    SP["Setup pipeline"]
    SUMP["Summary pipeline"]
    ACT["Operator and session API (REST)"]
    STORE[("Setup store: glossary, prompter points")]
    BUS[["Event bus: stored events, SSE"]]
  end
  subgraph GC["Google Cloud"]
    GSTT["Speech-to-Text V2 (chirp_3)"]
    subgraph AG["LLM agents on Vertex AI Gemini: one call each, JSON out"]
      J["Compliance Judge"]
      X["Context Judge"]
      F["Fact Checker"]
      T["Comment Triage"]
      C["Answer Composer"]
      B["Brief Agent"]
      S["Broadcast Summary"]
    end
  end
  DATA[("Product sheets, passages, claim rules, promos")]
  subgraph OUT["Screens"]
    H["Host"]
    O["Operator"]
    V["Viewer"]
  end
  MIC -- "audio" --> STTC
  STTC <--> GSTT
  STTC --> UP
  CMT --> CP
  PDF --> SP
  UP <--> J
  UP <--> X
  UP <--> F
  CP <--> T
  CP <--> C
  SP <--> B
  SUMP <--> S
  SP --> STORE
  STORE -. "prompter points: next session" .-> UP
  STORE -. "glossary: next mic connection" .-> STTC
  ACT -- "End broadcast" --> SUMP
  DATA -.-> UP
  DATA -.-> CP
  DATA -.-> SP
  UP --> BUS
  CP --> BUS
  SUMP --> BUS
  ACT --> BUS
  BUS -- "SSE" --> H
  BUS -- "SSE" --> O
  BUS -- "SSE" --> V
  O -- "approve, dismiss, push, switch, start/end" --> ACT
  H -- "cancel switch (Esc)" --> ACT
  classDef agent fill:#F2C46D,stroke:#8A5A00,color:#1D1400
  class J,F,T,C,B,S agent
```

**Notes on the overview:**
- **Setup does not emit events.** It stores the confirmed glossary and prompter points. The glossary is used from the next mic connection as phrase hints, and the prompter points from the next session. `/setup` uses REST only.
- **Actions come back over REST:** operator actions (`api/operator.py`, 22 routes) and session start/end (`api/sessions.py`). Mic audio arrives over a WebSocket (`api/audio_ws.py`).
- **Google Cloud runs the speech recognition and the models.** The backend holds the code that calls them: audio relay, prompt building, schema validation, deadlines.

## 2. Comment path (viewer question → answer)

```mermaid
flowchart TD
  A["Viewer comment"] --> P{"Prefilter: reaction, spam, link, phone number"}
  P -- "reaction or hidden" --> X["Shown or hidden, no AI call"]
  P -- "text to analyse" --> TC{"Triage cache hit?"}
  TC -- "yes" --> G
  TC -- "no" --> T["Comment Triage (LLM, 2.5 s)"]
  T --> G["Product attribution and grouping: same question, same group"]
  G --> CMP{"Answerable from the product sheet?"}
  CMP -- "no (e.g. shipping)" --> OP["Operator: Needs review"]
  CMP -- "yes" --> AC{"Answer cache hit?"}
  AC -- "yes" --> VF
  AC -- "no" --> CO["Answer Composer (LLM, 12 s, sheet passages)"]
  CO --> VF{"verify_answer: citations, numbers, unapproved claims"}
  VF -- "not verified" --> OP
  VF -- "verified" --> R{"Route by question type"}
  R -- "AUTO (e.g. price)" --> AUTO["AI answer posted to viewers"]
  R -- "HOST (e.g. skin type)" --> HOST["Host top-3 card with suggested answer"]
  R -- "OPERATOR (sensitive, e.g. pregnancy)" --> OPD["Operator: draft to approve"]
  classDef agent fill:#F2C46D,stroke:#8A5A00,color:#1D1400
  class T,CO agent
```

## 3. Utterance path (host speech → alerts, prompter, switch)

```mermaid
flowchart TD
  M["Host speaks"] --> STT["Speech-to-Text: final transcript about 1 s after speech end"]
  STT --> MG{"Previous final unfinished (no . ? !) and at most 3.5 s ago?"}
  MG -- "yes" --> JT["Use the joined text"]
  MG -- "no" --> OT["Use this final"]
  JT --> RF["Reflex: banned-phrase scan, instant provisional alert"]
  OT --> RF
  RF --> CJ["Compliance Judge (LLM, 2.5 s)"]
  RF --> XJ["Context Judge (LLM, 2.5 s)"]
  RF --> F["Fact Checker (LLM, 3 s, sheet passages)"]
  CJ --> AL["Compliance alert: red overlay on host"]
  CJ --> CR{"Correction? approved wording or explicit retraction required"}
  CR -- "yes" --> OK["Green 'Corrected'"]
  XJ --> PR["Prompter: mark points said"]
  XJ --> SW["Product switch: named transition, then a product fact, then 5 s countdown"]
  XJ --> PUB["Host answered an open question: post the reply (needs all three verdicts)"]
  F --> FN["Fact note: stated value vs sheet value"]
  CJ -. "judge failed or timed out" .-> FB["Fallback: un-negated HIGH reflex hit becomes an unverified alert"]
  classDef agent fill:#F2C46D,stroke:#8A5A00,color:#1D1400
  class CJ,XJ,F agent
```

The Compliance Judge, the Context Judge and the Fact Checker run **in parallel** for each final (`JUDGE_MODE=split3`, D-099). Each verdict is applied the moment it arrives, so the red alert never waits for the prompter or the fact check. `JUDGE_MODE=split` puts both judges' jobs in one Utterance Judge (rollback); `single` adds the fact check to that call.

## 4. One sentence, end to end

```mermaid
sequenceDiagram
  autonumber
  participant Host
  participant STT as Speech-to-Text
  participant BE as Backend (code)
  participant J as Compliance Judge (LLM)
  participant X as Context Judge (LLM)
  participant F as Fact Checker (LLM)
  participant UI as Host and Operator screens
  Host->>STT: "your wrinkles will disappear overnight"
  STT->>BE: final transcript (about 1 s)
  BE->>BE: reflex scan, provisional alert
  par compliance
    BE->>J: utterance + recent lines + rules + open alerts
    J-->>BE: violation: ageing claim, HIGH
  and context
    BE->>X: utterance + recent lines + open questions + prompter points
    X-->>BE: product talk, no point covered
  and facts
    BE->>F: utterance + product sheet passages
    F-->>BE: no wrong facts
  end
  BE->>UI: red overlay "Say this instead" (target 5 s p95 after speech end)
  Host->>STT: "Let me correct that. It helps keep skin hydrated for up to 24 hours..."
  STT->>BE: final transcript
  BE->>J: utterance + open alerts
  J-->>BE: corrects the alert
  BE->>BE: correction check: approved wording heard
  BE->>UI: green "Corrected"
```

## 5. Before and after the broadcast

```mermaid
flowchart LR
  subgraph PRE["Before the broadcast (/setup)"]
    U["PDF upload"] --> IX["Check, read, match product, split, index"]
    IX --> BA["Brief Agent (LLM, 60 s)"]
    BA --> ED["Operator reviews and edits glossary and point drafts"]
    ED --> CF["Confirm glossary"]
    CF --> HINT["STT phrase hints and prompter points for the next session"]
  end
  subgraph POST["After the broadcast (/summary)"]
    END["End broadcast"] --> ST["Statistics computed by code"]
    ST --> BS["Broadcast Summary (LLM, 30 s)"]
    BS --> CK["Recap sentences checked against the numbers"]
    CK --> PG["Summary page and PDF report"]
  end
  classDef agent fill:#F2C46D,stroke:#8A5A00,color:#1D1400
  class BA,BS agent
```

## The seven agents

| Agent | Runs | Input | Output | Model, deadline | If it fails |
|---|---|---|---|---|---|
| Comment Triage | each comment (cache first) | comment, product on air, open question groups | kind, intent, product, canonical question, group to join | gemini-3.5-flash-lite (MINIMAL), 2.5 s | question goes to operator review |
| Answer Composer | each new question group (cache first) | canonical question, product sheet passages, set offers, active promo | answer, citations, grounded, needs_human | gemini-3.8-flash (LOW), 12 s | group goes to operator review |
| Compliance Judge | each final transcript | utterance (joined if split), recent lines, claim rules, approved claims, open alerts with their "say this instead" | violations (negated / quoted), corrections | gemini-3.5-flash-lite (MINIMAL), 2.5 s | reflex decides: un-negated HIGH hit becomes an unverified alert |
| Context Judge | each final transcript, in parallel | utterance (joined if split), recent lines, run sheet, open questions, prompter points, cues | answered question, points said, switch signal | gemini-3.5-flash-lite (MINIMAL), 2.5 s | prompter and switch skip that sentence; no host answer posted |
| Fact Checker | each final transcript, in parallel with the judges | utterance, retrieved sheet passages, active promo | claims: supported / contradicted with the sheet value | gemini-3.5-flash-lite (MINIMAL), 3 s | no fact note for that sentence |
| Brief Agent | /setup, per product | product sheet text | glossary terms, prompter point drafts | gemini-3.8-flash (MEDIUM), 60 s | error shown, previous result kept |
| Broadcast Summary | after "End broadcast" | statistics computed by code | headline, highlights, watch-outs, follow-ups | gemini-3.8-flash (MEDIUM), 30 s | statistics shown without a recap |

**What agents never do:**
- call each other or any tool;
- post to viewers by themselves;
- decide numbers shown on screens;
- change state directly.

Every effect goes through code that checks it first. Settings are in `.env.example`, and the decisions behind them are in `docs/DECISIONS.md`.
