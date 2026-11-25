---
topic: sidestore-ios-update-recovery
updated: 2026-11-25
status: implementation-under-test-physical-recovery-unverified
---

# iOS更新後にSideStoreが使えない場合

## 現在の事実と未確認事項

- 利用者の家族端末で「iOS 27.2.1と思われる版に更新後、SideStoreのアイコンを押しても反応しない」という報告がある。OSの正確なビルド、アラート、クラッシュログは未取得。
- **この報告だけではペアリング不一致とは断定できない。** 起動拒否（署名期限・失効・開発者の信頼）、即時クラッシュ、アイコンやOS側の問題も区別する。
- 既存改造版でのiPhone/Watch導入・手動Refresh成功は過去の実機確認済み。今回の家族端末の復旧や将来のiOS対応が確認済みという意味ではない。
- Fairway本体・Watchアプリ・保存スコアは削除しない。既存の証明書を一括失効させない。ペアリングファイルやKeychainを一括削除しない。

## 通常版は更新に耐えられるのか

完全には耐えられない。公式の[Pairing File説明](https://docs.sidestore.io/docs/advanced/pairing-file)も、OS更新・リセット等でペアリングの再作成が必要になる場合があると説明している。これは改造版だけの制約ではない。

固定ベースの通常版には既にBonjourによるRemote Pairingポート再検出と限定再試行がある。`MinimuxerWrapper.swift`の`resolveDiscoveredRemotePairingPort`、`withRemotePairingRetry`を再利用する。手動ポート指定は優先する。

一方、通常版には起動直後のクラッシュ報告もある。[Issue #1630](https://github.com/SideStore/SideStore/issues/1630)では、保存済みPKCS#12の解析中にASN.1の長さ計算が不正になってSwiftのRangeトラップが起きるという、シンボル化した解析が投稿されている。同じ処理は固定したCodeSignKitにも存在したため、今回修正した。ただし、この家族端末も同じ原因だと証明するものではない。

[Issue #1723](https://github.com/SideStore/SideStore/issues/1723)には、iOS 27.2のロック中の自動更新がRemotePairingError 1016で失敗する報告がある。「最近ロック解除されていない」という一時的な条件を、永久に壊れたペアリングと混同しない。

## 操作手順：まずiPhoneだけで確認

1. iPhoneを通常の方法で再起動し、**パスコードで一度ロック解除**する。AppライブラリでSideStoreを検索して開く。ホームの古いショートカットだけが反応しない場合と分ける。
2. 起動を拒否するアラートが出た場合は、その文言を記録する。「もう利用できません」等はペアリング修正では直せない場合がある。
3. iPhoneの「設定 → 一般 → VPNとデバイス管理」で、SideStoreに使っている開発者が信頼済みか確認する。信頼の確認が表示された場合だけ案内に従う。「Appを削除」は押さない。
4. 「設定 → プライバシーとセキュリティ → デベロッパモード」が表示される場合は有効か確認する。既に有効なら不要なオフ・オンはしない。
5. 画面が一瞬出てすぐ消える場合は「設定 → プライバシーとセキュリティ → 解析と改善 → 解析データ」で同時刻のSideStoreの`.ips`を確認する。ログは個人情報を含み得るため公開リポジトリには置かない。必要なのはException Type、Termination Reasonとシンボル化した該当スタック。
6. SideStoreを開ける場合だけ、Wi-FiとLocalDevVPNを接続し、SideStoreの「Settings → Watch対応 → iOS更新後の接続確認 → iPhoneの接続を確認」を押す。`OS Recovery 20261125`が新版の識別表示。
7. 接続成功後、「My Apps」でSideStoreの残り日数を押してRefreshし、次にFairwayの残り日数を押す。最後にWatchでFairwayを開く。日数表示だけで全端末の成功と判定しない。

### SideStoreが開けないままの場合

起動できないアプリ自身の修復ボタン・自動更新は実行できない。iOSが署名を受け付けない場合は新しい署名が必要で、アプリ内部からそれを回避する機能は実装できない。

WindowsのLoaderから**今回の改造版SideStoreだけを、同じApple Account・同じ署名後アプリIDで上書き**する経路がある。FairwayをLoader経由で入れ直す必要はない。既存のSideStoreと違うID・チームになる場合は中止して確認する。単に同じ表示名であるだけでは同一アプリとは限らない。証明書再利用を優先し、失効を求める画面ではそのまま進めない。

上書き後にSideStoreが開いたら、上記6～7へ進む。起動が復旧しても、ペアリングが有効かはその後に別途確認する。

### 本当にペアリングが無効だった場合

1. 先にロック解除・VPN・ポートを確認する。1016やネットワークエラーだけならファイルを削除しない。
2. 新しい正しいRemote Pairingファイルが手元にあれば「Settings → Watch対応 → ペアリングファイルの管理」のRemote Pairingカードのメニューから「Import / Replace File」を選んで読み込む。必要なら同じカードでPreferredに指定し、再起動して確認する。
3. 新しいファイルがない場合は、既存の「Wireless Pairing」機能で対応する接続先と承認手順を使える場合がある。ただし、この構成で同じiPhone単体の再ペアリングが必ず可能だという実機証拠はない。無効な鍵を計算して元に戻すことはできない。
4. 必要な場合だけWindowsで新しいRemote Pairingを生成してSideStoreに読み込む。既存WatchペアリングのKeychainは別物なので削除しない。アプリの削除・Apple Account変更は不要。

## 今回追加したコード

`tools/watch-support/apply_os_recovery.py`を既存GroupFixの**後**に適用する。

- CodeSignKit `d0c67710fda9a2646b9e829cb2cf443892728371`をローカル依存にし、SideSignのテストとXcode実アーカイブの両方を修正版に向ける。テストだけ直った別依存にしない。
- ASN.1長さの負数・オーバーフロー・欠落・負のオフセットを拒否し、PKCS#12解析をクラッシュから通常の失敗へ変える。証明書そのものや秘密鍵は消さない。
- OS版・ビルド文字列の変化を検出して、次のRemote Pairing起動前に既存のBonjourポート再検出を試す。具体的なiOS版の比較・上限値には依存しない。初回導入では以前のOSを推定できないので、明示ボタンを使える。
- 再検出失敗時は最後のポートを保持する。手動ポート指定・自動再試行のオフ設定は維持する。
- RemotePairingError 1016を「ロックを解除して再試行」として扱い、誤ったペアリング再作成誘導を減らす。
- 接続確認と復旧ガイドの画面を追加する。ここでの成功はiPhoneとの通信成功であり、Apple認証・署名・Watch導入成功の証明ではない。
- ペアリングのImportでは旧ファイルを先に削除せず、atomic書き込みで置き換える。書き込み失敗で旧ファイルを失う窓をなくす。別ファイルの端末同一性を自動証明する機能ではない。

判定ロジックは`tools/watch-support/Recovery/Sources/FWOSRecovery/RecoveryAdvice.swift`。同一ソースをDeviceGatewayとSideSignへ組み込み、独立Swift Packageでテストする。証明書解析の回帰テストは`SideSign/OSRecoveryTests.swift`。

```sh
swift test --package-path tools/watch-support/Recovery
# 既存overlay群の後、固定CodeSignKitをDependencies/CodeSignKitへ配置して実行
python3 tools/watch-support/apply_os_recovery.py build/SideStore
cd build/SideStore/Dependencies/SideSign
swift test --filter 'WatchSupportTests|OSRecoveryTests'
```

ビルドは`.github/workflows/sidestore-watch-probe.yml`の専用ブランチで行う。元の実機成功版は置き換えず保持する。

## 確認すべき受け入れ条件

- [ ] 改造版を同一IDで上書きし、SideStoreが開く。既存のアプリ一覧・Accountが維持される。
- [ ] iPhone接続確認、SideStore Refresh、Fairway Refreshが成功する。
- [ ] WatchでFairwayを開き、既存スコアを確認する。
- [ ] OS更新の前後で同じ条件を再確認する。
- [ ] ショートカットの自動実行結果と、旧署名期限後のWatch起動を別途確認する。

未知のiOSでAppleが通信方式や署名要件を変える場合は、新しい実装が必要になり得る。今回は既知の失敗の扱いと復旧性を改善するもので、将来の全iOSでの無条件動作を保証しない。
## 別実装の参考：端末内での再ペアリング

[SideInstallerのPairingController](https://github.com/FrizzleM/SideInstaller/blob/08936ec54189a6b4f9228ac605ab6f21c8d283d8/ios-app/PairingController.swift)と[Rust側ホスト実装](https://github.com/FrizzleM/SideInstaller/blob/08936ec54189a6b4f9228ac605ab6f21c8d283d8/rust-core/src/pairing.rs)には、同じiPhoneでRemote Pairingホストを動かし、設定側の承認でファイルを作る実装がある。PINを別画面でも見られるようにする処理、設定へ移動中の実行維持、キャンセル・段階ごとのタイムアウト、ホスト識別子の維持が必要になる。

これは「PCなしで新しいペアリングを生成する」追加候補。ただし、起動しないSideStore自身でこの処理を実行することはできない。別の既に起動できる署名ツールや別端末を使う復旧経路は別途設計が必要。今回はこのコードを無検証で移植せず、起動障害・接続障害の区別と既存経路を壊さない対策を適用した。
