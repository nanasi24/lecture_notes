"""講義PDFをページ単位のテキストに変換する前処理。

使い方:
  python extract.py <pdf> --out work/<name> [--raw] [--split] [--chunk-size N]

出力 (--out 配下):
  pages.txt        全ページ。各ページは "--- p.N ---" で始まる(根拠ページ番号用)
  chunks/*.txt     --split 時のみ。章/セクション単位のテキスト
  manifest.json    ページ数・文字数・チャンクのページ範囲
--raw: ノイズ除去をしない(v1 用)。指定しなければヘッダー/フッター/ページ番号等を除去する。
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import fitz  # PyMuPDF

PAGE_NO_PATTERNS = [
    re.compile(r"^\d{1,3}$"),                        # 12
    re.compile(r"^\d{1,3}\s*/\s*\d{1,3}$"),          # 12 / 48
    re.compile(r"^(page|p\.)\s*\d{1,3}$", re.I),     # Page 12, p.12
    re.compile(r"^[-–—]\s*\d{1,3}\s*[-–—]$"),        # - 12 -
]


def normalize(line: str) -> str:
    """ヘッダー/フッター判定用に、数字を # に置き換え空白を詰める。"""
    return re.sub(r"\s+", " ", re.sub(r"\d+", "#", line)).strip().lower()


def read_pages(pdf: Path) -> list:
    with fitz.open(pdf) as doc:
        return [[ln.strip() for ln in p.get_text().splitlines() if ln.strip()] for p in doc]


def clean_pages(pages: list) -> list:
    """毎ページ繰り返す行・ページ番号・連続重複行・重複ページを除去する。"""
    n = len(pages)
    # 1) 過半数のページに現れる短い行 = ヘッダー/フッター(日付、講義名、著者など)
    freq = Counter()
    for lines in pages:
        freq.update({normalize(ln) for ln in lines})
    threshold = max(3, n * 0.5)
    repeated = {k for k, c in freq.items() if c >= threshold and len(k) <= 80}

    cleaned, titles = [], []
    seen_pages = {}
    for i, lines in enumerate(pages, start=1):
        out = []
        for ln in lines:
            if normalize(ln) in repeated:
                continue
            if any(p.match(ln) for p in PAGE_NO_PATTERNS):
                continue
            if out and out[-1] == ln:  # スライドタイトルの二重出力など
                continue
            out.append(ln)
        titles.append(out[0].lower() if out else "")
        # 2) 以前のページと全く同じ内容(繰り返し出る目次スライド等)は参照だけにする
        key = "\n".join(out)
        if key and key in seen_pages:
            out = [f"(p.{seen_pages[key]} と同内容)"]
        elif key:
            seen_pages[key] = i
        cleaned.append(out)
    return cleaned, titles


def split_chunks(n: int, titles: list, chunk_size: int) -> list:
    """チャンクのページ範囲 [(start, end), ...] を返す(1始まり・両端含む)。

    スライド資料では同じタイトルのページ(Outline/目次など)が繰り返し現れ、
    それが章の区切りになっていることが多い。3回以上出るタイトルを区切りとして使い
    (連続する区切りページは1つにまとめる)、見つからなければ chunk_size ページずつに分ける。
    長すぎる章は chunk_size*2 を超えないよう切る。
    titles はヘッダー除去後・重複ページ置換前の各ページ先頭行。
    """
    counts = Counter(t for t in titles if t)
    dividers = {t for t, c in counts.items() if c >= 3}
    is_div = [t in dividers for t in titles]
    starts = [i + 1 for i in range(1, n) if is_div[i] and not is_div[i - 1]]
    bounds = sorted(set([1] + starts))
    if sum(is_div) > n / 2:  # ほぼ全ページが「区切り」なら判定失敗とみなす
        bounds = [1]
    if len(bounds) == 1:
        bounds = list(range(1, n + 1, chunk_size))
    ranges = []
    for j, s in enumerate(bounds):
        e = (bounds[j + 1] - 1) if j + 1 < len(bounds) else n
        while e - s + 1 > chunk_size * 2:
            ranges.append((s, s + chunk_size - 1))
            s += chunk_size
        ranges.append((s, e))
    return ranges


def render(pages: list, start: int = 1, end: int = None) -> str:
    end = end or len(pages)
    parts = []
    for i in range(start, end + 1):
        parts.append(f"--- p.{i} ---")
        parts.extend(pages[i - 1])
    return "\n".join(parts) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--raw", action="store_true", help="ノイズ除去しない")
    ap.add_argument("--split", action="store_true", help="章/セクション単位に分割")
    ap.add_argument("--chunk-size", type=int, default=8)
    a = ap.parse_args()

    raw = read_pages(a.pdf)
    if a.raw:
        pages, titles = raw, [p[0].lower() if p else "" for p in raw]
    else:
        pages, titles = clean_pages(raw)
    a.out.mkdir(parents=True, exist_ok=True)
    text = render(pages)
    (a.out / "pages.txt").write_text(text, encoding="utf-8")

    manifest = {
        "pdf": str(a.pdf),
        "pages": len(pages),
        "chars_raw": sum(len(ln) for p in raw for ln in p),
        "chars_out": sum(len(ln) for p in pages for ln in p),
        "cleaned": not a.raw,
        "chunks": [],
    }
    if a.split:
        cdir = a.out / "chunks"
        cdir.mkdir(exist_ok=True)
        for old in cdir.glob("chunk_*.txt"):
            old.unlink()
        for k, (s, e) in enumerate(split_chunks(len(pages), titles, a.chunk_size), start=1):
            path = cdir / f"chunk_{k:02d}.txt"
            path.write_text(render(pages, s, e), encoding="utf-8")
            manifest["chunks"].append({"file": str(path), "pages": [s, e]})
    (a.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    json.dump({k: v for k, v in manifest.items() if k != "chunks"} | {"n_chunks": len(manifest["chunks"])},
              sys.stdout, ensure_ascii=False)
    print()


if __name__ == "__main__":
    main()
