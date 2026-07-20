# Disassembly & engine hacks (advanced / v1.0)

Text swaps cover 95% of a translation. The last mile — **compact status-screen
name/class rendered as graphic tiles**, and **half-width spacing** — usually requires
patching executable code. This is genuinely hard **without a system-aware debugger**;
set expectations and prefer a collaborative loop with the user.

## Map ROM → CPU address space (do this first)

You can only disassemble meaningfully once you know how ROM offsets map to CPU
addresses.

- **WonderSwan / WSC** run a NEC **V30MZ** (16-bit x86-compatible, real mode). The
  reset vector is at CPU `0xFFFF0` (= last 16 bytes of a mapped bank). Disassemble
  those 5 bytes: it's an `ljmp seg:off`. On the proven 1MB title the ROM is **linearly
  mapped — CPU physical address == ROM file offset** — so the boot entry
  `ljmp 0x4000:0x0277` → ROM `0x40277`, and `capstone` in `CS_MODE_16` disassembles
  cleanly from there.

```python
import capstone
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_16)
for ins in md.disasm(rom[0x40277:0x40340], 0x40277):
    print(f"{ins.address:#08x}: {ins.mnemonic} {ins.op_str}")
```

- Confirm linearity by disassembling the entry: real boot code looks like
  `cli / mov ss,.. / mov sp,.. / rep stosw / call ... / <main loop>`. If you get
  `add [bx+si],al` spam, you're in **data** (that region is graphics/tables) or the
  mapping isn't linear — recheck the bank registers (`out` to the mapper ports early
  in boot reveal the scheme).

- For GB/GBC (SM83), GBA/DS (ARM), SNES (65816), MD (68000): use the matching capstone
  arch/mode and that system's memory map. The **method is the same**: find the entry,
  confirm you're looking at code, then trace.

## Finding a routine

- **Recursive trace from the entry**, following *direct* `call`/`jmp` targets, gives a
  reachable-code set. But renderers are frequently invoked through **indirect calls**
  (`call [table]`, far pointers, a command dispatch table) — a pure static trace won't
  reach them. On the proven title the entry reached only ~22 functions; the glyph
  renderer was not among them.
- Byte-pattern searches for a distinctive constant (e.g. `cmp ax,0x400` for the
  code→slot boundary, or `cmp al,0x24/0x26` for a half-width boundary) mostly hit
  **inside data** — always re-disassemble a window around each hit and confirm it sits
  in valid code before trusting it.

## Why you likely need a debugger here

To locate a renderer reached by indirect calls, break at it while it runs and read the
live call site / registers. Options:

- **BizHawk** (WSC core) — has a debugger *and Lua*, so you can script breakpoints and
  dump state. Best for a collaborative loop.
- **Mednafen** — has a built-in debugger (GUI), good but not scriptable by an agent.
- The generic **emucap** control MCP does **not** support WonderSwan (it covers
  SNES/GB/GBA/NES/Saturn/PSX/PCE/MD/etc.) — check `status.supported_systems` before
  assuming.

**Collaborative loop**: ask the user to set a breakpoint on VRAM/tile writes during
the target screen and report the PC / source pointer; you convert that to a ROM offset
(linear map) and craft the patch, they test, repeat.

## Half-width spacing — the specific problem

The game renders low codes (digits/letters, e.g. `0x1..0x26`) at **8px** and everything
else at **16px**. To get a half-width *space* you need either an unused half-width code
whose glyph you blank (often **none are free** — verify by scanning real text usage of
every low code, not just data tables), or a renderer patch that advances 8px for your
space code. The latter needs the width-decision code located as above. If neither is
feasible, the pragmatic fallback is to **minimize spaces in the Korean** so text reads
at Japanese density (not true half-width, but tighter and zero-risk).

## Status name/class as graphics

If a compact status window shows the character name/class in Japanese even though the
name/class **text tables are already translated**, and searching the ROM finds the
class string in **exactly one place** (the table you already translated), then that
screen is almost certainly drawing **pre-rendered graphic tiles**, not text. Localizing
it means finding and redrawing those tiles (a graphics task, per-character/per-class),
or patching the routine to render from the text table instead — again, a debugger makes
this tractable.
