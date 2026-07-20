---
name: retro-rom-korean-patch
description: >-
  End-to-end methodology for translating a retro console game ROM (WonderSwan/WSC
  proven; adaptable to GB/GBC/GBA/SNES/MD and similar 2D tile-based systems) from
  Japanese into Korean (or any language needing a new glyph set). Use this whenever
  the user wants to make a fan translation / localization patch, "한글패치"/"한글화"
  of a game ROM, reverse-engineer a game's font or text encoding, extract or
  re-inject in-game script/dialogue, render a Hangul (or other) font into tile
  graphics, build an IPS/xdelta patch, fix a ROM checksum, or disassemble game code
  to alter the text renderer. Trigger even when the user only says "translate this
  game", "make a Korean patch", "롬 한글패치", or names a .ws/.gb/.gba/.sfc/.md file
  and a translation goal — this skill supplies the whole pipeline and reusable tools.
---

# Retro ROM Korean (fan-translation) patching

This skill captures a battle-tested pipeline for translating a tile-based console
game from Japanese to Korean. It was built and proven on the WonderSwan Color game
*Langrisser Millennium WS* (5,900+ strings, full story), and generalizes to other
2D systems. It bundles ready-to-use scripts and the hard-won reverse-engineering
tricks that are easy to get wrong.

The overarching idea: **treat the ROM as (1) a font of tile graphics + (2) a stream
of text records that index that font.** You crack how codes map to glyphs, carve out
free glyph slots, draw a Korean font into them, then swap every Japanese text record
for a Korean one that fits — all without changing the ROM size.

## Golden rules (why the naive approach fails)

- **Verify by rendering, not by assuming.** After every change, render the affected
  glyph codes straight out of the patched ROM and *look at them*. Most bugs (wrong
  code→tile mapping, misaligned records, truncated strings) are invisible except
  in a render. `scripts/scenedump.py` and the render snippet below are your microscope.
- **The text is usually uncompressed but byte-aligned, not word-aligned.** Records
  are separated by delimiter words (high byte `0xFF`) and can start on **odd** byte
  offsets. An even-only scanner silently misses ~40% of the script. This is the
  single biggest trap — see `references/text-extraction.md`.
- **Never trust one scan pass.** Text hides behind: odd alignment, `0x0000` padding
  before a record, kanji-heavy lines that fail a "looks like text" heuristic, and
  single-glyph records (e.g. a lone 愛). Widen filters iteratively and re-render.
- **Keep the ROM the same size.** Fit each translation into the original record's
  cell count; pad short, compress (drop spaces, shrink `……`→`…`) rather than truncate.
- **Fix the checksum last.** `wsfont.fix_checksum` (adapt the algorithm per system).

## Phase 0 — Recon

1. Identify the system and load the ROM. Note size, header, checksum location.
2. `git init` a workspace; keep the original ROM untouched and always diff against it.
3. Confirm Python deps: `numpy`, `Pillow` (rendering), `capstone` (disasm),
   `pyxdelta` (xdelta). Install if missing.

## Phase 1 — Crack the font (glyph tiles)

The font is tile graphics: each glyph = N sub-tiles of 8×8 pixels at some bit depth
(WSC: 16×16 glyph = 4 tiles, 2bpp, 16 bytes/tile). You must learn:

- Tile pixel format (bit depth, plane layout, pixel order).
- **The code → glyph-slot mapping.** Often NOT `slot = code`. On the proven title it
  was bank-split: `slot = code-1 if code < 0x400 else code+3`. Crack it with an
  **in-game hex diagnostic**: overwrite each font slot with a glyph that draws its own
  slot index, run in an emulator, read which code shows which index.
- **Where free glyph slots live.** Blank/unused regions of the font let you add a new
  script (Korean) without disturbing the original glyphs. Find the last used slot and
  the contiguous blank run after it; verify in-game which codes render there.

`scripts/wsfont.py` — tile decode/encode, `code_to_slot`/`code_to_tilebase`,
`write_glyph16`, `load_rom`/`save_rom`, `fix_checksum`, and the free-code range
constants. Read its docstrings; adapt the mapping + tile format to your system.
Deep dive: `references/font-cracking.md`.

## Phase 2 — Draw the Korean font

**Do not hand-compose jamo.** A hand-built 조합형 (initial/medial/final assembly)
renderer looks blocky and has endless glyph bugs (double-consonant finals, etc.).
Instead render a real Korean **screen/pixel TTF** (Windows `NGULIM.TTF` 새굴림 at 16px
was best; 돋움/Dotum families also good) into the tile grid at a **fixed baseline**,
thresholding grayscale to the palette levels (bg / anti-alias edge / ink).

`scripts/hangulttf.py` — drop-in `glyph16(ch)` that returns a 16×16 index grid from a
TTF. Point `translate.py` at it. Tune `PX`, `OX/OY`, and the two thresholds, then
render a test string and eyeball ㄹ/받침/쌍자음 clarity.

## Phase 3 — Extract the text (the hard part)

Read `references/text-extraction.md` **before** writing any scanner. Summary:

- Records are runs of 16-bit codes (`1..MAX_GLYPH`) separated by delimiter words
  (`>= 0xFF00`). A record **starts** right after a delimiter — byte `p` where
  `rom[p-1] == 0xFF`, **or** after `0x00` padding that itself follows a delimiter.
