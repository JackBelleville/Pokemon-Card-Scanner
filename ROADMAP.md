# Roadmap — from local scanner to hosted card lookup

Written 2026-08-17. Long-term goal: a publicly hosted version where a user can look up any
card and get its information.

## Chosen architecture: set-first selection

**The user picks a set, then scans.** Recognition is always scoped to that one set, exactly
as `compareCards(hashes, setid)` works today. Adding sets grows the catalogue without growing
the candidate pool for any single scan.

This is the decision that shapes everything below, and it is the right one. The alternative —
matching a scan against every card ever printed — asks far more of the matcher than it can
deliver. Measured on the current database:

```
pool of 122 cards (both sets)
nearest-impostor distance:  min 8 | p5 12 | median 16 | max 26
pairs closer than the cutoff of 18:  98

  8  Fire Energy  <->  Psychic Energy
 10  Ponyta       <->  Mewtwo
 12  Diglett      <->  Dugtrio
```

The median card's nearest neighbour is already **below** the cutoff at 122 cards. Perceptual
hashing of the whole card is too coarse to be the sole discriminator across 20,000. Set-first
selection sidesteps that entirely.

### What set scoping does not fix

All 98 of those collisions are **within Evolutions**, not across sets:

| set | cards | within-set pairs under cutoff | cards with a neighbour <= 12 |
|---|---|---|---|
| Evolutions | 113 | 98 | 16 |
| First Partner Series 1 | 9 | 0 | 0 |

A scan of the correct card lands 8-12 away from it, so any card whose nearest same-set
neighbour is within ~12 can be misidentified. Evolutions has 16 such cards.

This risk is currently unmeasured against real scans. `testImages/` holds two photos of a
single Magmar plus two blank grey rectangles that are geometry fixtures for the contour and
warp code, so the recognition path has real coverage of exactly one card.

First Partner, by contrast, is clean — nearest impostor at 23, no pairs under cutoff. Small
sets of visually distinct cards are easy; large sets with many similar commons and near-identical
energy cards are where the work is.

So the residual accuracy problem is real but **bounded and targeted**: a handful of ambiguous
cards per set, not a global search problem. That is Phase 3, and it is much smaller than it
would be without set scoping.

---

## Phase 0 — Evaluation harness — DONE 2026-08-17

Built as `evaluate.py`, with fixtures listed in `testImages/expected.csv`.

```
python evaluate.py          score every fixture; exit 1 if any misbehaves
python evaluate.py --risk   per-set report of confusable cards
```

10 fixtures currently pass. `test_headless.py` is superseded by this and can be removed.

Tuning was previously done by scanning a card and eyeballing the result. That worked for 9 cards
and will not work across many sets.

Build a labeled test set — scan images paired with **the expected outcome**, which is sometimes
a specific card and sometimes "no match" — and a script reporting **top-1 accuracy** and
**false-match rate** per set. `test_headless.py` is the skeleton; it prints results but has
nothing to check them against.

The gap is not hypothetical. `testImages/` contains four files with no record of what any of
them is for:

| file | what it actually is | expected result |
|---|---|---|
| `tiltleft.jpg` | photo of Magmar, tilted | match #20 |
| `tiltright.jpg` | photo of Magmar, tilted | match #20 |
| `horizontal.jpg` | blank grey rectangle | contour found, no match |
| `vertical.jpg` | blank grey rectangle | contour found, no match |

The last two are geometry fixtures for the contour and warp code. Running `test_headless.py`
prints `NO MATCH (above cutoff)` for both, which looks like a recognition failure and is not
one — a reading error made during the 2026-08-17 session, from output alone. Two of four
fixtures pass by failing, and nothing in the repo says so.

That is the whole value of this phase: today the test output cannot distinguish a bug from
correct behaviour, so it cannot catch a regression either. Note also that recognition has real
coverage of exactly one card, in two nearly identical poses.

*Done when:* changing a threshold produces a number that moves, instead of a guess, and a
broken run is distinguishable from a passing one without reading the images by hand.

Highest-leverage item on this list, small, and independent of every decision below. Start here.

## Phase 1 — Move data out of code

`pokedex.py` is five parallel tuples that must stay index-aligned by hand. Adding six Pokemon
required verifying all five stayed at 163 entries; a silent misalignment would shift every
Pokemon's type and height by one. At full National Dex scale this is a liability.

- Move the Pokedex to a data file loaded the way sets already are. The project has a good
  pattern in `cardSets.py` — it just is not applied here.
