# Text extraction — the byte-alignment trap

This is where most fan-translations lose half their script. Read carefully.

## The record format (proven on WonderSwan, common elsewhere)

- Game text = a stream of **16-bit little-endian "glyph codes"** (`1 .. MAX_GLYPH`,
  where `MAX_GLYPH` is the highest renderable code, e.g. `0x7F9`/`0x7FC`).
- Records (dialogue lines, menu strings, names) are separated by **delimiter words**
  whose value is `>= 0xFF00` (e.g. `0xFFFF`, `0xFFFE`). As bytes (LE) a delimiter is
  `[low, 0xFF]` — its **high byte is 0xFF**. Codes never have high byte `0xFF`
  (they're `<= 0x07xx`), so delimiters are unambiguous.
- Between a delimiter and the next record there may be **`0x0000` padding**.

## Trap #1: byte alignment, not word alignment

Records can start on **odd** byte offsets, because a record of odd byte-length shifts
the alignment of everything after it. A scanner that reads 16-bit words only at even
offsets (the obvious `for i in range(start, end, 2)`) will:

- find the even-aligned records (maybe half of them), and
- read the odd-aligned records as **garbage** (shifted by one byte), skipping them.

On the proven title this hid **~1,925 of ~4,566 dialogue records (42%)**. The symptom
in-game: many lines still Japanese even though "everything was translated", plus a few
**corrupted** lines (an even-scan wrote Korean at a wrong offset = a "phantom").

**Fix:** scan at byte granularity. A record **starts** at byte `p` when:

```python
def is_start(rom, p):
    if rom[p-1] == 0xFF:              # right after a delimiter's high byte
        return True
    k = p - 1                         # or after 0x00 padding that follows a delimiter
    z = 0
    while k >= 1 and rom[k] == 0x00:
        k -= 1; z += 1
    return z >= 1 and rom[k] == 0xFF
```

Then read 16-bit codes forward while `1 <= word <= MAX_GLYPH`, stopping at the next
non-code word. `scripts/records.py` implements exactly this (`extract`, `valid_starts`).

## Trap #2: telling text from data tables

The ROM has big **data tables** (AI/stat tables) made of the same code range — long
runs of single kanji like 活/速/脈. You must not translate these, and you must not
let them flood your "uncovered text" list.

Distinguish by **content**, not code range:

- Real text contains **kana** (a mid code range, e.g. `0x2D..0xD2`) and/or the
  punctuation codes `「」。、！？…・`.
- Pure-kanji equal-length runs are data.

Use a "texty" predicate and **widen it in stages**, re-rendering each stage, because
each looser filter surfaces a new class of real lines:

1. `has 「 OR has 。/、 OR kana_ratio >= 0.4` — catches obvious dialogue.
2. `has any punctuation OR kana_count >= 3` — catches kanji-heavy narration and
   scenario titles (e.g. `15才の少年、シオン。` has only ~36% kana).
3. `has >= 1 kana OR punctuation` — catches lines with just one or two kana
   (e.g. `毎年必ず先生と`).
4. Single-glyph records (a lone `愛` menu option) have **no** kana/punct — handle these
   by inspecting short delimiter-bounded records near known UI strings, individually.

## Trap #3: records preceded by non-standard bytes

Scenario titles and prologue narration were often preceded by **runs of `0x00`** or
even by a preceding line's `、`, so the strict `rom[p-1]==0xFF` rule missed them.
The padding-aware `is_start` above (walking back over `0x00` to find `0xFF`) recovers
the `0x00`-padded ones. A handful embedded mid-stream may still need manual offsets.

## The phantom guard (prevents corruption)

Because earlier even-only passes may have recorded translations at wrong offsets, the
build step must, **in the script region**, only apply offsets that are real
`valid_starts`. Everything outside the script region (UI/name/description tables in
other banks) is applied unconditionally. This drops "phantom" offsets that would
overwrite real records. `translate.py`'s main loop shows the guard.

## Practical scan-and-count recipe

```python
import records
rom = bytes(open("game.ws","rb").read())
covered = set(...)                       # offsets already in your translation dicts
recs = records.extract(rom, SCRIPT_S, SCRIPT_E, require_texty=True, min_len=2)
uncovered = [(o,c) for o,c in recs if o not in covered]
# write offsets+lengths to a todo file, render with scenedump.py, hand to subagents
```

Always finish by re-extracting with the loosest filter and confirming the uncovered
count is ~0 (excluding intentional `？？`/data skips). If a user reports "line X still
Japanese", find X's exact record start (walk back to a delimiter), check why your
filter missed it, loosen, re-render, translate.
