#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hangulttf.py - 실제 한글 TTF(새굴림)를 16x16 2bpp 글리프로 렌더.
=================================================================
조합형 자모 합성(hangul16.py)의 글리프 버그(ㅆ종성→ㅇ, ㄲ/ㄸ초성→단자음)와
둔탁함을 해결하기 위해, 화면용 한글 폰트 NGULIM(새굴림)을 16px 고정 베이스라인으로
직접 렌더한다. 반환은 hangul16.glyph16과 동일: 16x16 색인(0..3) 2D 리스트, 아니면 None.
팔레트: 배경=1, 가장자리(AA)=2, 잉크=3 (원본 폰트와 동일).
"""
from PIL import Image, ImageFont, ImageDraw
import numpy as np
import os

_FONT_PATH = os.environ.get("KR_TTF", "C:/Windows/Fonts/NGULIM.TTF")
PX = 16          # 폰트 크기
OX, OY = 0, 0    # 셀 내 고정 원점(모든 글자 공통 베이스라인)
TH_EDGE = 60     # 이 이상 -> 가장자리(2)
TH_INK = 140     # 이 이상 -> 잉크(3)
BG, EDGE, INK = 1, 2, 3

_font = ImageFont.truetype(_FONT_PATH, PX)
_cache = {}


def glyph16(ch):
    if ch == ' ':
        return [[BG] * 16 for _ in range(16)]
    code = ord(ch)
    # 한글 음절 블록만 렌더(그 외는 None -> 호출측 공백 대체)
    if not (0xAC00 <= code <= 0xD7A3):
        return None
    if ch in _cache:
        return _cache[ch]
    im = Image.new('L', (16, 16), 0)
    d = ImageDraw.Draw(im)
    d.text((OX, OY), ch, fill=255, font=_font)
    a = np.asarray(im)
    grid = [[BG] * 16 for _ in range(16)]
    for y in range(16):
        row = grid[y]
        arow = a[y]
        for x in range(16):
            v = arow[x]
            if v >= TH_INK:
                row[x] = INK
            elif v >= TH_EDGE:
                row[x] = EDGE
    _cache[ch] = grid
    return grid


if __name__ == '__main__':
    test = "랑그릿사밀레니엄전투를시작했다끊을까발견"
    scale = 10
    disp = {1: 30, 2: 150, 3: 255}
    glyphs = [glyph16(c) for c in test]
    img = Image.new('L', (len(glyphs) * 16 * scale, 16 * scale), 10)
    for i, g in enumerate(glyphs):
        cc = np.vectorize(disp.get)(np.array(g)).astype(np.uint8)
        img.paste(Image.fromarray(cc).resize((16 * scale, 16 * scale), Image.NEAREST), (i * 16 * scale, 0))
    img.save("work/hangulttf_test.png")
    print("saved work/hangulttf_test.png :", test)
