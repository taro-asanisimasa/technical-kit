# 配置と視覚的な層の根拠・適用例

位置・余白・まとまり・層を使い、細かい説明を読む前に全体構造と注目点をつかめる図を目指す。
所属や全体と部分の階層を示すことと、構造の上に経路・処理・差分を重ねることは、両方検討する。
図形の重なりや層数を増やすこと自体は目的にしない。

## 研究が示すことと、このキットの制作方針を区別する

以下は原著論文または著者本人の説明を要約したもの。図の設計への応用は、このキットの判断として分けて記す。
原則2層程度を基本案にするのは制作上の方針であり、2層が常に最適と実証されたという意味ではない。
知覚上のまとまりを見つけやすいことだけで、システムの意味や条件まで無意識に正しく理解できるとは扱わない。

| 根拠 | 示される知見と限界 | このキットでの応用 |
|---|---|---|
| [Larkin & Simon, 1987, Why a Diagram is (Sometimes) Worth Ten Thousand Words](https://iiif.library.cmu.edu/file/Simon_box00068_fld05250_bdl0001_doc0001/Simon_box00068_fld05250_bdl0001_doc0001.pdf) | 同じ推論に使う情報を場所でまとめると、探索や記号の対応付けを減らせる、と分析する。任意の図が文章より優れるという主張ではない | 一緒に判断する要素や、その説明を近づける |
| [Palmer, 1992, Common Region: A New Principle of Perceptual Grouping](https://doi.org/10.1016/0010-0285(92)90014-S) | 同じ領域内の図形はまとまりとして知覚されやすく、整合した入れ子は階層的なまとまりも作る。主に図形の知覚的実演で、業務構成図の読解成績の保証ではない | 囲みや背景領域に所属の意味を持たせ、近接等の手掛かりと矛盾させない |
| [Tversky, 2011, Visualizing Thought](https://www.tc.columbia.edu/faculty/bt2158/faculty-profile/files/2011_Tversky_VisualizingThoughts.pdf) | 位置、近接、線、矢印、囲みは概念上の関係も伝える。文脈によって意味が変わり、図形が意図と違う解釈を誘う場合もある | 配置と記号を意味の表現として設計し、誤った所属・順序・経由点が読まれないか確認する |
| [Tufte, Sparkline theory and practice](https://www.edwardtufte.com/notebook/sparkline-theory-and-practice-edward-tufte/) | 2005年8月19日の著者コメントは、背景の重要度帯とデータ線を読み分け、背景の強調が通常の読解を妨げないよう説明する。設計実践上の知見 | 背景の構造と今回の焦点に異なる視覚的な強さを与え、両方を読める状態で重ねる |
| [Chandler & Sweller, 1992, The Split-Attention Effect as a Factor in the Design of Instruction](https://bpspsychub.onlinelibrary.wiley.com/doi/abs/10.1111/j.2044-8279.1992.tb01017.x) | 対応する図と説明等を統合した教材が、分離した教材よりよい学習結果を示した実験。構成図への適用は設計上の応用 | 照合が必要な説明を対象の近くへ置き、離れた凡例や説明欄との往復を減らす |

Palmerの[原著全文](https://e-edu.nbu.bg/mod/resource/view.php?id=598321&lang=bg)は、共通領域が常に他の手掛かりを上回るわけではなく、競合する手掛かりの強さ等にもよると記す。
近くに置く、囲む、色をそろえる等の手法だけで理解を保証せず、読み手が行う判断に合うかを確かめる。

## 同じ図で、所属の階層と今回の説明を読めるようにする

構成図なら、システム、実行環境、部品という確認できた包含を示し、その上へ注目する通信経路と操作を重ねられる。
同じ実行環境のAPIと処理プログラムを囲み、保存先を別のまとまりとして余白で分ける等、囲みと暗黙のグルーピングを使い分ける。
「保存先」という分類だけを理由に、同一ネットワークや同じ責任範囲に所属しているような囲みを作らない。

比較図では共通の配置を保ち、変更される部品と経路を焦点にする。機能の階層を表す図では、全体と部分を包含で示し、今回説明する役割や依存を重ねる。
どの種類の図でも、既存の表記規則と事実を優先し、意味のない背景や二重枠を加えない。

細かな処理や条件は対象のそばへ置く。判断を変える条件は、見た目の主従を理由に見えなくしたり、一時的な作業注釈だけへ移したりしない。
図だけで区別できない意味には短いラベルを添える。文字や図形を小さくして詰め込む前に、配置、強調、図の分割を見直す。

## 誤読と過密を確認する

- 近さ、整列、同じ形や色が、意図しない仲間関係や順序を示していないか。
- 囲みの名前、包含、実際の所属が一致し、異なる分類軸を無理に親子関係へ変えていないか。
- 経路を束ねた結果、存在しない共有経路や中継処理が生まれていないか。
- 構造と今回の説明の両方が読め、重要な条件を見失わないか。
- 縮小時にまとまりと焦点が分かり、掲載サイズで部品名・注記・線を追えるか。

draw.io内部のレイヤーは編集を助けるために任意で使う。レイヤー数と、読者が読み分ける視覚的な層の数は一致させなくてよい。
既存図の限定修正では、依頼範囲を保ち、この方針に合わせるだけの再構成を追加しない。

## 視線の順と強調の数を決める根拠

`SKILL.md` の「描く前に、主張と視線の順を決める」の根拠を示す。種別は、研究が実験やメタ分析、実務が実務家の経験則を表す。
焦点を1つ、色相を灰のほかに2つまで、強さを3段とする既定値は、以下の研究から導いたこのキットの制作方針であり、数値そのものが実証されたわけではない。

| 根拠 | 示される知見と限界 | このキットでの応用 | 種別 |
|---|---|---|---|
| [Treisman & Gelade, 1980, 特徴統合理論](https://en.wikipedia.org/wiki/Feature_integration_theory)（原著は未読、要約で確認） | 1つの特徴だけで周囲と異なる要素は、周囲の数が増えても見つけるまでの時間が伸びにくい。2つの特徴の組合せで初めて区別できる要素は、1つずつ探す必要がある。単純な刺激での実験 | 焦点は図全体で色相が唯一になるようにし、特徴の組合せで区別させない | 研究 |
| [Wolfe, 2021, Guided Search 6.0](https://search.bwh.harvard.edu/new/pubs/Wolfe2021_GS6.pdf) | 注意は、目標、目立ち、履歴、報酬、場面の意味を合わせた優先度の高い場所へ向く。目標と周囲の差が大きく、周囲どうしが似ているほど誘導が強い。目立ちの効果は一過性 | 強調を1つに絞り、ほかは揃えて控えめにする。読者の目的に強調を合わせる | 研究 |
| [Haroz & Whitney, 2012](https://whitneylab.berkeley.edu/PDFs/Haroz_Whitney_2012_InfoVis.pdf) | 色の種類が増えると、異なる要素に気づく成績が下がる。既知の目標を探す成績は下がりにくい。同じ色を空間的にまとめると回復する。格子状の刺激での実験 | 色相の数を図全体で減らす。凡例を頼りに探す図では、色による分類を使ってよい | 研究 |
| [Strobelt ほか, 2016, テキスト強調手法の比較](https://vcg.seas.harvard.edu/publications/20160101-guidelines-for-effective-usage-of-text-highlighting-techniques) | 単独の強調手法の成績は、文字の大きさ0.86、枠線0.84、背景色0.78、赤文字0.76、太字0.74の順で、斜体は0.15だった。文中の語を探す課題での比較 | 強調には大きさや枠の太さを先に使う。すべての箱を太字にしない | 研究 |
| [Schneider ほか, 2018, 強調のメタ分析](https://www.clearinghouse.edu.tum.de/wp-content/uploads/2018/12/CHU_KR-22_-Schneider_2017_Lernmaterial_Hervorhebungen.pdf)（公式要約で確認、原著は未読） | 103研究・12,201人の分析で、強調は記憶（g = 0.53）と転移（g = 0.33）に効いた。図の中では色による強調が効き、矢印やラベルを足すだけの手がかりには明確な効果が見られなかった。点滅は逆効果だった。学習教材での結果 | 焦点は色で塗る。矢印を足すだけで視線を導いたことにしない | 研究 |
| [Hegarty, Canham & Fabrikant, 2010](https://www.ovid.com/journals/jeplm/pdf/00004786-201001000-00021~thinking-about-the-weather-how-display-salience-and)、[Hegarty, 2011, 総説](https://mechanism.ucsd.edu/bill/teaching/F12/cs200/Readings/hegarty.thecognitivescienceofvisua-spatialdisplays.implicationsfordesign.2011.pdf) | 課題に必要な情報を目立たせても、読み方を知る前は成績が変わらず、知った後にだけ向上した。視線は主に読者の課題と知識で決まる。天気図での推論課題 | 焦点の近くに、そこを見る理由を1文で添える。焦点のない参照用の図に強調を無理に作らない | 研究 |
| [NN/g の F 字型の読み方](https://nngroup.com/articles/f-shaped-pattern-reading-web-content/)（本文は未読、要約で確認） | 文章が中心のWebページで、構造の手がかりがないときの読み方の型。図の読み方の研究ではない。Z字型はこの研究に含まれない | F字型やZ字型で図を組まない。参考にするのは、左上から読み始めることだけ | 研究（文章） |
| [Duarte の Glance Test](https://www.duarte.com/resources/guides-tools/the-glance-test/)、Knaflic『Storytelling with Data』 | 短時間で主張が読み取れるかを確かめる。全体を灰色にして1か所だけ色を付け、人に最初に見た場所を尋ねる | 意図した答えを伝えない確認の3つの問い | 実務 |

## アイコンの使い方を決める根拠

`SKILL.md` の「アイコンは種類を示す札として使う」の根拠を示す。種別は上の表と同じ。
要約や二次資料で確認したものは、原著の数値と食い違う可能性がある。

| 根拠 | 示される知見と限界 | このキットでの応用 | 種別 |
|---|---|---|---|
| [McDougall, Curry & de Bruijn, 1999](https://eprints.bournemouth.ac.uk/10165/1/Measuring_symbol_and_icon_characteristics_mcdougall__curry_%26_debruijn_1999.pdf)、[McDougall, de Bruijn & Curry, 2000](https://doi.org/10.1037/1076-898X.6.4.291)（要約で確認） | 記号を具象性、複雑さ、意味の分かりやすさ、親しみ、意味の距離で測る枠組み。具象であることの利点は初見に限られ練習で消える一方、複雑さの不利は長く残る。UIのアイコンでの課題 | 線の少ない単純な形を選ぶ。種類どうしは形も意味も離す | 研究 |
| [Isherwood, McDougall & Curry, 2007](https://qastaffprofiles.bournemouth.ac.uk/display/journal-article/11106)（要約で確認） | 初見では絵と意味の距離が、慣れた後は親しみが、アイコンを理解する速さを左右する | 読者が見慣れた慣例の記号を、独自の記号より優先する。初見の読者向けには意味の近さを重視する | 研究 |
| Wiedenbeck, 1999（BIT 18(2)。本文は未取得、[二次資料](https://uxmyths.com/post/715009009/myth-icons-enhance-usability)で確認） | ラベル付きのアイコンが、習得の速さと使いやすさの評価で最もよかった。アイコンだけでは探索が速くならなかった | アイコンは必ず文字のラベルと組にする | 研究 |
| Bertin『図の記号学』（[解説](https://axismaps.com/guide/visual-variables)） | 形の違いは同じか違うかを伝えるが、同じ形の群を瞬時に拾い出させる力は弱い | 種類の群は配置で見せ、アイコンは読んだときの意味の理解を助ける役にする | 理論 |
| [Harp & Mayer, 1998](https://en.wikipedia.org/wiki/Seductive_details)、[Rey, 2012, メタ分析](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8442593/)（要約で確認、効果量は資料により異なる） | 興味を引くが本題と関係のない絵や話は、想起と応用の成績を下げる。視覚的なものほど影響が強い | 意味を担わない装飾のアイコンは置かない | 研究 |
| [Carney & Levin, 2002](https://bearworks.missouristate.edu/articles-chhs/956)（要約で確認） | 装飾の挿絵は学習を高めず、内容を表す、整理する、解釈を助ける挿絵は高める | アイコンは、箱が何かを表す役割だけに使う | 研究 |
| [Moody, 2009, Physics of Notations](https://bibbase.org/network/publication/moody-thephysicsofnotationstowardascientificbasisforconstructingvisualnotationsinsoftwareengineering)（要約で確認） | 記法の原則として、意味が透けて見えること、見分けやすいこと、1つの記号に複数の意味を、1つの意味に複数の記号を持たせないことを挙げる。検証が不足しているという批判がある | 1つの種類に1つの記号を対応させる | 理論 |
| NN/g, Harley, 2014, Icon Usability（本文は未取得、二次資料で確認） | 誰にでも通じるアイコンはホーム、印刷、検索など一部に限られ、それ以外には文字のラベルが必要になる | 慣例の記号がない概念にアイコンを作らない | 実務 |
| [ISO 9186-1](https://webstore.ansi.org/preview-pages/ISO/preview_ISO+9186-1-2014.pdf)（プレビューで確認、合格の基準値は未確認） | 図記号の理解度を、ラベルなしで見せて意味を答えさせる方法で試す | アイコンだけを見せて、何の種類かを答えさせる確認 | 規格 |
