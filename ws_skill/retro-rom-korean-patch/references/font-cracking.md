# Cracking the font: tile format, code→slot mapping, free-glyph budget

The font is the foundation. Get these three things right and the rest follows.

## 1. Tile pixel format

Console 2D graphics are tile-based. Determine, for your system:

- **Tile size** (usually 8×8 pixels) and how a "glyph" is composed of tiles. WSC text
  font: a **16×16 glyph = 4 tiles** in row-major order (top-left, top-right,
  bottom-left, bottom-right).
- **Bit depth & plane layout.** WSC: **2bpp planar**, 16 bytes/tile, 2 bytes per row
  (plane0 byte then plane1 byte), bit 7 = leftmost pixel. `wsfont.decode_tile` /
  `encode_tile` show the exact bit math — adapt for GB (2bpp interleaved), GBA
  (4bpp/8bpp linear), SNES (2/4bpp planar), MD (4bpp linear), etc.
- **Palette meaning inside the font.** WSC text: index 1 = background, 2 = anti-alias
  edge, 3 = ink. Match this when you draw Korean so it blends with original glyphs.

Sanity check: render the first ~64 slots straight from ROM. You should see the game's
character set (kana, kanji, digits, letters). If it's noise, your format is wrong.

## 2. Code → glyph-slot mapping (often nonlinear!)

The text stream uses **codes**; the font stores **slots**. The map is frequently NOT
identity. On the proven title it was **bank-split**:

```
slot = (code - 1)      if code < 0x400
slot = (code + 3)      if code >= 0x400     # 4-slot jump at the 0x400 boundary
file_offset_of_glyph   = slot * bytes_per_glyph   # e.g. slot*64 for 16×16 @ 2bpp
```

You cannot guess this reliably — **crack it empirically with an in-game hex
diagnostic**:

1. Build a diagnostic ROM where **every font slot is overwritten with a glyph that
   draws its own slot index** (e.g. render the hex number of the slot).
2. Run it in an emulator and display a screen full of text (or a known string).
3. Read which **code** shows which **slot index**. Two or three data points reveal the
   formula (e.g. code `0x400` showed slot `0x403` → `+3`).

`wsfont.code_to_slot` / `code_to_tilebase` encode the proven formula; replace with
yours.

## 3. Free-glyph budget (where Korean lives)

Korean needs ~800–1000 unique syllable glyphs. Find room without disturbing originals:

- Render the whole font; find the **last used slot** and the **contiguous blank run**
  after it (all-`0x00` or all-`0xFF` slots).
- The font region is bounded (WSC: file `0..0x20000` = slots `0..0x7FF`). The **max
  renderable code** is whatever maps to the last slot in that region — beyond it the
  game shows black boxes. Verify the usable code range **in-game** (paint a glyph at a
  candidate high code and confirm it renders).
- Proven budget: codes `0x4B0..0x7FC` (~845 glyphs) rendered fine.

### When the syllable pool overflows

A full RPG script can exceed the free pool. Two levers (see `translate-template.md`):

- **Reuse punctuation codes**: map `「」。、！？…・（）＋－：／` and digits/letters to the
  *existing* font codes instead of spending new slots.
- **Reclaim low codes**: after translating, many original kanji/kana glyphs are no
  longer referenced by any *remaining untranslated* text. Compute that set
  (`keep = codes still used by untranslated records ∪ punctuation ∪ in-place kanji`),
  and reuse `[0x25 .. pool_start] \ keep` as extra glyph slots. Conservative but safe.

## In-place kanji trick (zero glyph budget)

If the UI uses kanji that have a natural Korean sino reading (e.g. 移動→이동, 攻撃→공격),
overwrite those specific glyph slots **in place** with the Korean syllable. Costs zero
new codes and localizes every screen that uses them consistently.
