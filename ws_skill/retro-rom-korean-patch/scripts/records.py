#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
records.py - 스크립트 영역의 '진짜 텍스트 레코드'를 바이트정렬로 정확히 추출.
================================================================================
게임 텍스트 = 구분자(0xffXX 워드, 바이트열 [low,0xff])로 나뉜 16비트 코드 레코드.
레코드는 **바이트정렬**(홀수 오프셋 가능) — 직전 바이트가 항상 0xff(구분자 끝).
따라서 레코드 시작 = rom[p-1]==0xff 이고 이어지는 워드들이 유효 코드(1..0x7f9).

valid_starts(rom): 스크립트 영역(0xA0000~0xC8200) 유효 레코드 시작 오프셋 집합.
extract(rom): [(offset, [codes...]), ...] 텍스트 레코드(가나/「 포함) 전체.
"""
import struct

SCRIPT_S, SCRIPT_E = 0xA0000, 0xC8200


def _texty(c):
    return 0x143 in c or (len(c) >= 3 and sum(1 for x in c if 0x2d <= x <= 0xd2) >= len(c) * 0.4)


def _is_start(rom, p):
    """레코드 시작 여부: 직전이 구분자 끝(0xff), 또는 0x00 패딩을 거슬러 올라가 0xff를 만남.
    (레코드는 [..구분자 0xffXX][0x00 패딩 0개 이상][레코드] 구조)."""
    if rom[p - 1] == 0xff:
        return True
    k = p - 1
    zeros = 0
    while k >= 1 and rom[k] == 0x00:
        k -= 1; zeros += 1
    # 0x00 패딩이 1개 이상 있고, 그 앞 바이트가 0xff(구분자 상위바이트)면 시작
    if zeros >= 1 and rom[k] == 0xff:
        return True
    return False


def extract(rom, s=SCRIPT_S, e=SCRIPT_E, require_texty=True, min_len=3):
    recs = []
    p = s
    while p < e:
        if _is_start(rom, p) and 1 <= (rom[p] | (rom[p + 1] << 8)) <= 0x7f9:
            q = p; codes = []
            while q + 1 < e:
                w = rom[q] | (rom[q + 1] << 8)
                if 1 <= w <= 0x7f9:
                    codes.append(w); q += 2
                else:
                    break
            if len(codes) >= min_len and (not require_texty or _texty(codes)):
                recs.append((p, codes)); p = q; continue
        p += 1
    return recs


def valid_starts(rom, s=SCRIPT_S, e=SCRIPT_E):
    """유효 레코드 시작(직전 구분자 끝 또는 [구분자][0x0000]) + 유효코드."""
    starts = set()
    p = s
    while p < e:
        if _is_start(rom, p) and 1 <= (rom[p] | (rom[p + 1] << 8)) <= 0x7f9:
            starts.add(p)
        p += 1
    return starts


if __name__ == '__main__':
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    import wsfont, os
    rom_path = os.environ.get("KRPATCH_ROM")
    if not rom_path:
        cands = [f for f in os.listdir('.') if f.lower().endswith(('.ws', '.wsc', '.gb', '.gbc', '.gba', '.sfc', '.smc', '.md'))]
        rom_path = cands[0] if cands else None
    if not rom_path:
        raise SystemExit("ROM을 찾을 수 없습니다. 환경변수 KRPATCH_ROM 에 ROM 경로를 지정하세요.")
    rom = bytes(wsfont.load_rom(rom_path))
    recs = extract(rom)
    print(f"텍스트 레코드: {len(recs)}개")
