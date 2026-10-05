# 비슷한 사례와 구조 (10/5 밤, codex gpt-6-astra high 웹 검색)

사용자 요청: "이런 로직 구성을 어떻게 하면 잘 만들 수 있을지, 비슷한 사례 검색해서 로직 구성에 가장 적합한게 뭔지 수집". 아래는 codex가 1차 출처만 인용해 정리한 원문이다(영어). 우리에게 주는 교훈과 마지막 구조 제안은 출처에서 끌어낸 추천이다.

Primary-source findings, 2024–2026; current documentation is marked. “Lesson for us” and the final architecture are recommendations inferred from the sources.

**A1 — Google components, current docs:** [Gemini](https://ai.google.dev/gemini-api/docs/document-processing) understands visual PDFs; [Custom Extractor](https://docs.cloud.google.com/document-ai/docs/ce-with-genai) extracts schema fields; [Document AI layout parsing](https://docs.cloud.google.com/document-ai/docs/layout-parse-chunk) and [Search parsing](https://docs.cloud.google.com/generative-ai-app-builder/docs/parse-chunk-documents) create structure-aware chunks.  
Lesson for us: Preserve [text/page anchors](https://docs.cloud.google.com/document-ai/docs/reference/rest/v1/Document#Entity), which are optional; review unsupported fields and measure [per-field precision/recall/F1](https://docs.cloud.google.com/document-ai/docs/evaluate). These components do not establish complete automatic onboarding.
**A2 — AWS, 2025 reference:** [Bedrock Data Automation + SageMaker](https://aws.amazon.com/blogs/machine-learning/process-multi-page-documents-with-human-review-using-amazon-bedrock-data-automation-and-amazon-sagemaker-ai/) uses S3 → Step Functions → blueprint extraction with visual grounding/confidence → threshold checks → human field corrections.  
Lesson for us: Calibrate field-specific review thresholds on our documents; this reference discusses calibration but supplies no field-accuracy benchmark.
**A3 — Azure, current reference:** [Document Intelligence → GPT structured extraction](https://learn.microsoft.com/en-us/azure/developer/ai/how-to/extract-entities-using-structured-outputs) produces schema-constrained results; Document Intelligence exposes [text spans and page polygons](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/analyze-document-response?view=doc-intel-4.0.0).  
Lesson for us: Carry source mappings through GPT processing; [confidence supports review routing](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/accuracy-confidence?view=doc-intel-4.0.0), but the GPT sample establishes neither automatic field citations nor measured extraction accuracy.
**A4 — Open-source parsers/service tooling, current docs:** [Unstructured](https://docs.unstructured.io/open-source/concepts/document-elements) retains typed elements/coordinates; [Docling](https://docling-project.github.io/docling/reference/docling_document/) retains page/bbox/character provenance; hosted [LlamaParse Extract](https://developers.llamaindex.ai/llamaparse/extract/guides/response-format/) supplies field citations/confidence, except in spreadsheet mode.  
Lesson for us: Separate parsing quality from factual correctness: [Docling confidence](https://docling-project.github.io/docling/concepts/confidence_scores/) assesses conversion quality; none of these pages supplies comparable product-field accuracy across our input types.

**B1 — NeMo Guardrails, current reference:** [Separate rails](https://docs.nvidia.com/nemo/guardrails/latest/about-nemo-guardrails-library/rail-types) cover inputs, retrieval, dialogue, tool execution, and outputs; execution rails validate tool arguments/results, while output rails can block responses.  
Lesson for us: Place checks at each boundary; “guardrail” does not inherently mean deterministic validation.
**B2 — Guardrails AI, 2024:** [ValidRange](https://guardrailsai.com/hub/validator/guardrails/valid_range) attaches numeric bounds to structured fields, with configured failure handling such as exceptions or regeneration.  
Lesson for us: Keep types, numeric bounds, required evidence IDs, and publication conditions in code; valid structure alone does not establish truth.
**B3 — Google Check Grounding, current docs:** [The API](https://docs.cloud.google.com/generative-ai-app-builder/docs/check-grounding?hl=en) checks claims against supplied facts and returns support scores/source-chunk citations; Google states latency below 500 ms.  
Lesson for us: Check claim support, not merely citation presence; benchmark actual latency and errors because evidence support is neither independent truth nor legal compliance.
**B4 — Google Model Armor, current docs:** [Application integration](https://docs.cloud.google.com/security-command-center/docs/model-armor) submits prompts/responses for configured screening and returns results for application-controlled display/block decisions.  
Lesson for us: Keep the publication gate in code; combine safety screening with separate product-grounding and domain-rule checks.

**C1 — Pharma, AWS MLR proof of concept, 2026:** [Parallel reviewers](https://aws.amazon.com/blogs/industries/medical-legal-regulatory-review-orchestration-with-ai-agents-on-aws/) use regulatory/product documents in prompts and RAG for scientific evidence/approved claims; reported recall exceeds 70%, with approximately two minutes per 1–3 pages.  
Lesson for us: Adapt this evidence-backed review pattern to onboarding; its measured latency does not support the live deadline, and qualified experts retain final decisions.
**C2 — Financial promotions, 2025 announcement:** [RegGenome–finspector](https://reg-genome.com/reggenome-finspector-strategic-partnership-financial-promotions/) proposes source-linked regulations converted into jurisdiction/firm-specific “AI checks”; the vendor says seconds, without publishing model architecture or a latency benchmark.  
Lesson for us: Build source-linked rule records, but do not cite this announcement as proof of LLM/RAG implementation or a 3-second SLA.
**C3 — Cosmetics/live commerce, LiveAMR research, 2025:** [Douyin-clip experiments](https://arxiv.org/html/2512.23280v1) use FunASR → T5 obfuscation normalization → fine-tuned BERT classification; serious-violation F1 rises 0.72→0.87 on a 100-sample classification test set; latency is unreported.  
Lesson for us: Test euphemisms, evasions, and STT errors together; this is research on Douyin content, not evidence of Douyin’s deployed moderation architecture.
**C4 — Video-ad moderation, Tencent RAVEN++, 2025:** [The paper](https://arxiv.org/html/2511.19168v1) encodes a category/subcategory/rule hierarchy through supervised fine-tuning and reinforcement learning, predicts violation timestamps, and reports a one-day production A/B test; latency is unreported.  
Lesson for us: Preserve localized evidence and reviewer hard cases; this supports specialized moderation models, not a proven live-stream latency claim.

**D1 — Long context versus RAG, EMNLP 2024:** [Li et al.](https://aclanthology.org/2024.emnlp-industry.66/) find sufficiently resourced long context stronger on average, RAG cheaper, and Self-Route close to long-context performance at lower cost across their benchmarks.  
Lesson for us: Benchmark full approved rule/product context first when it fits; the paper does not establish a winner for our product sheets.
**D2 — Small knowledge bases, NAACL 2025:** [Wang et al.](https://aclanthology.org/2025.naacl-industry.53/) compare Assistants API with LangChain RAG and report a two-year course deployment; missing relevant knowledge dominates, while reranking provides limited benefit.  
Lesson for us: Measure evidence coverage before adding retrieval agents; this is not a controlled three-way comparison of long context, RAG, and agentic tool use.

**E1 — FACTS Grounding, 2024/2025:** [Google’s benchmark](https://deepmind.google/blog/facts-grounding-a-new-benchmark-for-evaluating-the-factuality-of-large-language-models/) separates 860 public/859 private examples, checks answer eligibility and grounding, and validates multiple model judges against human ratings.  
Lesson for us: Seal release tests; additionally hold out entire products/tenants to test our generalization requirement—FACTS does not establish tenant-level generalization.
**E2 — SimpleQA, 2024:** [OpenAI](https://openai.com/index/introducing-simpleqa/) uses two independent human trainers’ agreeing answers, followed by a third-trainer sample audit; it still estimates approximately 3% dataset error.  
Lesson for us: Independently verify reference answers and adjudicate disagreements; generated tests awaiting approval are not automatically trustworthy ground truth.
**E3 — Judge-bias studies, 2024/2025:** Studies report [self-preference/familiarity bias](https://arxiv.org/abs/2410.21819) and [answer-position bias](https://arxiv.org/abs/2406.07791) in LLM evaluation.  
Lesson for us: Blind model identities, swap comparison order, and calibrate judges against expert labels; multiple judges do not guarantee independence.

**F1 — Anthropic engineering practice, 2024:** [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) recommends simple workflows and notes that one call with retrieval/examples often suffices; agents trade latency and cost for performance.  
Lesson for us: Establish a single-call baseline for each bounded task; add agents only for demonstrated quality gains.
**F2 — LangGraph, 2025:** [Latency guidance](https://www.langchain.com/blog/how-do-i-speed-up-my-agent) recommends fewer calls, code, and parallelism; its [architecture benchmark](https://www.langchain.com/blog/benchmarking-multi-agent-architectures) finds single-agent performance slightly better with one distractor domain, then degrading as domains increase.  
Lesson for us: Route narrowly and remove supervisor paraphrasing; the benchmark measures task scores/tokens, not our end-to-end latency.
**F3 — Google ADK, 2026 reference:** [Graph workflows](https://cloud.google.com/blog/topics/developers-practitioners/graph-workflows-in-adk-everything-you-need-to-know) parallelize independent lookups, join results without an LLM, apply explicit policies in code, and pause for human review.  
Lesson for us: Use deterministic orchestration for known dependencies and publication decisions; reserve model routing for interpreting meaning.

**Best-fit architecture for us — proposed synthesis**

1. Separate asynchronous onboarding from the live Cloud Run path; retain original files, versions, languages, and source locations.
2. Parse by format; have Gemini propose typed product facts with evidence spans, missing-value flags, and conflicts rather than invented completeness.
3. Build separate, versioned law/platform/brand rule records from authoritative sources; brand uploads alone cannot establish complete regulatory coverage.
4. Generate proposed rules and tests automatically; present evidence-linked approval bundles before activating knowledge or policy versions.
5. Keep compact approved rules/current-product facts in context; use Vertex AI Search for larger evidence collections and unresolved questions.
6. Feed Chirp transcripts into bounded compliance/fact/context checks; compare one call against parallel judges, with code-controlled deadlines and alert decisions.
7. Process comments through triage → grouping → grounded drafting → claim verification → publication gate; unsupported or timed-out drafts become host cards.
8. Combine Model Armor screening, grounding checks, and deterministic schema/value/evidence checks; only application code can authorize auto-posting.
9. Run the director asynchronously over approved cues and current state; its planning must not delay host alerts or bypass output checks.
10. Release against sealed product/tenant holdouts and independently checked labels; track field accuracy, violation recall/false alarms, grounding, and audio-to-alert p95/p99—the 3-second target remains unproven.

## 첫 실험: Gemini가 새 제품 문서를 직접 읽기 (10/5 밤, 봉인 코퍼스)

- 6개 가상 브랜드, 10개 파일(PDF 표, 브로슈어, 한국어 워드, HTML, 엑셀 가격표, 글자가 그림 안에 있는 PNG). 정답은 GPT 작성 + Sonnet 블라인드 추출로 확인(가격·용량·함량 숫자는 두 정답이 모두 일치).
- gemini-3.8-flash에 제품별 파일을 통째로 넣고 정해진 형식으로 뽑게 했다(temperature 0, 1회).
- 결과: 가격 10/10, 틀린 가격 0, 카테고리 6/6(식품·헤어 포함), 구버전·신버전 충돌 1/1 발견, 성분 함량 9/12(콜라겐 음료의 1병당 비타민C·아연 값을 성분 대신 핵심 정보에 넣음), 틀린 숫자 0. 제품당 17~30초.
- 한계: 1회 실행, 6개 제품. 주의사항·표현 목록은 개수만 봤고 의미 일치는 아직 채점하지 않았다. 문서 구조 분석기와 Vertex AI Search 구조 분석과의 비교는 남았다.
