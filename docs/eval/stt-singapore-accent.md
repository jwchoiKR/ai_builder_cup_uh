# chirp_3 on Singapore-accented speech (10/5)

**Data:** IMDA National Speech Corpus, Part 1 (read speech), Singapore Open Data Licence, via the Hugging Face copy `recursal/reprocessed_singapore_national_speech_corpus`.
- Sample A: 1 speaker (SP0402), 100 sentences.
- Sample B: 15 speakers × 12 sentences = 180 sentences, taken from the first 2.5 GB of the `Channel_0-00` shard.
- Ground truth: the corpus `read_text` field.

**Method:** Speech-to-Text V2 batch Recognize with `chirp_3`, region `us`, automatic punctuation on (the same model and region as production). WER is computed after lower-casing, removing punctuation and spelling out digits. Script: `stt_wer_nsc.py`.

| language code | WER, sample A (1 speaker) | WER, sample B (15 speakers) |
|---|---|---|
| en-US (production) | 4.46% | 7.03% |
| en-GB | 4.65% | 7.03% |
| en-AU | 4.52% | 7.03% |
| en-IN | 4.46% | 7.09% (5 failed calls) |
| en-PH | 4.46% | not run |
| auto | 4.76% (5 failed calls) | not run |

**Result:** the language code makes no measurable difference on Singapore English. Keep `en-US`; `en-SG` is not offered by chirp_3.
- WER per speaker ranges from 1.6% to 18.3%. The two hardest speakers are at 16-18%.
- Part of the measured error is normalisation, not recognition: corpus markers (`<NON/>`, `<SPK/>`), "gun shot" vs "gunshot", "twelve o' clock" vs "12:00".
- Real misses look like "dog fleeing" → "duck flying" and "boot" → "wood".

**Limits:** these are general read sentences, not product talk. Product names, ingredient percentages and prices depend on the phrase hints (glossary) and are not measured here. Conversational Part 3 in the Hugging Face copy has empty transcripts, so it could not be scored.
