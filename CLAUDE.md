# lecture_notes

講義PDF(lectures/)から試験対策の復習ノート(notes/)を生成するプロジェクト。
トークン最適化を v0〜v3 で段階的に行い、bench/ で測定・比較する。

## ルール
- ノート生成の手順は `.claude/skills/review-notes/` に書く(ここには書かない)
- Python は `.venv/bin/python` を使う。依存は requirements.txt で管理
- 中間ファイルは work/ に置く
- 各段階の変更内容と理由は docs/log.md に記録する
- 不明点は推測で進めず質問する

## Git運用
- lectures/ notes/ work/ はコミットしない(著作権)。動作確認用は samples/ の自作PDFのみ
- まとまった作業ごとにコミット。メッセージは内容がわかる日本語(例: `v1: PDFを事前にテキスト化`)
- 各バージョン完成時に tag(v0-baseline, v1-extract, v2-chunk, v3-subagent)
- push 前は必ずユーザーに確認する
