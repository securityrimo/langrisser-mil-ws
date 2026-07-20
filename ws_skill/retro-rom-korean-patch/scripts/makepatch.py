#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
makepatch.py - 원본 ROM과 패치 ROM을 비교해 IPS 패치 파일 생성.
IPS 포맷: "PATCH" + [3B offset(BE), 2B size(BE), data]... + "EOF"
 - size=0 이면 RLE 레코드(2B run, 1B value)이지만, 여기선 단순 raw 레코드만 사용.
 - offset 최대 0xFFFFFF(16MB), size 최대 0xFFFF(청크 분할). 1MB ROM이라 문제없음.
사용: python tools/makepatch.py 원본.ws 패치.ws 출력.ips
"""
import sys

def make_ips(orig: bytes, patched: bytes) -> bytes:
    assert len(orig) == len(patched), "크기 동일해야 함(패치는 인플레이스 교체)"
    out = bytearray(b"PATCH")
    n = len(orig)
    i = 0
    while i < n:
        if orig[i] == patched[i]:
            i += 1
            continue
        # 차이 구간 시작
        start = i
        while i < n and orig[i] != patched[i]:
            i += 1
        # [start, i) 를 여러 IPS 레코드로 분할(최대 0xFFFF, offset!=0x454F46 'EOF' 회피)
        j = start
        while j < i:
            chunk = min(0xFFFF, i - j)
            off = j
            # IPS 'EOF' 오프셋(0x454F46) 충돌 회피: 해당 오프셋이면 한 바이트 당겨서 기록
            if off == 0x454F46:
                out += (off - 1).to_bytes(3, "big")
                data = patched[off - 1:off - 1 + chunk + 1]
                out += len(data).to_bytes(2, "big")
                out += data
                j = off - 1 + len(data)
                continue
            out += off.to_bytes(3, "big")
            out += chunk.to_bytes(2, "big")
            out += patched[off:off + chunk]
            j += chunk
    out += b"EOF"
    return bytes(out)

def main():
    orig_p, patch_p, out_p = sys.argv[1], sys.argv[2], sys.argv[3]
    orig = open(orig_p, "rb").read()
    patched = open(patch_p, "rb").read()
    ips = make_ips(orig, patched)
    with open(out_p, "wb") as f:
        f.write(ips)
    diff = sum(1 for a, b in zip(orig, patched) if a != b)
    print(f"IPS 생성: {out_p} ({len(ips)} bytes), 변경 바이트 {diff}개")

if __name__ == "__main__":
    main()
