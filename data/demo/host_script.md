# Demo host script (recording v1)

This is the scripted run used to record the demo video. The host speaks the lines into the real microphone.
If no microphone is available, the Demo Console can inject each line as a final transcript (same pipeline).

- Language: English. Market: Singapore. Currency: S$.
- Products: Hydra Barrier Cream (`daon_lab_hydra_barrier_c_288d9c77`), then Deep Hydration Ampoule (`daon_lab_deep_hydration__2d51f429`).
- Bursts (`B1`..`B5`) are defined in `data/demo/comment_script.json` and are fired from the Demo Console.
- Background chatter from `data/demo/comment_pool.json` runs during the whole broadcast.
- "Expected" lists what must be visible on screen. Use it as the acceptance checklist for the recording.

| Scene | Who acts | Line or action | Expected on screen |
|---|---|---|---|
| S01 Setup | Operator | Open `/setup`. The two shipped PDFs are listed as "Indexed locally" (no upload). Run Brief Agent for each product. Review and confirm the glossary. Leave the prompter point drafts unapplied. | Glossary list with source sections. "Confirm glossary" shows "Confirmed · version 1". |
| S02 Start | Operator | Open `/studio`. Press **Start broadcast**. | Host: LIVE timer runs, Now = Hydra Barrier Cream, Next = Deep Hydration Ampoule, prompter shows cream points. Operator: Run of show item 01 "On air now". |
| S02 Start | Host | "Hi everyone, welcome to DAON LAB live! Today we start with our Hydra Barrier Cream." | No alert. |
| S02 Start | Host | "It's a lightweight gel-cream, so it absorbs really quickly." | Prompter point daon_lab_hydra_barrier_c_288d9c77-b4 turns light grey with a check mark. |
| S02 Start | Host | "Inside you've got one percent ceramide NP, five percent panthenol and three percent squalane." | daon_lab_hydra_barrier_c_288d9c77-b1 grey. Required counter 1 / 5. |
| S03 Price questions | Operator | Fire burst **B1**. | Reactions appear in chat with no reply. Price questions form one group. When the composer finishes (target ≤ 15 s), one "AI answer" reply quoting S$36.00 answers every asker so far. Later askers are answered at once without a new LLM call (operator chip "Instant answers" increases). Lee repeating the same question does not increase the asker count. The set price question gets its own reply with S$62.00. |
| S04 Grouping | Operator | Fire burst **B2**. | Question desk: "Is it OK for oily skin?" group with 7 unique askers, "Can I use it under makeup?" with 4, dry skin as a separate group. Host top 3 shows oily skin and makeup with suggested answers. Fragrance question is auto-answered. |
| S05 Host answers | Host | (Wait until the oily-skin card shows its suggested answer.) "Raj is asking if it's OK for oily skin. Yes, it's a lightweight gel-cream, so just use a smaller amount on oily areas." | Host: "Posting answer…" chip on the card for 2 s, then the card leaves the top 3. Viewer: reply with "Host answer" badge under Raj's question. |
| S06 Fact error | Host | "And today the live price is only thirty-two dollars." | Host: amber correction bar "✕ S$32 → ○ S$36" with source. Operator: amber Price correction card with Resend to host / Post notice. |
| S06 Fact error | Host | "Sorry, my mistake, the live price is thirty-six dollars." | Correction bar clears on both screens. |
| S07 Compliance | Host | "Use it every night and your wrinkles will disappear overnight." | Within 5 s of speech end: host full-screen red alert with "Say this instead", the spoken phrase, rule ASEAN-3-SKIN-AGEING and its source. Operator: red "Host correction required" card with elapsed timer. If not corrected within 5 s the operator card shows "Not corrected" and the actions pulse. |
| S07 Compliance | Host | "Let me correct that. It helps keep your skin hydrated for up to twenty-four hours in our in-house test." | Host: red screen clears, green "Corrected" confirmation for 1.5 s. Operator: card moves to the alert log with "Corrected in N.N s". Prompter daon_lab_hydra_barrier_c_288d9c77-b2 grey. |
| S08 Negation | Host | "Just to be clear, it does not treat acne. It's a moisturiser." | No full-screen alert. A provisional amber "Checking…" chip may flash and must clear within 3 s. |
| S09 Sensitive | Operator | Fire burst **B3**. | Pregnancy and eczema questions appear only on the operator Question desk as "Needs review". The pregnancy group has a verified AI draft with a citation (Cautions / FAQ). The eczema group has no verified draft (the sheet does not cover eczema), so the operator writes the reply if needed. Shipping question also "Needs review" with no AI draft. Spam, link, phone number and harassment comments are hidden from host and viewer chat; operator sees them under "Show filtered". |
| S09 Sensitive | Operator | Open the pregnancy group, press **Edit reply**, adjust the wording slightly, press **Post**. | Viewer: reply with the "DAON LAB" badge. Group status "Answered". |
| S10 Points | Host | "We patch tested it on thirty-two people and nobody reported a reaction, in our in-house test." | daon_lab_hydra_barrier_c_288d9c77-b3 grey. Required counter 3 / 5. Run of show shows "3 / 5 required points covered". |
| S11 Time sale | Operator | Banners & notices: start **Time sale: extra 10% off**. | Viewer: time sale pop-up and countdown 10:00. Host: TIME SALE chip with countdown. Product card prices switch to promo prices. |
| S11 Time sale | Operator | Fire burst **B4**. | "how much is the cream now?" answered with S$32.40. Set price answered with S$55.80. No stale S$36.00 answer is reused. |
| S12 Switch | Host | "Someone is asking about the ampoule, we'll get to it in a minute." | No switch. |
| S12 Switch | Operator | Before the next line, press **Arm B5 Switch boundary** in the Demo Console. | Console shows "B5 armed". |
| S12 Switch | Host | "Okay, now let me show you our Deep Hydration Ampoule. It has four percent niacinamide." | No banner yet (first switch cue). Operator transcript line shows the chip "switch cue 1/2". daon_lab_deep_hydration__2d51f429-b1 is stored as pre-covered. |
| S12 Switch | Host | "It's a watery gel, just two to three drops after toner." | Second cue: host shows the green bar "Switching to Deep Hydration Ampoule" counting down 5 to 1; operator shows "Switching in 5s" with Cancel. No fact correction appears for this sentence. After the countdown: Now = Deep Hydration Ampoule, Next = End of run sheet. Prompter shows ampoule points with daon_lab_deep_hydration__2d51f429-b1 grey. Cream questions leave the host top 3 (kept on the operator desk). Operator Run of show: item 01 done with actual duration, item 02 on air. |
| S12 Switch | System | B5 fires automatically at the ampoule segment start. | "how much?" 1 s after the switch is attributed to the cream (grace window). "is the cream fragrance free?" is attributed to the cream. Later ampoule questions are attributed to the ampoule. "Does the ampoule sting?" goes to Needs review. |
| S13 Fact error | Host | "This one has ten percent niacinamide." | Amber bar "✕ 10% niacinamide → ○ 4% niacinamide". |
| S13 Fact error | Host | "Sorry, four percent niacinamide." | Bar clears. |
| S14 End | Operator | Press **End broadcast**. | Summary page: per-product duration and question counts, unanswered questions, alert and correction log with correction times, AI-written recap that only uses the numbers shown. |
