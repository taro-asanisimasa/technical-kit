# 作図補助ツール

Python 3.10以上の標準ライブラリだけで、配置計算、XML検査、簡易プレビュー、編集データの抽出を行う。
PNGの本来の描画には、別途インストール済みのdraw.io Desktopが必要になる。ダウンロードやインストールは行わない。
以下のコマンドは `drawio-diagrams/` フォルダで実行し、入力は非機密の例から試す。

## 生成して検査する

出力先を作り、同梱の架空の例を生成する。`work/` は作業用で、Skillの配布物へ戻さない。

```sh
mkdir -p work
python3 -B scripts/generate.py assets/example-diagram.json work/example.drawio
python3 -B scripts/check.py work/example.drawio
python3 -B scripts/preview.py work/example.drawio --output work/example.html
```

`example.html` をローカルのブラウザで開くと、全体表示と100%表示を確認できる。
外部のviewer、ネットワーク接続、localhostサーバーは不要。これは簡易SVGであり、draw.io本来の描画器ではない。
ラベルや入れ子、概略の経路を確認する補助として使い、ネイティブPNGの目視確認を置き換えない。
未知のshapeや省略した表現は画面に制約として表示する。

```sh
python3 -B scripts/generate.py assets/example-nested.json work/nested.drawio
python3 -B scripts/generate.py assets/example-nested.json work/boxes.drawio --boxes-only
python3 -B scripts/check.py work/nested.drawio --json
```

既存出力は既定で上書きしない。置換する場合だけ、変更前の正本を保全してから `--force` を指定する。
入力と同じファイルへの出力や、出力のシンボリックリンクは拒否する。
小さな既存図の修正に、JSON化や全体再生成を強制しない。

## JSONは行・列と論理上の関係を表す

同梱の2つのJSONを起点にする。自動グラフ配置ではなく、明示した行・列を共通の寸法から座標に変える補助ツールである。
親内の行・列は0から始まり、同じ親の同じ位置へ複数の箱は置けない。`parent` は `groups` のIDを指定する。

| キー | 内容 |
|---|---|
| `title` | ページ名 |
| `layout` | 行・列の寸法、余白、文字等の共通設定 |
| `groups` | `{id, label, row, col, parent?, width?, height?, evidence?}` の配列 |
| `nodes` | グループと同じ基本項目に、`role?` と `status?` を加えた配列 |
| `edges` | 論理上の関係の配列。下表を参照 |
| `notes` | `{label, x, y, width?}` の配列。`x, y` はページ上の座標 |
| `legend` | 凡例を生成する真偽値。既定は `true` |

IDは英字で始め、英数字・`_`・`-` を使う。`evidence` は根拠を作業入力へ残す任意欄で、表示用XMLへは転記しない。
根拠を必要とする業務では、JSONまたは別の作業メモも保管する。図の公開時に入力資料まで一緒に公開しない。

| 関係のキー | 内容 |
|---|---|
| `id, source, target` | 必須。ID、始点ノードID、終点ノードID |
| `label` | 見える線の説明 |
| `owner` | 線の主体を表す区分。色と凡例で区別する |
| `status` | `[State: …]` の文字として線のラベルへ付ける |
| `kind, condition` | 種類と成立条件。束ねの互換性判定にも使う |
| `source_port, target_port` | `left/right/top/bottom`、または `{side, position}`。位置は辺の0〜1 |
| `waypoints` | `{x, y}` の配列。ページ上の明示的な折れ点 |
| `bundle` | 既定は `false`。意味が同じ共有区間として描ける場合だけ `true` |
| `evidence` | 表示されない根拠メモ |

`kind` と `condition` は線のラベルにも追記する。読み手の判断に必要な条件を、入力だけに隠さない。
グループへの接続、自己ループ、任意の自由配置は生成器の対象外。必要なら最新XMLを編集する。

束ねは起点・主体・接続辺と位置・状態・種類・条件が一致する関係を対象にする。
属性の一致だけでは意味が同じと判断できないため、利用者または作成AIが共有経路として誤解を生まないか確かめる。
各論理関係の線（束ねた場合は枝）に論理上の始点・終点・関係IDをXML属性として残す。幹は表示上の共有線分として扱う。架空の処理順や中継点を追加する目的では使わない。

主な `layout` の初期値は次のとおり。数値は描画座標の単位であり、最終的な掲載サイズの読みやすさは別に確認する。

```json
{
  "margin": 60,
  "cell_width": 200,
  "cell_height": 80,
  "gap_x": 104,
  "gap_y": 60,
  "padding": 32,
  "title_height": 42,
  "route_spacing": 26,
  "font_size": 18,
  "font_family": "sans-serif"
}
```

`gap_x` と `gap_y` は `route_spacing` の2倍以上にする。文字サイズは12以上を受け付けるが、小さくして詰める前に情報量と分割を見直す。
フォントは実行環境で利用できる名前を選ぶ。`sans-serif` は環境ごとに実際の書体が異なる。
配線は有限の経路候補を比較する。最適経路や交差ゼロを保証せず、警告が出たら行・列・接続辺・明示折れ点を調整する。

