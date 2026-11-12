"""指定バージョンの復習ノート生成を `claude -p` で実行し、トークン数・時間・品質を results.csv に追記する。

  .venv/bin/python bench/run_bench.py --version v1 --pdf lectures/LD9.pdf          # 3回(ばらつき大なら5回)
  .venv/bin/python bench/run_bench.py --version v0 --pdf samples/sample_lecture.pdf --runs 1   # 疎通確認
  .venv/bin/python bench/run_bench.py --baseline                                   # 固定オーバーヘッドの測定

トークンの合計は JSON の modelUsage(モデル別内訳、サブエージェント分を含む)を全モデル分合算する。
main の usage だけの値も main_* 列に参考として残す。
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bench"))
from check_quality import check  # noqa: E402

RESULTS = ROOT / "bench" / "results.csv"
RAW_DIR = ROOT / "work" / "bench_raw"  # 生のJSON(ノート本文を含みうるので git 管理外)
SPREAD_LIMIT = 0.20
COLUMNS = [
    "timestamp", "git_commit", "version", "lecture", "run", "model",
    "total_input", "total_output", "total_cache_creation", "total_cache_read", "total_tokens",
    "sonnet_tokens", "haiku_tokens", "other_tokens",
    "main_input", "main_output", "main_cache_creation", "main_cache_read",
    "duration_s", "turns", "cost_usd", "coverage", "cited_ratio", "n_questions",
    "missing_keywords", "note_path", "status", "note",
]


def find_claude(explicit: str = None) -> str:
    cand = explicit or os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not cand:
        sys.exit("claude コマンドが見つかりません。インストールするか --claude / CLAUDE_BIN で指定してください。")
    return cand


def git_commit() -> str:
    try:
        h = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", ".claude", "bench", "CLAUDE.md"],
                               cwd=ROOT, capture_output=True, text=True).stdout.strip()
        return (h or "none") + ("-dirty" if dirty else "")
    except FileNotFoundError:
        return "none"


def sum_model_usage(model_usage: dict) -> dict:
    tot = {"input": 0, "output": 0, "cache_creation": 0, "cache_read": 0}
    by_family = {"sonnet": 0, "haiku": 0, "other": 0}
    for name, u in (model_usage or {}).items():
        part = {
            "input": u.get("inputTokens", 0),
            "output": u.get("outputTokens", 0),
            "cache_creation": u.get("cacheCreationInputTokens", 0),
            "cache_read": u.get("cacheReadInputTokens", 0),
        }
        for k, v in part.items():
            tot[k] += v
        fam = "sonnet" if "sonnet" in name else "haiku" if "haiku" in name else "other"
        by_family[fam] += sum(part.values())
    tot["total"] = sum(tot.values())
    return {**tot, **by_family}


def run_once(claude: str, prompt: str, model: str, tag: str) -> tuple:
    cmd = [claude, "-p", prompt, "--output-format", "json", "--model", model,
           "--permission-mode", "acceptEdits",
           "--strict-mcp-config"]  # MCPサーバーのツール定義を読み込まない(測定ノイズを減らす)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1800)
    wall = time.time() - t0
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (RAW_DIR / f"{tag}.json").write_text(proc.stdout + ("\n--- stderr ---\n" + proc.stderr if proc.stderr else ""),
                                         encoding="utf-8")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"is_error": True, "result": (proc.stderr or proc.stdout)[-300:]}
    return data, wall


def append_row(row: dict) -> None:
    new = not RESULTS.exists()
    with RESULTS.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in COLUMNS})


def bench_one(claude, version, pdf: Path, run, model, keywords: Path, pages: int, commit, extra_note="") -> dict:
    stem = pdf.stem
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    if version == "baseline":
        prompt, note_path = "「ok」とだけ返答してください。ツールは使わないでください。", None
    else:
        note_path = ROOT / "notes" / f"{stem}_{version}_r{run}.md"
        if note_path.exists():
            note_path.unlink()
        prompt = f"/review-notes {version} {pdf.relative_to(ROOT)} {note_path.relative_to(ROOT)}"
    print(f"[{version} r{run}] {prompt}", flush=True)
    data, wall = run_once(claude, prompt, model, f"{ts}_{stem}_{version}_r{run}")

    mu = sum_model_usage(data.get("modelUsage"))
    u = data.get("usage") or {}
    row = {
        "timestamp": ts, "git_commit": commit, "version": version, "lecture": stem if note_path else "-",
        "run": run, "model": model,
        "total_input": mu["input"], "total_output": mu["output"],
        "total_cache_creation": mu["cache_creation"], "total_cache_read": mu["cache_read"],
        "total_tokens": mu["total"],
        "sonnet_tokens": mu["sonnet"], "haiku_tokens": mu["haiku"], "other_tokens": mu["other"],
        "main_input": u.get("input_tokens", ""), "main_output": u.get("output_tokens", ""),
        "main_cache_creation": u.get("cache_creation_input_tokens", ""),
        "main_cache_read": u.get("cache_read_input_tokens", ""),
        "duration_s": round(data.get("duration_ms", wall * 1000) / 1000, 1),
        "turns": data.get("num_turns", ""),
        "cost_usd": data.get("total_cost_usd", ""),
        "status": "error" if data.get("is_error") else "ok",
        "note": extra_note,
    }
    if data.get("is_error"):
        row["note"] = (extra_note + " " + str(data.get("result", ""))[:200].replace("\n", " ")).strip()
    if note_path:
        row["note_path"] = str(note_path.relative_to(ROOT))
        if note_path.exists():
            q = check(note_path, keywords, pages)
            row.update(coverage=q.get("coverage", ""), cited_ratio=q["cited_ratio"], n_questions=q["n_questions"],
                       missing_keywords=";".join(q.get("missing", [])))
        else:
            row["status"] = "no_note"
    append_row(row)
    print(f"   -> {row['status']} total={row['total_tokens']} cost=${row['cost_usd']} "
          f"{row['duration_s']}s coverage={row.get('coverage', '')} cited={row.get('cited_ratio', '')}", flush=True)
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version")
    ap.add_argument("--pdf", type=Path)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--keywords", type=Path, help="省略時は bench/keywords/<PDF名>.txt")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--no-extend", action="store_true", help="ばらつきが大きくても5回に増やさない")
    ap.add_argument("--claude")
    a = ap.parse_args()

    claude = find_claude(a.claude)
    commit = git_commit()
    if a.baseline:
        bench_one(claude, "baseline", ROOT / "bench" / "run_bench.py", 1, a.model, None, None, commit)
        return
    if not (a.version and a.pdf):
        ap.error("--version と --pdf が必要です")
    pdf = a.pdf.resolve()
    keywords = a.keywords or ROOT / "bench" / "keywords" / f"{pdf.stem}.txt"
    if not keywords.exists():
        print(f"警告: {keywords} がありません。網羅率は記録されません。", file=sys.stderr)
    with fitz.open(pdf) as d:
        pages = len(d)

    rows = [bench_one(claude, a.version, pdf, r, a.model, keywords, pages, commit) for r in range(1, a.runs + 1)]
    ok = [int(r["total_tokens"]) for r in rows if r["status"] == "ok" and r["total_tokens"]]
    if a.runs == 3 and not a.no_extend and len(ok) >= 2:
        spread = (max(ok) - min(ok)) / min(ok)
        print(f"ばらつき (max-min)/min = {spread:.1%}")
        if spread > SPREAD_LIMIT:
            print("20% を超えたので 2 回追加して計 5 回にします")
            for r in (4, 5):
                row = bench_one(claude, a.version, pdf, r, a.model, keywords, pages, commit,
                                extra_note=f"extended_to_5 (spread of r1-3 = {spread:.1%})")
                rows.append(row)
    # 失敗した run は理由を表示
    for r in rows:
        if r["status"] != "ok":
            print(f"   ! r{r['run']}: {r['status']} {r.get('note', '')}")


if __name__ == "__main__":
    main()
