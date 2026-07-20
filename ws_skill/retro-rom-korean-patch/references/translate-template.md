# Translation-engine pattern (translate.py)

You write one `translate.py` per game; it stitches your translation dicts into the ROM.
Below is the proven structure. Data modules are plain files like
`kr_story.py` containing `T = {0xADDR: "한국어", ...}` (offset → Korean); the engine
auto-loads all of them.

## Punctuation reuse table

Map Japanese/ASCII punctuation, digits, and letters to **existing** font codes so they
cost no glyph budget. Verify each code by rendering it — do not guess.

```python
PUNCT = {'「':0x143,'」':0x144,'…':0x2b,'、':0x27,'。':0x28,'！':0x2a,'？':0x29,
         '・':0x2c,'／':0x26,'（':0x30c,'）':0x30d,'＋':0x25,'－':0x493,'：':0x190, ...}
PUNCT.update({str(i): i+1 for i in range(10)})              # digits '0'->0x1 ...
PUNCT.update({chr(ord('A')+i): 0xb+i for i in range(26)})   # letters A->0xb ...
```

## KRFont — syllable allocation with reclaim overflow

```python
class KRFont:
    def __init__(self, rom, reclaim=None):
        self.rom, self.next, self.map = rom, KR_CODE_START, {}
        self.reclaim, self.ri = list(reclaim or []), 0
        self.space = self._alloc_blank()          # a blank glyph used for spaces/pad
    def _next_code(self):
        if self.next <= KR_HARD_END:              # primary free pool
            c = self.next; self.next += 1; return c
        assert self.ri < len(self.reclaim), "pool exhausted"
        c = self.reclaim[self.ri]; self.ri += 1; return c   # reclaimed low code
    def code(self, ch):
        if ch == ' ': return self.space
        if ch in PUNCT: return PUNCT[ch]
        if ch in self.map: return self.map[ch]
        g = glyph16(ch)                           # from hangulttf.py
        if g is None: return self.space           # unmapped -> blank, warn
        c = self._next_code(); wsfont.write_glyph16(self.rom, c, g); self.map[ch]=c
        return c
```

## compute_reclaim — free extra codes safely

```python
def compute_reclaim(rom, translated_offsets):
    keep = set()
    for start, codes in all_text_records(rom):        # every record in ROM
        if start not in translated_offsets:           # still Japanese -> keep its codes
            keep.update(codes)
    keep |= set(PUNCT.values()) | set(INPLACE_KANJI)   # never reclaim these
    return [c for c in range(0x25, KR_CODE_START) if c not in keep]
```

## condense + apply — fit into the cell budget, never truncate meaning

```python
def condense(text, n):
    if len(text) <= n: return text
    t = text
    while len(t) > n and ' ' in t:                 # 1) drop word spaces
        i = t.rfind(' '); t = t[:i] + t[i+1:]
    while len(t) > n and '……' in t:                # 2) shrink ellipses
        t = t.replace('……','…',1)
    return t                                        # last resort: caller truncates+warns

def apply(rom, krf, off, text):
    n = record_len(rom, off)                        # codes until the delimiter
    text = condense(text, n)
    codes = [krf.code(c) for c in list(text)[:n]]
    codes += [krf.space] * (n - len(codes))         # pad short
    struct.pack_into("<%dH" % n, rom, off, *codes)
```

## main — phantom guard + build

```python
def main():
    rom = wsfont.load_rom(SRC)
    merged = {}
    for tbl in ALL_DATA_MODULES: merged.update(tbl)  # later modules override earlier
    reclaim, _ = compute_reclaim(rom, set(merged))
    krf = KRFont(rom, reclaim=reclaim)
    for code, ch in INPLACE_KANJI.items():           # zero-budget in-place kanji
        wsfont.write_glyph16(rom, code, glyph16(ch))
    starts = records.valid_starts(bytes(rom))        # phantom guard set
    for off, text in merged.items():
        if SCRIPT_S <= off < SCRIPT_E and off not in starts:
            continue                                 # skip mis-aligned phantom
        apply(rom, krf, off, text)
    wsfont.fix_checksum(rom); wsfont.save_rom(rom, OUT)
```

## Parallel-agent translation loop (Phase 4 detail)

- Split uncovered records into ~150-record groups. For each, render a PNG with
  `scenedump.py` (offset labels on the left, glyphs on the right) and write a
  `offset  code-count` todo file.
- Spawn one subagent per group. Prompt essentials: *read the PNG and the todo file;
  translate each offset to natural Korean **≤ its code-count** (each of `「。、！？…・`
  counts as 1 cell; avoid spaces to save cells); skip `？？` speaker labels and
  data fragments; output `T = {0xADDR: "한국어", # 日本語}`; verify it parses.*
- Give every agent the **same glossary** of canonical name transliterations. At the
  end, unify residual variants with a global text replace across all modules
  (e.g. 베올프/베오르프→베오울프), then rebuild and re-check for truncations.
