#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wsfont.py - WonderSwan 2bpp 8x8 tile font toolkit
=================================================

랑그릿사 밀레니엄 WS 한글패치 프로젝트용 폰트 유틸리티.

기능:
  - 2bpp planar(WonderSwan) 8x8 타일 디코드/인코드
  - ROM에서 폰트 타일 추출 -> PNG 시트
  - 8x8 글리프(2D 배열) <-> 타일 바이트 변환
  - ROM 특정 타일 슬롯에 글리프 삽입
  - WonderSwan 내부 헤더 체크섬 재계산

WonderSwan 2bpp 타일 포맷:
  타일 1개 = 16바이트, 한 줄 2바이트(plane0, plane1).
  픽셀 색 index = (plane1_bit<<1) | plane0_bit,  bit7 = 왼쪽 픽셀.
"""
import struct

TILE_BYTES = 16          # 2bpp 8x8
TILE_W = TILE_H = 8


# ---------- 2bpp 타일 디코드/인코드 ----------

def decode_tile(data, off):
    """16바이트 -> 8x8 색인(0..3) 2D 리스트."""
    rows = []
    for y in range(8):
        b0 = data[off + y * 2]
        b1 = data[off + y * 2 + 1]
        row = []
        for x in range(8):
            lo = (b0 >> (7 - x)) & 1
            hi = (b1 >> (7 - x)) & 1
            row.append((hi << 1) | lo)
        rows.append(row)
    return rows


def encode_tile(rows):
    """8x8 색인(0..3) 2D 리스트 -> 16바이트."""
    out = bytearray(16)
    for y in range(8):
        b0 = b1 = 0
        for x in range(8):
            v = rows[y][x] & 3
            if v & 1:
                b0 |= 1 << (7 - x)
            if v & 2:
                b1 |= 1 << (7 - x)
        out[y * 2] = b0
        out[y * 2 + 1] = b1
    return bytes(out)


# ---------- PNG 렌더 ----------

def render_sheet(data, start_tile, ntiles, cols=16, scale=6, labels=True,
                 pal=(40, 120, 200, 255)):
    """폰트 타일을 인덱스 라벨과 함께 PNG(Image) 로 렌더."""
    from PIL import Image, ImageDraw
    cell = 8 * scale + 2
    labelw = 44 if labels else 0
    rows = (ntiles + cols - 1) // cols
    W = labelw + cols * cell
    H = rows * cell + 2
    img = Image.new('RGB', (W, H), (20, 20, 30))
    d = ImageDraw.Draw(img)
    for i in range(ntiles):
        t = start_tile + i
        off = t * TILE_BYTES
        if off + TILE_BYTES > len(data):
            break
        rws = decode_tile(data, off)
        gt = Image.new('L', (8, 8))
        gp = gt.load()
        for y in range(8):
            for x in range(8):
                gp[x, y] = pal[rws[y][x]]
        gt = gt.resize((8 * scale, 8 * scale), Image.NEAREST).convert('RGB')
        r = i // cols
        c = i % cols
        img.paste(gt, (labelw + c * cell + 1, r * cell + 1))
        if labels and c == 0:
            d.text((2, r * cell + cell // 2 - 4), f"{t:04X}", fill=(180, 180, 120))
    return img


def render_glyphs(glyphs, cols=16, scale=8, pal=(30, 110, 190, 255), gap=2):
    """글리프(8x8 2D 배열) 리스트를 PNG(Image) 로 렌더 (미리보기용)."""
    from PIL import Image
    n = len(glyphs)
    rows = (n + cols - 1) // cols
    cell = 8 * scale + gap
    img = Image.new('RGB', (cols * cell, rows * cell), (20, 20, 30))
    for i, g in enumerate(glyphs):
        gt = Image.new('L', (8, 8))
        gp = gt.load()
        for y in range(8):
            for x in range(8):
                gp[x, y] = pal[g[y][x] & 3]
        gt = gt.resize((8 * scale, 8 * scale), Image.NEAREST).convert('RGB')
        img.paste(gt, ((i % cols) * cell, (i // cols) * cell))
    return img


# ---------- ROM I/O ----------

def load_rom(path):
    return bytearray(open(path, 'rb').read())


def save_rom(rom, path):
    open(path, 'wb').write(bytes(rom))


def write_tile(rom, tile_index, rows):
    """ROM의 tile_index 슬롯(= 오프셋 tile_index*16)에 글리프 기록."""
    off = tile_index * TILE_BYTES
    rom[off:off + TILE_BYTES] = encode_tile(rows)


def write_tile_at(rom, byte_off, rows):
    rom[byte_off:byte_off + TILE_BYTES] = encode_tile(rows)


# ---------- 16×16 글자 코드 <-> 폰트 위치 매핑 (인게임 확정) ----------
# 각 글자(16×16) = 8×8 타일 4개(2×2, row-major TL,TR,BL,BR).
# 코드 C의 글리프는 '슬롯' code_to_slot(C) 에 있고, 슬롯 S = 타일 4S..4S+3.
#   C <= 0x3FF : slot = C-1      (저코드)
#   C >= 0x400 : slot = C+3      (고코드, 경계에서 4슬롯 점프)
# 원본 폰트 글리프는 슬롯 0x4B2까지. 슬롯 0x4B3~0x7FC(파일 0x12CC0~0x1FF00,
# 원래 0xFF 빈영역)는 비어 있어 한글 글리프로 채우면 코드 0x4B0~0x7F9로 렌더된다.

def code_to_slot(code):
    return (code - 1) if code < 0x400 else (code + 3)


def code_to_tilebase(code):
    return code_to_slot(code) * 4


def write_glyph16(rom, code, grid16):
    """16×16 색인(0..3) 배열을 코드 C의 폰트 위치(4타일)에 기록."""
    base = code_to_tilebase(code)
    for k, (oy, ox) in enumerate([(0, 0), (0, 8), (8, 0), (8, 8)]):
        quad = [[grid16[oy + y][ox + x] for x in range(8)] for y in range(8)]
        write_tile(rom, base + k, quad)


# 한글 글리프 배정용 자유 코드 풀 (원본 폰트 미사용, 인게임 검증됨)
KR_CODE_START = 0x4B0     # 코드 0x4B0 -> 슬롯 0x4B3 (빈영역 시작)
KR_CODE_END = 0x7F9       # 검증된 상한 (그 이상도 가능성 있음)


# ---------- WonderSwan 헤더 체크섬 ----------

def ws_checksum(rom):
    """
    WonderSwan 체크섬 = 마지막 2바이트를 제외한 전체 바이트의 16비트 합.
    헤더 마지막 2바이트(오프셋 len-2, len-1)에 리틀엔디언으로 저장.
    """
    s = 0
    for i in range(len(rom) - 2):
        s = (s + rom[i]) & 0xFFFF
    return s


def fix_checksum(rom):
    """체크섬을 재계산해 헤더에 기록. (old, new) 반환."""
    old = rom[-2] | (rom[-1] << 8)
    new = ws_checksum(rom)
    rom[-2] = new & 0xFF
    rom[-1] = (new >> 8) & 0xFF
    return old, new


if __name__ == '__main__':
    import sys
    if len(sys.argv) >= 3 and sys.argv[1] == 'sheet':
        rom = load_rom(sys.argv[2])
        start = int(sys.argv[3], 0) if len(sys.argv) > 3 else 0
        n = int(sys.argv[4], 0) if len(sys.argv) > 4 else 256
        out = sys.argv[5] if len(sys.argv) > 5 else 'sheet.png'
        render_sheet(rom, start, n).save(out)
        print('saved', out)
    elif len(sys.argv) >= 3 and sys.argv[1] == 'checksum':
        rom = load_rom(sys.argv[2])
        print('stored :', hex(rom[-2] | (rom[-1] << 8)))
        print('compute:', hex(ws_checksum(rom)))