| ノードの `role` | 塗り／枠 | 意味 |
|---|---|---|
| `external` | `#f5f5f5`／`#666666` | 外部の主体 |
| `process` | `#fff2cc`／`#d6b656` | 処理。既定の役割 |
| `storage` | `#dae8fc`／`#6c8ebf` | 保存 |
| `control` | `#d5e8d4`／`#82b366` | 制限・認証等 |

役割と状態を色で混ぜない。状態は対象自身のラベルへ付くので、GUIで対象を動かしても孤立した札として残らない。
警告・エラーを赤で補う場合も、文字や記号を併用する。配色やレイヤーを変える必要がある場合は、生成器またはXMLを必要な範囲で調整する。

## 検査は構造エラーと警告を区別する

`check.py` は入力を変更せず、XMLの構造、ID、親・接続先、有限な座標、親子関係を検査する。
文字の概算幅、基準フォント、箱の重なり、直交配線、端点方向、線と箱、交差、描画順は警告として示す。
構造エラーは終了コード1、エラーなしは0となる。終了コード0でも警告があれば確認する。

```sh
python3 -B scripts/check.py work/example.drawio --font-size 18 --font-family sans-serif --max-lines 3
python3 -B scripts/preview.py work/example.drawio --output work/page.html --page 1
```

文字幅は概算であり、実フォントの測定ではない。複雑なshape、自由な曲線、外部素材などを含む既存図は、対応する編集環境で確認する。
大量の箱・経路では組合せ検査を省略し、警告で示す。構造検査だけで全経路を検査したとは扱わない。

## 編集可能PNGを出力・更新する

信頼できるインストール済みdraw.io Desktopを使う。実行ファイルをPATHで見つけられない場合は `--drawio` で環境ごとのパスを指定する。
別途Desktopを入れる判断と実行は利用者の権限に従う。

```sh
python3 -B scripts/export.py work/example.drawio --output work/example.drawio.png
python3 -B scripts/check.py work/example.drawio.png
python3 -B scripts/export.py work/example.drawio.png --extract-only --output work/latest.drawio
```

抽出では全ページ・全レイヤーを保持し、画像を再描画しない。
PNG出力では `--embed-diagram` を指定し、出力PNGからXMLを再取得して入力の各ページ・モデル構造と比較する。
外側のファイルメタデータやページIDは比較対象外。厳密な構造比較に通らないDesktopバージョンでは出力を確定せず終了する。
画像ピクセルは比較していないため、最終PNGの表示と編集環境での再編集も確かめる。

```sh
python3 -B scripts/export.py work/example.drawio --output work/selected.drawio.png --page 1 --layers 0,2 --scale 1
```

ページは1始まり、レイヤー番号は0始まり。レイヤー指定は見える画像だけに作用し、埋め込みXMLには全レイヤーが残る。
非表示にしても秘密情報の削除にはならない。画像加工サービス等を経由すると編集データが失われる場合もある。[draw.io公式の形式説明](https://www.drawio.com/docs/manual/export/xml-in-png/)

既存の保存方式を優先し、新規単発図では `.drawio.png` を正本の既定にする。
GUI編集を優先する方式では、必ず最新PNGから抽出して更新し、古いJSONで全体を上書きしない。
継続生成を優先する方式ではJSON・生成コード・設定を正本として管理し、GUIで採用した変更も入力側へ戻す。
`.drawio` とPNGは作業用・生成物として併存できるが、独立した正本を2つにしない。

## 実行範囲と入力の制約

スクリプトにHTTP送信、依存パッケージの取得、認証変更、インストール処理はない。
プレビューではラベルをエスケープし、外部素材を取得せず、Content Security Policyでスクリプトと通信を禁止する。
書き出しだけは利用者が信頼するDesktopを別プロセスで起動する。シェルは介さず、更新確認を無効にする引数・環境変数を渡す。

Desktopにはメディア参照を扱う機能があるため、補助ツールはプレーンなラベルと許可したstyleに入力を限定する。
HTML、画像・リンク、外部フォント、未知のstyleや埋め込みstencil等は自動出力で受け付けない。これらが必要な既存図は、内容と参照先を確認した編集環境で扱う。
この入力制限は、Desktopの通信をOSで遮断する仕組みではない。厳密な隔離が必要な環境では、その環境で許可された描画手段を使う。

読取りはXML、圧縮ページ、編集データ入りPNGに対応する。PNGのCRCと埋め込みXMLは確認するが、画像データの完全なデコードは行わない。
DTD・entityは拒否し、ファイルサイズ、展開量、XML深さ、ページ・セル数、親の深さに上限を設ける。
生成器は4MiBのJSON、合計250箱、300関係、10段の入れ子を上限とする。読取り側は16MiB入力、1ページ8MiB、展開合計24MiB、50ページ、1ページ10,000セルを上限とする。
制限を超える図は分割するか、適切な別の手段で扱う。

## 同梱テストを実行する

キットのルートで次を実行する。実Desktopや追加ライブラリは不要。

```sh
python3 -B -m unittest discover -s skills/drawio-diagrams/tests
```

これは生成・検査・入出力の回帰確認であり、ネイティブ描画、GUI編集、他のSkillとの品質比較を実施するものではない。
