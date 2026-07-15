---
name: research-assistant
description: Leverages subagents (generalist, codebase_investigator) to perform deep research, technical analysis, or codebase investigations. Use this when a task requires multiple search/read steps or high-volume data processing that would clutter the main context. / サブエージェント（generalist・codebase_investigator）に委任して、深いリサーチ・技術調査・コードベース調査を行います。「詳しく調べて」「リサーチして」「調査して」「コードベースを調べて」などで起動してください。
---

# リサーチ・アシスタント / Research Assistant

## 言語設定 / Language Policy
ユーザーへの全ての返答は日英バイリンガルで表示してください。日本語を先に表示し、改行の後に英語を続けてください。
Always respond to the user in both Japanese and English. Display Japanese first, then English on the next line.

## 概要 / Overview
このスキルは、複雑な調査を専門のサブエージェントに委任することで、深いリサーチを促進します。これにより、メインの会話履歴をクリーンに保ち、コンテキストトークンを節約できます。
This skill facilitates deep research by delegating complex investigations to specialized subagents. This keeps the main conversation history clean and saves context tokens.

## 手順 / Workflow

### 1. 目的の定義 / Define the Objective
ユーザーと共に具体的な調査目標を明確にします。
Clarify the specific research goal with the user.

- **何を / What**: 技術ドキュメント、市場動向、コードベースのロジックなど / Technical documentation, market trends, codebase logic, etc.
- **成果物 / Outcome**: 要約レポート、事実リスト、または技術提案 / A summary report, a list of facts, or a technical proposal.

### 2. サブエージェントの選択 / Choose the Subagent
タスクに基づいて最適なツールを選択します：
Select the most appropriate tool based on the task:

- **`generalist`**: 広範なウェブ調査、バッチ処理、またはコードベース以外のタスク。 / For broad web research, batch processing, or non-codebase tasks.
- **`codebase_investigator`**: システムアーキテクチャ、依存関係、およびリポジトリ内の根本原因の理解。 / For understanding system architecture, dependencies, and root causes within the repository.

### 3. タスクの委任 / Delegate the Task
選んだサブエージェントに、調査目的・期待する成果物を明記した詳細なプロンプトを渡して委任します（利用可能なサブエージェント呼び出し手段を使用）。
Delegate to the chosen subagent with a detailed prompt stating the research goal and expected output (using whatever subagent-invocation mechanism is available).

### 4. 統合と保存 / Synthesize & Save
サブエージェントの要約を確認し、詳細な調査結果を `tmp/` ディレクトリに保存することを提案します。
Review the subagent's summary and offer to save the detailed findings to the `tmp/` directory.

## 例 / Examples

### シナリオ：深い技術調査 / Scenario: Deep Technical Research
**ユーザー / User**: 「D3.jsをMarpスライドに統合する方法を調べて。」 / "Find out how to integrate D3.js with Marp slides."

**アクション / Action**:
1. 複数のウェブ検索が必要であることを特定。 / Identify that this requires multiple web searches.
2. `generalist` に委任。 / Delegate to `generalist`.
3. 簡潔な要約と `tmp/research_d3_marp.md` 内の詳細レポートへのリンクを提供。 / Provide the user with a concise summary and a link to a detailed report in `tmp/research_d3_marp.md`.

### シナリオ：アーキテクチャの調査 / Scenario: Architecture Investigation
**ユーザー / User**: 「私たちの自動化スクリプトの依存関係フローを説明して。」 / "Explain the dependency flow of our automation scripts."

**アクション / Action**:
1. `codebase_investigator` に委任。 / Delegate to `codebase_investigator`.
2. サブエージェントが提供したアーキテクチャマップを提示。 / Present the architectural map provided by the subagent.
