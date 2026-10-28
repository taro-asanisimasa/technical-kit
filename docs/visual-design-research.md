# 図・表・画面の指示を支える調査

少数の値を再利用する方針を採用し、**役割と値の対応、媒体に合う初期値、実際の表示確認**を組み合わせる。
値の候補を限定しても、同じ種類の箱に余白16と24が混在すれば統一されない。役割に名前付きの設定（トークン）を割り当て、その値を再利用する。

今回確認した資料には「8の倍数・2色・文字2段」の組合せが普遍的に優れるという直接実証はない。「古く見えない」ことも保証しない。
以下は一次資料を踏まえたキット側の設計判断であり、この改訂指示による品質改善はA/B比較で未測定である。

使う指示は[共通プロンプト](visual-design-prompt.md)、draw.ioの具体値は[視覚スタイル](../skills/drawio-diagrams/references/visual-style.md)に分ける。[README](../README.md)の2つのSkillを維持し、新しいSkillは増やさない。

## 根拠の種類を混同しない

| 種類 | このキットでの扱い |
|---|---|
| 標準・仕様 | 適用範囲内の要件やデータ形式として扱う。WCAGとDTCGの位置付けは異なる |
| デザインシステムの事例 | 役割・値・余白・文字階層を管理する先例として使う |
| ベンダー推奨 | 対象モデル・用途・版を伴う実務指針として使う |
| 実証研究 | 評価した課題・モデル・指標の範囲で結果を読む |
| キットの初期値 | 使い始めるための選択。既存規約や必要な調整を優先する |

DTCGの2025.10文書はFinal Community Group Reportであり、W3C Standardではない。媒体別に値を選ぶこのキットの構成も、DTCGが指定した分類ではない。

## LLM公式資料は設計の具体化と確認を重視する

全資料の確認日は**2026-10-28**。日付のない更新型文書とGitHubのmainは、この確認時点の内容を指す。以下の文章は独自要約であり、第三者のSkill本文を収録していない。

