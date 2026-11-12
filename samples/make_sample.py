"""動作確認用の自作サンプル講義PDFを生成する(架空の講義。著作権フリー)。

  .venv/bin/python samples/make_sample.py  ->  samples/sample_lecture.pdf

実際の講義資料に近づけるため、日英混在・毎ページのヘッダー/フッター/ページ番号・
繰り返し出る Outline スライドを含める。
"""
from pathlib import Path

import fitz

HEADER = "Data Structures 2026 / データ構造入門"
FOOTER = "Sample Lecture 3 — Stacks and Queues"
OUTLINE = ["Outline", "1. Stack(スタック)", "2. Queue(キュー)", "3. Applications(応用)"]

SLIDES = [
    ["Lecture 3: Stacks and Queues", "第3回 スタックとキュー", "Instructor: Sample Teacher"],
    OUTLINE,
    ["Stack(スタック)",
     "A stack is a LIFO (Last In, First Out) data structure.",
     "スタックは後入れ先出し(LIFO)のデータ構造である。",
     "Main operations: push (追加) and pop (取り出し).",
     "push と pop はどちらも O(1) で実行できる。"],
    ["Stack implementation",
     "配列を使った実装では、top(先頭位置)を保持する。",
     "When the array is full, push causes overflow(オーバーフロー).",
     "空のスタックに pop すると underflow(アンダーフロー)になる。"],
    OUTLINE,
    ["Queue(キュー)",
     "A queue is a FIFO (First In, First Out) data structure.",
     "キューは先入れ先出し(FIFO)のデータ構造である。",
     "Operations: enqueue (末尾に追加) and dequeue (先頭から取り出し)."],
    ["Circular buffer(リングバッファ)",
     "配列でキューを実装すると、先頭側に空きが生じる。",
     "head と tail を mod N で回すリングバッファ(circular buffer)で解決する。",
     "enqueue / dequeue はどちらも O(1)。"],
    OUTLINE,
    ["Applications(応用)",
     "スタック: 関数呼び出しのコールスタック、括弧の対応チェック、逆ポーランド記法の計算",
     "Queue: BFS (breadth-first search, 幅優先探索), プリンタのジョブ管理",
     "両端から出し入れできるものを deque(両端キュー)と呼ぶ。"],
    ["Summary(まとめ)",
     "Stack = LIFO, Queue = FIFO.",
     "どちらも基本操作は O(1)。",
     "配列実装では overflow / underflow とリングバッファに注意する。"],
]


def main() -> None:
    out = Path(__file__).with_name("sample_lecture.pdf")
    font = fitz.Font("cjk")
    doc = fitz.open()
    n = len(SLIDES)
    for i, lines in enumerate(SLIDES, start=1):
        page = doc.new_page(width=842, height=595)  # A4 横(スライド風)
        page.insert_font(fontname="cjk", fontbuffer=font.buffer)
        page.insert_text((40, 30), HEADER, fontname="cjk", fontsize=10, color=(0.4, 0.4, 0.4))
        page.insert_text((40, 100), lines[0], fontname="cjk", fontsize=28)
        y = 160
        for ln in lines[1:]:
            page.insert_text((60, y), ln, fontname="cjk", fontsize=16)
            y += 40
        page.insert_text((40, 570), FOOTER, fontname="cjk", fontsize=10, color=(0.4, 0.4, 0.4))
        page.insert_text((700, 570), "2026/11/12", fontname="cjk", fontsize=10, color=(0.4, 0.4, 0.4))
        page.insert_text((790, 570), str(i), fontname="cjk", fontsize=10, color=(0.4, 0.4, 0.4))
    doc.set_metadata({"title": "Sample Lecture 3", "author": "sample"})
    doc.subset_fonts()
    doc.save(out, garbage=4, deflate=True)
    print(f"wrote {out} ({n} pages)")


if __name__ == "__main__":
    main()
