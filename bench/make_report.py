"""bench/results.csv を集計して bench/report.md を作る。

  .venv/bin/python bench/make_report.py

v0 比の削減率を「合計トークン数」と「total_cost_usd(参考のコスト換算)」の両方で出す。
"""
import csv
import statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "bench" / "results.csv"
REPORT = ROOT / "bench" / "report.md"
ORDER = ["baseline", "v0", "v1", "v2", "v3", "v3b"]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def agg(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return {"mean": st.mean(vals), "min": min(vals), "max": max(vals)}


def fmt_int(a):
    return "-" if not a else f"{a['mean']:,.0f} ({a['min']:,.0f}–{a['max']:,.0f})"


def fmt_f(a, nd=2, pre=""):
    return "-" if not a else f"{pre}{a['mean']:.{nd}f} ({pre}{a['min']:.{nd}f}–{pre}{a['max']:.{nd}f})"


def pct(a):
    return "-" if not a else f"{a['mean']:.0%}"


def reduction(cur, base):
    """v0 比の増減率。-35% なら 35% 削減。"""
    if not cur or not base or not base["mean"]:
        return "-"
    return f"{cur['mean'] / base['mean'] - 1:+.0%}"


def main() -> None:
    rows = [r for r in csv.DictReader(RESULTS.open(encoding="utf-8")) if r["status"] == "ok"]
    groups = defaultdict(list)
    for r in rows:
        groups[(r["lecture"], r["version"])].append(r)

    out = ["# ベンチマーク結果", "",
           "値は 平均 (最小–最大)。合計トークン = modelUsage の全モデル合算"
           "(入力 + 出力 + キャッシュ作成 + キャッシュ読込。サブエージェント分を含む)。",
           "コストは `total_cost_usd`(API 価格での参考換算。Pro プランでは請求されない)。", ""]

    base_rows = groups.get(("-", "baseline"))
    if base_rows:
        b = agg([f(r["total_tokens"]) for r in base_rows])
        out += [f"**固定オーバーヘッド(baseline: 何もしない1往復)**: {fmt_int(b)} tokens, "
                f"{fmt_f(agg([f(r['cost_usd']) for r in base_rows]), 4, '$')}", ""]

    for lecture in sorted({k[0] for k in groups if k[0] != "-"}):
        out += [f"## {lecture}", "",
                "| 版 | n | 合計トークン | v0比 | 内 キャッシュ読込 | Sonnet / Haiku | コスト換算 | v0比 | 時間(秒) | 網羅率 | 根拠付き率 |",
                "|---|---|---|---|---|---|---|---|---|---|---|"]
        base = groups.get((lecture, "v0"), [])
        bt = agg([f(r["total_tokens"]) for r in base])
        bc = agg([f(r["cost_usd"]) for r in base])
        for v in ORDER[1:]:
            g = groups.get((lecture, v))
            if not g:
                continue
            t = agg([f(r["total_tokens"]) for r in g])
            c = agg([f(r["cost_usd"]) for r in g])
            cr = agg([f(r["total_cache_read"]) for r in g])
            so = agg([f(r["sonnet_tokens"]) for r in g])
            ha = agg([f(r["haiku_tokens"]) for r in g])
            out.append(" | ".join([
                f"| {v}", str(len(g)), fmt_int(t), reduction(t, bt), fmt_int(cr),
                f"{so['mean']:,.0f} / {ha['mean']:,.0f}" if so and ha else "-",
                fmt_f(c, 3, "$"), reduction(c, bc),
                fmt_f(agg([f(r["duration_s"]) for r in g]), 0),
                pct(agg([f(r["coverage"]) for r in g])), pct(agg([f(r["cited_ratio"]) for r in g])),
            ]) + " |")
        out.append("")

    out += ["## 読み方", "",
            "- **合計トークン**はキャッシュ読込も1トークンとして数えるため、エージェントが何ターンも往復すると"
            "同じ文脈を毎回読み直す分だけ大きく膨らむ。",
            "- **コスト換算**ではキャッシュ読込が通常入力の約1/10、Haiku は Sonnet より安い単価で計算されるので、"
            "トークン数の削減率とコストの削減率は一致しない。両方を見て「量が減ったのか、安い種類のトークンに置き換わったのか」を区別する。",
            ""]
    REPORT.write_text("\n".join(out), encoding="utf-8")
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