- Scan at **byte granularity** (both parities), not word granularity.
- Classify text vs data by content, not code range: real text has kana / `「」。、！？`;
  pure-kanji equal-length runs are data tables. Widen the "texty" filter in stages
  (punctuation-or-≥3-kana → ≥1-kana → include short records) and re-render each stage.

`scripts/records.py` — `extract()` and `valid_starts()` implement the correct
byte-aligned, padding-aware record finder. `scripts/scenedump.py` renders a ROM range
as an offset-labeled glyph image so you (or a subagent) can *read* the source.

## Phase 4 — Translate at scale (parallel subagents)

Translating thousands of records solo is slow. Instead:

1. Split uncovered records into ~150-record groups; render each group to a PNG.
2. Dispatch one general-purpose subagent per group. Give it: the group's render PNG,
   a `offset  code-count` list, a **glossary** of canonical character-name
   transliterations, and the rule *"output ≤ N cells per record, keep `「。、！？…・`
   as 1 cell each, skip `？？`/data fragments."*
3. Each agent writes a data module `{offset: "한국어", ...}`; the main `translate.py`
   auto-loads them. Verify each module parses (`ast.parse`) and re-render spot checks.

This "render → agent reads image → agent emits offset:text dict" loop is the workhorse.
Keep a single glossary and unify name variants at the end with a global replace.

## Phase 5 — Build engine: allocate codes, write, checksum

`translate.py` (project-specific; the proven pattern is in
`references/translate-template.md`) does:

- **Punctuation reuse**: map `「」。、！？…` etc. to existing font codes (saves glyph budget).
- **Syllable allocation**: assign each unique Korean syllable a free code (Phase 1
  pool) and write its glyph once (`KRFont`). When the pool overflows, **reclaim**
  low codes whose original glyph is no longer referenced by any *untranslated* text.
- **`apply(off, text)`**: read the original record length, `condense()` the Korean to
  fit (drop spaces, then shrink ellipses), pad with the blank glyph, write codes.
- **Phantom guard**: in the script region, only write offsets that are `valid_starts`
  — drops mis-aligned "phantom" offsets that would corrupt real records.

## Phase 6 — Patch files + verify

- **IPS**: `scripts/makepatch.py` builds an IPS from original vs patched (self-contained).
  **xdelta**: `pyxdelta.run(src, dst, patch)` — but xdelta3 chokes on non-ASCII paths,
  so copy to ASCII temp names first, then rename the output.
- **Round-trip check both**: apply the patch to a fresh original and assert it equals
  the patched ROM. Validate the checksum. Confirm size unchanged.
- Ship a README with **CRC32/MD5/SHA-1 of both original and patched ROM** so users can
  verify their base dump and their patched result. Compute with `zlib.crc32` + `hashlib`.

## Phase 7 (advanced/v1.0) — Engine hacks via disassembly

Some things aren't text: **compact status-screen name/class may be pre-rendered
graphic tiles**, and **half-width spacing** needs the text renderer's width logic.
These require patching executable code. Read `references/disassembly.md`:

- Map ROM→CPU. On WSC the reset vector at ROM `0xFFFF0` is a far jump; the 1MB ROM is
  **linearly mapped** (CPU address == ROM offset), so `capstone` (16-bit x86 / V30MZ)
  disassembles it directly from the entry point.
- The text renderer is typically reached by **indirect calls** (jump tables / far
  pointers), so static tracing often can't locate it — this is where a WonderSwan-aware
  **debugger** (BizHawk WSC + Lua, or Mednafen's debugger) becomes necessary. Offer the
  user a collaborative loop: they run the debugger and report the address/RAM, you craft
  the patch.

## Quick render snippet (your microscope)

```python
import sys; sys.path.insert(0,'scripts'); import wsfont, struct
import numpy as np; from PIL import Image
rom = bytes(wsfont.load_rom("game.ws"))
def glyph(c):
    b = wsfont.code_to_tilebase(c); img = np.full((16,16),25,np.uint8); pal=[0,85,170,255]
    for k,(dy,dx) in enumerate([(0,0),(0,8),(8,0),(8,8)]):
        g = wsfont.decode_tile(rom,(b+k)*16)
        for y in range(8):
            for x in range(8): img[dy+y,dx+x]=pal[g[y][x]]
    return img
# render the record at an offset, then Read the PNG
```

## Bundled resources

- `scripts/wsfont.py` — tile codec, code↔slot mapping, glyph write, ROM I/O, checksum.
- `scripts/records.py` — byte-aligned, padding-aware text-record extractor.
- `scripts/hangulttf.py` — TTF→tile Korean glyph renderer (fixed baseline).
- `scripts/scenedump.py` — render a ROM range as an offset-labeled glyph image.
  (Set the ROM via env `KRPATCH_ROM`, or it picks the first ROM file in the folder.)
- `scripts/makepatch.py` — build an IPS patch from original vs patched.
- `references/font-cracking.md` — cracking tile format, code→slot, free-slot budget.
- `references/text-extraction.md` — the byte-alignment trap and the correct scanner.
- `references/translate-template.md` — the full translation-engine pattern (KRFont,
  reclaim, condense, phantom guard).
- `references/disassembly.md` — ROM→CPU mapping, capstone setup, renderer hunting.