- Add schema versioning and migrations, and an index on `(setid, cardnumber)`.
- Remove or rename `createDatabase()`. It reads as "ensure tables exist" but deletes the
  database file outright, and has already destroyed indexed hashes once (see the 2026-08-04
  session notes). `ensureSetIndexed()` is the safe path.

*Done when:* adding a Pokemon or a set touches no `.py` file.

## Phase 2 — Sets at scale

Hand-authoring `cards.csv` does not reach hundreds of sets. Two pieces:

- **Ingestion.** An importer that builds a set folder from a bulk source (`pokemontcg.io`,
  TCGdex), with the hand-authored path kept for gaps. That path is proven — it is how
  `firstpartner1` was built, and none of the free APIs carry MEP even now.
- **Set selection UX.** This is a direct consequence of set-first architecture: with 200 sets,
  the numbered console list in `chooseSet()` stops working. Needs search, filtering by series,
  and probably recency ordering. Worth designing before the web UI, since both clients need it.

Also decide image storage here. Roughly 400KB per card puts a large catalogue in the multi-GB
range, which is where committing images to the repo stops being viable.

**Indexing cost:** hashing currently happens on first use of a set. Across many sets, ship
prebuilt hashes with the data instead of hashing on demand — a first-run cost per set is fine
locally but not acceptable in a hosted request path.

## Phase 3 — Close the within-set ambiguity gap

Targeted work, driven by the Phase 0 harness. Only the ambiguous cards need attention.

- Use the harness to find each set's risky cards automatically (nearest neighbour <= 12),
  the way the table above was produced. This should be a standing report, not a one-off.
- For those cards, add a verification step rather than a better global hash. The strongest
  option is that **the card prints its own identity**: `MEP 039` bottom-left, the name across
  the top. OCR of those two regions distinguishes Fire Energy from Psychic Energy trivially,
  where no whole-card hash can.
- Retire per-set hand-tuned `cutoff` in favour of a confidence score. Tuning one value per set
  by hand does not scale past a few sets, and the current value of 18 is already below the
  median nearest-impostor distance in Evolutions.

## Phase 4 — Separate core from desktop UI

Extract a library: image in, ranked candidates out, no `cv2.imshow` anywhere. Today matching
and display are interleaved — `utils.findCard()` both matches and renders, and
`getFoundCardData()` draws text into an OpenCV window. None of that can be hosted.

The desktop app becomes one client of the library. Pure refactor, no behaviour change,
and a prerequisite for anything web-facing.

## Phase 5 — Service and web UI

- HTTP API over the core library: set list, scan endpoint, card lookup.
- **Text search matters as much as scanning.** "Look up any card" mostly does not need a
  camera, and search is far easier and more reliable than recognition.
- Browser UI with `getUserMedia` for capture.

Note the scan loop changes character: locally every frame is hashed, but over a network the
client sends one still image. Simpler, not harder.

## Phase 6 — Price information

Deliberately last. Once card identity is solid this is a small feature: a `Prices` table keyed
by `(setid, cardnumber)`, a refresh job with a TTL, and a third display section beside card
info and Pokemon info.

**Never fetch prices in the scan path.** `compareCards` runs on every frame of the live feed;
an API call there would mean hundreds of requests while lining up a card. Prices live in the
local database like hashes do, refreshed by an explicit command.

**Source:** PriceCharting is the only one confirmed to carry the First Partner promos —
`api.pokemontcg.io` still has no MEP set, re-verified 2026-08-17. API access is **$49/month**.
Auth is a 40-character token as the `t` parameter, main endpoint `/api/product`, prices returned
as integer pennies.

---

## Open questions and risks

**PriceCharting terms at $49/month may not permit republishing prices publicly.** That tier is
retailer-oriented. If redistribution is not allowed, the hosted pricing feature cannot ship
regardless of budget. Read the terms before subscribing, not after. The cost is also far easier
to justify against a hosted app with users than against a local scanner — another reason this
phase is last.

**Card images are copyrighted** by Nintendo / Creatures / GAME FREAK / TPCi. Local use is one
thing; serving thousands of card images from a public site is a different exposure. Worth
deciding early because it shapes Phase 2's storage design. One mitigation: never serve card art,
returning only metadata alongside the user's own photo.

**Scope of the catalogue.** English-only is roughly 20,000 cards; including Japanese and promos
is considerably more. This changes the size of Phase 2 but, thanks to set-first selection, not
the difficulty of Phase 3.

---

## Suggested starting point

Phase 0 and Phase 1 are both small, useful regardless of later decisions, and block nothing.
Begin with the evaluation harness — once accuracy is measurable, Phase 3 stops being guesswork
and the risky-card report falls out of it for free.
