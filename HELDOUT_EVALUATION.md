# Measuring the matcher honestly (held-out evaluation)

**Why this exists.** The matcher is tuned on queries we wrote ourselves, so its score on them
(93% to 97% top-1) says how well we fitted our own examples, not how well it works for strangers.
This protocol collects queries from people who have never seen the guides, and reports the
result with its uncertainty. It is the number to quote in the viva, and it is the baseline any
future matcher (for example an embedding model) must beat.

For reference, the scenario cards written as formal sentences (not how people chat) score about 56% top-1
and 74% top-3 against the current guides (`--scenario-texts`, below). Real chat messages are shorter and
blunter, so expect the held-out result to land between our own-queries score and that stress test.
Do not guess: measure it.

## What is in the kit (`scripts/heldout/`)

| File                | What it is                                                                                                       |
| ------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `scenarios.json`    | 68 situations: 62 map to one guide each, 6 are off-topic. This is the **answer key**. Do not show it to testers. |
| `tester_sheet.html` | The page testers fill in. One offline file, works on a phone. Holds the situation texts only, never the key.     |
| `make_sheet.py`     | Rebuilds the sheet from `scenarios.json`.                                                                        |
| `build_heldout.py`  | Turns the CSV files testers send back into a query file for the evaluation.                                      |
| `../match_eval.py`  | Scores the matcher, with 95% intervals.                                                                          |

The situations are written without any guide title or whole keyword phrase (a test checks this on
every run), so a tester cannot score by copying words from the card.

## Steps

**1. Freeze.** Before the first tester starts, stop editing guides and keywords. Write down the git commit.
Any keyword you add after seeing results makes that result a development score, not a held-out one.

**2. Choose testers.** 4 to 6 people who have not used the site or read the guides. Different backgrounds
help (a gamer, a student, a relative who is not technical). Give each a number: "tester 2 of 4".
Each tester answers only their share (about 17 situations, around 10 minutes), so together they cover all 68.

**3. Send the sheet.** Send `tester_sheet.html` as a file, or copy it to `frontend/public/tester.html`
so it is served at `/tester.html` and you can send a link (an attached `.html` file can be awkward to open on
an iPhone). Tell them:

> Open this page. For each situation, type what you would write to a chatbot to get help, in your own
> words. Do not copy the situation text. Enter that you are "tester 2 of 4". When you are done, tap
> Download file (or Copy answers) and send it back to me. Nothing is uploaded; do not type your name,
> number or email.

**4. Collect and import.** Put the returned CSV files in one folder, then from `backend/`:

```powershell
python scripts/heldout/build_heldout.py answers_T1.csv answers_T2.csv answers_T3.csv answers_T4.csv -o heldout_queries.json
```

Read what it left out ("copied the scenario text", personal data, empty answers) and which
situations nobody answered. Fix gaps by asking another tester for those numbers.

**5. Measure once.**

```powershell
python scripts/match_eval.py app/data/seed heldout_queries.json
```

Record the result below. Run it once. If you change keywords afterwards, say so and treat any new
number as a development score.

**6. Read the result like this.**

- Quote the **interval**, not just the percentage. With 60 queries the 95% interval is about 12 points
  either side; with 120 it is about 9. "72%, 95% interval 60% to 82%" is an honest claim; "72%" alone is not.
- **Top-3** is the number that matches what the person sees (the chat shows up to 3 guides).
  **Top-1** is the strict one. Report both.
- Look at the **by kind of question** table and at the listed misses. They show where the word-based
  matcher is weak (for example vague "how do I..." questions) and give the case for the next step.
- The off-topic rows show **false matches**: the chat suggested a guide for something it should have ignored.

## Result log

| Date | Commit | Testers | Queries | Top-1 (95% interval) | Top-3 (95% interval) | Off-topic ignored | Notes |
| ---- | ------ | ------- | ------- | -------------------- | -------------------- | ----------------- | ----- |
|      |        |         |         |                      |                      |                   |       |

## What to say about the limits

- The queries were prompted by written situations, so they are close to real use but not identical.
- A few testers means a wide interval; say how many.
- Each query has exactly one expected guide. Some problems fit two guides (for example a heat shutdown
  could be a cooling or a power guide), so strict top-1 slightly understates how useful the suggestions are.
- 14 guides (GPU, storage, motherboard) are not covered until their files are in `app/data/seed/`.
  Add situations for them to `scenarios.json` (the tests check each new card for leaks), then rebuild the sheet.

## Afterwards

The held-out set becomes a **development set** the moment you tune against it. Keep it: it is the baseline for
the embedding matcher in the roadmap. For the final claim about that matcher, collect a fresh set from new testers.

`python scripts/heldout/build_heldout.py --scenario-texts -o stress_queries.json` writes the situation
texts themselves as queries (a harsh, formal-wording stress test). Score it the same way. It is not a held-out result.