| 資料・URL | 版・公開／更新日 | 示すこと | 限界 |
|---|---|---|---|
| OpenAI [Frontend prompt instructions](https://developers.openai.com/api/docs/guides/frontend-prompt) | GPT-5.5向け、日付表示なし | 用途と既存設計に合わせ、文字の収まりを確認 | Web向けの細則を全媒体へ移植しない |
| OpenAI [Designing delightful frontends](https://developers.openai.com/blog/designing-delightful-frontends-with-gpt-5-4) | GPT-5.4、2026-03-20 | 色・文字を役割で定義し、実表示と動作を確認 | 表現的なWebの例を技術図へ強制しない |
| OpenAI [Prompt engineering](https://developers.openai.com/api/docs/guides/prompt-engineering) | 更新型 | 原則、部品、状態、配置先、確認手順を具体化 | すべての図にUIの状態定義が必要ではない |
| Anthropic [frontend-design](https://github.com/anthropics/skills/blob/main/skills/frontend-design/SKILL.md) | main | 小さなトークン体系と設計意図を定め、実装を見直す | 例示された配色や装飾は普遍則ではない |
| Anthropic [Improving frontend design through Skills](https://claude.com/resources/articles/improving-frontend-design-through-skills) | 2025-11-12 | 抽象的すぎず固定しすぎない指示を必要時に読む | 紹介事例は統制実験ではない |
| Google [Prompt design strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies) | 2026-10-13更新 | 制約・例・文脈を構造化し、結果を見て改善 | 特定の余白刻みを実証していない |
| Google [Stitchのvibe design](https://blog.google/innovation-and-ai/models-and-research/google-labs/stitch-ai-ui-design/) | 2026-03-18 | DESIGN.mdで設計規則をツール間に持ち運ぶ事例 | 任意のLLMによる自動読込を保証しない |

共通するのは目的に合う設計を具体化すること。装飾の推奨・禁止は用途と版で異なるため、各社の細則を一つの禁止リストに合成しない。

## デザインシステムは役割と値を分離する

| 資料・URL | 版・公開／更新日 | 示すこと | 限界 |
|---|---|---|---|
| DTCG [Format Module](https://www.designtokens.org/tr/2025.10/format/) | 2025.10 | 名前・型・値・参照で設計上の決定を共有 | 良い色や余白の値は規定しない |
| DTCG [Resolver Module](https://www.designtokens.org/tr/2025.10/resolver/) | 2025.10 | 文脈に応じた代替値を解決 | 図・スライド・Webの区分はキット側の判断 |
| Android [Grids and units](https://developer.android.com/design/ui/mobile/guides/layout-and-content/grids-and-units) | 2026-10-22更新 | 基本8dp、細部4dp、文字はspを使う | 8pxを全座標に課す根拠ではない |
| IBM Carbon [Themes](https://www.carbondesignsystem.com/building-blocks/foundations/themes/overview) | 2026-08-12更新 | 役割・トークンを保ち、テーマに応じて値を変える | トークンだけで情報構造は決まらない |
| IBM Carbon [Spacing](https://www.carbondesignsystem.com/building-blocks/foundations/spacing/overview) | 2026-09-30更新 | 段階的な余白で関連・階層を示し、可変配置も許す | 全寸法を固定リストに収める規則ではない |
| GOV.UK [Table](https://design-system.service.gov.uk/components/table/) | 更新日未確認 | 比較に表を使い、見出しを備え、数値を右に揃える | 全表の列順やセルの文数は指定しない |
| W3C [WCAG 2.2](https://www.w3.org/TR/WCAG22/) | Recommendation、2024-12-12 | コントラスト、色以外の手がかり、表示変化への耐性 | 対象と例外があるWebの適合基準 |

WCAGでは通常文字は4.5:1、大きな文字は3:1等、理解に必要な図形やUIの識別情報は3:1が基準となる。すべての装飾線に同じ要件があるわけではない。
印刷物・投影物にも可読性の観点は使えるが、そのままWebへの適合を主張しない。計算したコントラストと、実表示での細線・文字の見え方は別に確認する。

## 研究は制約と描画評価を支持するが、自己修正は万能ではない

| 論文・URL | 年・確認版 | 評価対象と分かること | 限界 |
|---|---|---|---|
| [LayoutPrompter](https://papers.nips.cc/paper_files/paper/2023/hash/88a129e44f25a571ae8b838057c46855-Abstract-Conference.html) | NeurIPS 2023 | 4データセットで制約の構造化・事例選択・候補順位付けを評価 | 固定の色数・余白刻みの実験ではない |
| [LACE](https://proceedings.iclr.cc/paper_files/paper/2024/hash/25d61d11fcbbfb28d1fbcc217141e776-Abstract-Conference.html) | ICLR 2024 | 拡散モデルに整列・重なりの制約を導入 | LLMへの指示文の評価ではない |
| [Design2Code](https://aclanthology.org/2025.naacl-long.199.pdf) | NAACL 2025 | 484の実Webを再現。自己修正の効果はモデル・課題で異なる | 参照への忠実度が中心で、自由な美的設計とは異なる |
| [DesignBench](https://arxiv.org/html/2506.06251v3) | 2025、v3: 2026-03-15 | 900サンプルで生成・編集・修復を分けて評価 | 個々の美的規則の因果効果は示さない |
| [UI-Bench](https://arxiv.org/html/2508.20410v3) | 2025、v3: 2025-09-03 | 10ツール・300サイトの仕上がりを専門家が対比較 | 英語中心。操作性・アクセシビリティ等は対象外 |
| [VFLM](https://arxiv.org/html/2603.22187v1) | CVPR 2026、v1 | SVGの生成・描画・修正を専用学習し、文字と配置を評価 | 一般モデルへ画像を戻すだけの改善は限定的 |

Design2Codeの§4.2–4.5とVFLM補足§4.4は、視覚フィードバックを加えても一律には改善しないことを示す。
ここから「観察した欠陥を具体的に直し、再確認し、問題が解消したら止める」を採用する。これは研究を踏まえた運用判断であり、追加プロンプトだけで研究と同じ効果が出るという意味ではない。

## 元の指示は、共通原則と初期値に分けて取り込む

| 元の規則 | 判断 | 取り込む形 |
|---|---|---|
| 伝えたいことを先に1文で決める | 採用 | 目的・読者・媒体を定め、必要な比較や操作を残す |
| 少数の値だけを使う | 補強 | 同じ役割に同じ設定を割り当てる |
| 全座標・全寸法を8の倍数にする | 緩和 | 余白の既定に使い、可変幅・比率・データ座標は別扱い |
| 線1/2/4、角丸8、文字2段 | 初期値に限定 | 媒体・密度・既存規約に合わせ、文字の役割を必要数設ける |
| 灰色と2色、主役は1つ | 緩和 | 強調を絞り、状態・分類・系列の意味は維持する |
| 枠か面の一方、影・グラデーション禁止 | 初期値に限定 | 簡潔な技術図の既定とし、機能上必要な表現は許す |
| 表の列順・整列・空欄・セル長 | 条件付き採用 | 比較軸に合う列順。数値量とIDを区別し、未確認を明示する |
| 例外値にはコメント | 緩和 | 設計上の例外だけ理由を残し、通常の計算値は違反にしない |
| 値を数える・ぼかして確認 | 補強 | 設定検査と実表示検査を分け、ぼかしは補助に留める |

既存規約、情報の正確さ、可読性を初期値より優先する。値の統一のために、内容やデータの意味を変えない。

## 導入後の品質は代表課題で確かめる

運用時には共通プロンプトと該当する媒体の規則を読み、この調査資料を毎回の必読にはしない。通常の文書作成は`layered-docs`、図の構造・配線・編集データは`drawio-diagrams`が担当する。

採用前後の比較では、同じモデル・素材・出力条件を使う。図、比較表、必要ならUIを代表課題とし、次を別々に記録する。

- 情報の欠落や意味の変化、操作上の不具合がないか。
- 役割の統一、文字の収まり、線の衝突、コントラストが適切か。
- 内容を探しやすく、比較・判断しやすいか。好みの評価は同条件の成果物を並べて行う。

今回の取り込みでは資料の確認と指示の整合を扱い、生成品質の比較実験は実施していない。描画できない環境では目視を未実施と記し、設定値の検査だけで見た目を確認済みとしない。
