---
name: translator
description: Detects language and translates text between any languages. Triggered by phrases like "翻訳して", "translate", "これは何語？", "英訳して", "日本語にして", "what language is this?". / テキストの言語を検出し、任意の言語間で翻訳します。「翻訳して」「translate」「これは何語？」「英訳して」などで起動します。
---

# 翻訳スキル / Translator Skill

## 言語設定 / Language Policy
ダイアログ（案内・質問・完了メッセージ）は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Display all dialogue (prompts, questions, completion messages) in both Japanese and English. Japanese first, then English on the next line.

翻訳結果は後述の出力フォーマットに従ってください。
Translation results must follow the output format described below.

## 出力フォーマット / Output Format

翻訳結果は必ず以下の形式で表示する。言語コードは ISO 639-1 の2文字コードを大文字で使用する。
Always display translation results in the following format. Use ISO 639-1 two-letter language codes in uppercase.

```
[言語コード] : [テキスト]
[言語コード] : [テキスト]
```

**例 / Examples:**
```
ES : Hola
JA : こんにちは
EN : Hi
```

複数の翻訳先がある場合は続けて表示する。
If translating to multiple target languages, list them one after another.

## ワークフロー / Workflow

### Step 1 — リクエストの種類を判定 / Identify request type

ユーザーの入力から以下のいずれかを判定する。
Determine which of the following the user is requesting.

| パターン / Pattern | 例 / Example | 動作 / Action |
|---|---|---|
| 言語検出のみ | 「これは何語？」/ "What language is this?" | 言語を検出して言語名を答える |
| 言語検出＋翻訳 | 「Hola、日本語でどういう意味？」 | 言語検出→指定言語へ翻訳 |
| 翻訳先指定 | 「以下を英訳して / [テキスト]」「〜をフランス語に」 | 翻訳先を特定して翻訳 |
| 翻訳先不明 | テキストだけ貼り付けて「翻訳して」 | Step 2 へ進んで翻訳先を確認 |

### Step 2 — 翻訳先が不明な場合のみ確認 / Ask target language only if unclear

翻訳先が明示されていない場合のみ聞く。それ以外はすぐに翻訳する。`ask_user` ツールを使って入力を求めること。
Ask only when the target language is not specified. Otherwise translate immediately. Use the `ask_user` tool to request input.

```json
{
  "questions": [
    {
      "header": "Target Language",
      "question": "翻訳先の言語を教えてください。（例：日本語、英語、スペイン語、フランス語 など）\nPlease specify the target language. (e.g. Japanese, English, Spanish, French)",
      "type": "text",
      "placeholder": "e.g., Japanese, English, Spanish"
    }
  ]
}
```

### Step 3 — 翻訳して出力 / Translate and display

出力フォーマットに従って表示する。元の言語コードと翻訳先の言語コードを必ず明記する。
Display using the output format. Always include both the source and target language codes.

言語コード早見表 / Quick reference for language codes:

| 言語 / Language | コード / Code |
|---|---|
| 日本語 / Japanese | JA |
| 英語 / English | EN |
| スペイン語 / Spanish | ES |
| フランス語 / French | FR |
| ドイツ語 / German | DE |
| 中国語（簡体）/ Chinese (Simplified) | ZH |
| 韓国語 / Korean | KO |
| ポルトガル語 / Portuguese | PT |
| イタリア語 / Italian | IT |
| アラビア語 / Arabic | AR |
| ロシア語 / Russian | RU |
| その他 / Other | ISO 639-1 コードを使用 / Use ISO 639-1 code |

## 使用例 / Examples

- 「Hola、これは何語？日本語でどういう意味？」→ 検出＋翻訳: `ES : Hola` / `JA : こんにちは`
  "Hola, what language is this? What does it mean in Japanese?" → Detect + translate.
- 「"Good morning" を日本語・スペイン語・フランス語に翻訳して」→ 複数言語へ同時翻訳
  "Translate 'Good morning' to Japanese, Spanish, and French" → Translate to all at once.
- 「翻訳して：Grazie mille」（翻訳先不明）→ Step 2 で `ask_user` を使って翻訳先を確認してから翻訳
  "Translate: Grazie mille" (target unspecified) → Ask for the target language via Step 2, then translate.
