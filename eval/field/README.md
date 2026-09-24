# Field robustness evaluation (spec S8, task C4.9)

Every accuracy number Herald has published so far comes from **typed** sentences written by the team's annotators.
This evaluation answers the question a judge will ask next: *does it still work when someone who isn't us speaks, in
their own words, with road noise?*

The design is "the label is the card, not the speech". Each fact card lists a few facts to get across ("woman, 72;
left side of her face is drooping; blood pressure 188 over 102; takes Eliquis"). The speaker says them however
they like, with no script. The clip then goes through the product's own path, Whisper speech-to-text and then the
live extraction model, called exactly as the app calls it (the card's mic, speaker and dispatch). The result is
scored against the card's labels with the same scorer as the held-out gold sets (`eval/bench_extract.py`).

## Files

| Path | What | In git? |
|---|---|---|
| `eval/field_cards_v1.jsonl` | the 30 fact cards: what to say (`say`) and the gold facts (`facts`) | yes |
| `eval/field/protocol.yaml` | consent wording (versioned), conditions, cards per speaker, clip limits, capture settings | yes |
| `eval/field/recorder.py` + `recorder.html` | the recording station (port 8103) | yes |
| `eval/field_bench.py` | speech-to-text → extractor → scores, 3 runs, confidence intervals | yes |
| `eval/field_v1.jsonl` | the manifest: one line per clip (speaker code, card, condition, file). No names | yes |
| `data/field_audio/<speaker>/<card>_<condition>.wav` | the recordings (16 kHz mono WAV) | **no**: voices are personal data |
| `data/field_audio/consent.jsonl` | who consented (by code) to which consent version, and withdrawals | no |
| `data/field_audio/_transcripts.jsonl`, `_bench/` | cached transcripts, per-clip results, the omission review file | no: transcripts are what people said |
| `eval/dumps/field_v1/<model>_summary.json` | numbers only: spread over runs, per-key table, intervals | yes |

## How the cards were written

The card writer could read only the labeling guide (`docs/LABELING_GUIDE.md`), the vocabulary and the county
checklists, and was forbidden from reading any gold set, adversarial set, training batch, prompt example or
demo scenario, so the cards are fresh text, not paraphrases of what the model was tuned or tested on.

A second annotator labeled the same `say` items blind, from the labeling guide alone, without seeing the first labels
(`eval/field_cards_v1_labeler_b.jsonl`). Agreement (`eval/agreement.py`, the benchmark's atoms):
- all 30 cards were identical;
- fact F1 was 1.000 over 207 atoms;
- role agreement was 1.000.

The two files aren't copies: 12 cards differ in fact order or free-text wording, which the scorer compares by presence.
The tool does detect a planted difference.

Treat this as an upper bound on label quality, as with gold v1. Both annotators are the same kind of annotator
reading the same guide, and the `say` items were written to state each fact plainly, which makes them easier to
label than natural speech.

30 cards, 169 facts over 46 keys:
- 24 cards on the medic's mic and 6 on the other mic (wife, daughter, patient, neighbor, husband, son);
- by call type: stroke 11, chest pain/STEMI 5, trauma/falls 6, sepsis 3, other medical 5.

Every card is validated against the vocabulary (keys, types, allowed values, plausibility ranges) and scores
perfectly against itself (`eval/field/cards.py`, `tests/test_field.py`).

Known in advance:
- fc28 (a neighbor on the other mic) is labeled bystander, per LABELING_GUIDE §3, but the app currently records any
  non-role speaker as family (TASKS.md "Requests to backend"). Its role errors are a product finding, not a label
  error.
- The scorer normalizes "fourteen oh five" to "14oh5", so a time the model writes in words with "oh" won't match
  "14:05". The model writes digits in practice.

## The target

- At least **5 speakers** and at least **100 clips**: each speaker says 10 cards twice, once in quiet and once with
  road noise, which is 20 clips per speaker.
- Cards are assigned in rotating blocks (speaker 1: cards 1–10, speaker 2: 11–20, speaker 3: 21–30, speaker 4:
  1–10 again, and so on), so every card is said before any card is said twice.
- The order of the two blocks is counterbalanced: odd-numbered speakers start quiet, even-numbered speakers start
  with noise. Practice (saying a card the second time is easier) then doesn't favor one condition.
- A mix of people helps the result mean something: different accents, speaking speeds, and someone who has never
  heard EMS shorthand.

## Running a session

1. **Start the station** on the Nano, in your own clone:
   ```bash
   cd ~/work/<you>/herald-ems
   ~/miniforge3/envs/zgx/bin/python -m uvicorn eval.field.recorder:app --host 127.0.0.1 --port 8103
   ```
2. **Open it on the laptop with the microphone** as `http://localhost:8103`. Browsers only allow the microphone on
   `localhost` or HTTPS. VS Code forwards the port automatically when you're connected to the Nano through it;
   otherwise run `ssh -L 8103:localhost:8103 hp18@<nano>`. Use the laptop's built-in microphone or a headset,
   the same one for everyone if possible.
3. **Noise source for the noise block:** a phone playing ambulance or road noise (an interior-of-a-moving-vehicle
   recording, not sirens only), about one meter from the microphone, at roughly normal speaking volume. Use the same
   phone, clip and volume for every speaker.
4. **New speaker → read the consent text aloud** (it is on screen, from `protocol.yaml`). Tick the box only if they
   agree. They get a code (s01, s02, …). Never write their name anywhere.
5. **For each card:** the speaker reads the card silently, then presses **Record** (or holds Space) and says all of
   it in one go, in their own words, as they would on the call. They should cover every item. It doesn't need to be
   perfect or in order. Listen back if unsure, then **Keep** or **Record again**. The page refuses clips that are
   silent (a mic problem) or shorter than half a second.
6. **Between blocks** the page stops and asks you to set up the room for the next condition (start or stop the
   noise), then press **Ready**.
7. A speaker can stop at any time. **Withdraw & delete** on the speakers list deletes their audio, their manifest
   lines, and every transcript or result line derived from it.

About 10–15 minutes per speaker.

### Rules

- **Consent first, always.** Only people who agreed. No judges, visitors or strangers unless they explicitly agree to
  this recording. **Never a real patient.**
- **No names** in any file: speaker codes only.
- Audio stays on the Nano, is never uploaded or shared, is never used for training (it would also stop being a test),
  and is deleted after the event: `rm -rf ~/work/*/herald-ems/data/field_audio`.
- The cards are made-up patients. Don't let anyone read a card from a real call.

## Scoring

```bash
~/miniforge3/envs/zgx/bin/python eval/field_bench.py --model ems-d-fp8 --runs 3
```

- Speech-to-text runs once per clip, on the GPU in this process (about 2 GB), and is cached.
- The extractor runs `--runs` times against the model already served by ZRT. It never starts or restarts a model.
- Each run appends one summary line to `eval/results.jsonl`:
  - headline precision, recall and F1 (the gold-v2 definition, so the number sits next to the held-out 0.916);
  - F1 over every key on the cards;
  - role (who-said-it) accuracy;
  - quiet vs noise;
  - 95% intervals over clips, and over speakers as clusters (the honest one when there are only 5–6 people);
  - the paired quiet-minus-noise difference with its interval;
  - latency.
- The per-key precision/recall table, pooled over runs, goes to `eval/dumps/field_v1/<model>_summary.json`.

### "As carded" vs "said": the omission review

As carded, a fact the speaker forgot to say counts as a model miss. That understates the model, so after run 1,
`data/field_audio/_bench/<model>/omissions_review.jsonl` lists each clip's transcript and the card facts the extractor
missed (list facts one item at a time).

A reviewer who hasn't seen the model's output for that clip reads the transcript and moves every fact the speaker
**really never said** from `missed` into `omitted`, keeping the `[key, value, role]` form. Save the file as
`data/field_audio/omissions.jsonl` and rescore:

```bash
~/miniforge3/envs/zgx/bin/python eval/field_bench.py --model ems-d-fp8 --runs 3 --omissions data/field_audio/omissions.jsonl
```

The "said" score is reported **beside** the as-carded score, never instead of it. A fact that was said but
misheard by Whisper is not an omission: it is exactly what this test measures.

### Reporting

Put the numbers in `docs/MODEL_PLAN.md` §5 and on one slide, with the intervals, and state honestly what it is.
For example: "N people, M clips, own words, quiet and road noise: F1 x (95% CI a–b over speakers); quiet x, noise y".
Check the result the way AGENTS.md rule 3 asks:
- the spread over the 3 runs;
- which misses are speech-to-text errors, which are extraction errors, and which were never said;
- whether one speaker or one card drives the result.
