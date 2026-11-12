"""生成ノートの品質チェック: 重要用語の網羅率と、根拠ページ番号の付与率。

  python bench/check_quality.py <note.md> --keywords bench/keywords/LD9.txt [--pages 48]

keywords ファイル: 1行1語。`|` で表記ゆれを並べる(どれか1つあれば OK)。`#` 以降はコメント。
  例)  フリップフロップ|flip-flop|FF
根拠チェックの対象:
  1. 要点まとめ の箇条書き行 / 2. 重要用語一覧 の表の本文行 / 3. 確認問題と解答 の解答行(**A1.** など)
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

PAGE_REF = re.compile(r"p\.\s*(\d+)(?:\s*[-–~〜]\s*(?:p\.)?\s*(\d+))?", re.I)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s)).lower()


def load_keywords(path: Path) -> list:
    groups = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            groups.append([alt.strip() for alt in line.split("|") if alt.strip()])
    return groups


def coverage(text: str, groups: list) -> dict:
    t = norm(text)
    missing = [g[0] for g in groups if not any(norm(alt) in t for alt in g)]
    n = len(groups)
    return {"keywords": n, "covered": n - len(missing),
            "coverage": round((n - len(missing)) / n, 3) if n else None, "missing": missing}


def sections(text: str) -> dict:
    """'## 1. 要点まとめ' のような見出しで本文を分ける。キーは見出しの番号。"""
    out, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s*(\d)\.", line)
        if m:
            cur = m.group(1)
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return out


def citation_items(text: str) -> list:
    sec = sections(text)
    items = [ln for ln in sec.get("1", []) if re.match(r"^\s*[-*]\s+\S", ln)]
    items += [ln for ln in sec.get("2", [])
              if ln.strip().startswith("|") and not re.match(r"^\|[\s|:-]+\|?$", ln.strip())][1:]  # 先頭は表ヘッダー
    items += [ln for ln in sec.get("3", []) if re.match(r"^\s*(\*\*)?A\d+[.．:]", ln)]
    return items


def citations(text: str, pages: int = None) -> dict:
    items = citation_items(text)
    cited = [ln for ln in items if PAGE_REF.search(ln)]
    bad = []
    if pages:
        for ln in cited:
            for m in PAGE_REF.finditer(ln):
                for g in m.groups():
                    if g and not 1 <= int(g) <= pages:
                        bad.append(int(g))
    sec = sections(text)
    return {"items": len(items), "cited": len(cited),
            "cited_ratio": round(len(cited) / len(items), 3) if items else 0.0,
            "invalid_pages": sorted(set(bad)),
            "sections_found": sorted(sec.keys()),
            "n_questions": len([ln for ln in sec.get("3", []) if re.match(r"^\s*(\*\*)?Q\d+", ln)])}


def check(note: Path, keywords: Path = None, pages: int = None) -> dict:
    text = note.read_text(encoding="utf-8")
    result = {"note": str(note)}
    if keywords and keywords.exists():
        result.update(coverage(text, load_keywords(keywords)))
    result.update(citations(text, pages))
    return result


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("note", type=Path)
    ap.add_argument("--keywords", type=Path)
    ap.add_argument("--pages", type=int, help="PDFのページ数(範囲外のページ番号を検出)")
    a = ap.parse_args()
    print(json.dumps(check(a.note, a.keywords, a.pages), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
