"""Last-stage OS recovery overlay. Does not erase trust, accounts or app data."""
from pathlib import Path
import re
import shutil
import sys
from apply import replace
HERE = Path(__file__).resolve().parent

def apply(store: Path):
    sign = store / 'Dependencies/SideSign'
    code = store / 'Dependencies/CodeSignKit'
    path = 'Sources/ASN1Helper.swift'
    text = (code/path).read_text(encoding='utf-8')
    start = text.index('    public static func parseTLV(')
    end = text.index('    public static func parseSequenceChildren(', start)
    replacement = '''    public static func parseTLV(from data: Data, at offset: Int = 0) -> (tag: UInt8, value: Data, totalLength: Int)? {
        // Damaged/decrypted PKCS#12 must throw upstream, never trap on boot.
        guard offset >= 0, offset <= data.count, data.count - offset >= 2 else { return nil }
        func byte(_ n: Int) -> UInt8 { data[data.index(data.startIndex, offsetBy: n)] }
        let tag = byte(offset)
        var current = offset + 1
        let firstLen = byte(current)
        current += 1
        var length = Int(firstLen)
        if (firstLen & 0x80) != 0 {
            let count = Int(firstLen & 0x7f)
            guard count > 0, count <= MemoryLayout<Int>.size, count <= data.count - current else { return nil }
            length = 0
            for i in 0..<count {
                let next = Int(byte(current + i))
                guard length <= (Int.max - next) / 256 else { return nil }
                length = length * 256 + next
            }
            current += count
        }
        guard length <= data.count - current else { return nil }
        let lower = data.index(data.startIndex, offsetBy: current)
        let upper = data.index(lower, offsetBy: length)
        return (tag, data.subdata(in: lower..<upper), current + length - offset)
    }

'''
    assert 'guard current + length <= data.count' in text[start:end], 'Unexpected ASN1 upstream'
    (code/path).write_text(text[:start]+replacement+text[end:],encoding='utf-8',newline='\n')
    replace(sign,'Package.swift', '.package(url: "https://github.com/mahee96/CodeSignKit.git",   branch: "main")', '.package(path: "../CodeSignKit")')
    project = store/'AltStore.xcodeproj/project.pbxproj'
    text = project.read_text(encoding='utf-8')
    pattern = r'A8E8DEA43059BC8800F69B47 /\* XCRemoteSwiftPackageReference "CodeSignKit" \*/ = \{.*?\n\t\t\};'
    text,count = re.subn(pattern, '''A8E8DEA43059BC8800F69B47 /* XCLocalSwiftPackageReference "Dependencies/CodeSignKit" */ = {
            isa = XCLocalSwiftPackageReference;
            relativePath = Dependencies/CodeSignKit;
        };''',text,flags=re.S)
    assert count == 1, 'Unexpected Xcode CodeSignKit reference'
    text = text.replace('A8E8DEA43059BC8800F69B47 /* XCRemoteSwiftPackageReference "CodeSignKit" */', 'A8E8DEA43059BC8800F69B47 /* XCLocalSwiftPackageReference "Dependencies/CodeSignKit" */')
    project.write_text(text,encoding='utf-8',newline='\n')
    shutil.copyfile(HERE/'SideSign/OSRecoveryTests.swift',sign/'Tests/SideSignTests/OSRecoveryTests.swift')
    policy = (HERE/'Recovery/Sources/FWOSRecovery/RecoveryAdvice.swift').read_text(encoding='utf-8')
    gateway = store/'Dependencies/minimuxer/DeviceGateway'
    replace(gateway,'idevice/IdeviceGateway.swift','            if isPairingError(err) {', '''            if FWOSRecoveryAdvice.classify(message: msg) == .unlockPhone {
                let error = IdeviceGatewayError(.connectionFailed, reason: FWOSRecoveryAdvice.unlockPhone.instruction)
                lastError = error
                throw error
            }
            if isPairingError(err) {''')
    with (gateway/'idevice/IdeviceGateway.swift').open('a',encoding='utf-8',newline='\n') as out:
        out.write('\n'+policy)
    (sign/'Sources/Models/FWOSRecoveryAdvice.swift').write_text(policy,encoding='utf-8',newline='\n')
    replace(store,'SideStore/Core/Pairing/PairingFileManager.swift', '''        if fm.fileExists(atPath: destinationURL.path) {
            try? fm.removeItem(at: destinationURL)
        }
        try contents.write''', '''        // Atomic replacement preserves old credentials if the new write fails.
        try contents.write''')
    path = 'SideStore/Core/DeviceApi/MinimuxerWrapper.swift'
    replace(store,path,'private func resolveDiscoveredRemotePairingPort() async -> UInt16? {\n    guard UserDefaults.standard.isAutoRetryRemotePairingPortEnabled else {', 'private func resolveDiscoveredRemotePairingPort(allowDisabled: Bool = false) async -> UInt16? {\n    guard allowDisabled || UserDefaults.standard.isAutoRetryRemotePairingPortEnabled else {')
    replace(store,path,'    await bindConnectionConfig()\n    debugLog("[SideStore] minimuxerStart(pairingFile) invoked")', '''    await bindConnectionConfig()
    if UserDefaults.standard.bool(forKey: "FWOSRecoveryPortCheckPending"),
       preferred == .rppairing,
       let port = await resolveDiscoveredRemotePairingPort() {
        remotePairingPortCache = port
        minimuxer.set(MinimuxerParams(remotePairingPort: port))
        UserDefaults.standard.set(false, forKey: "FWOSRecoveryPortCheckPending")
    }
    debugLog("[SideStore] minimuxerStart(pairingFile) invoked")''')
    with (store/path).open('a',encoding='utf-8',newline='\n') as out:
        out.write('''
// Explicit connection preflight: no account/certificate/trust reset.
func fairwayCheckPhoneConnection() async throws {
    if PairingFileManager.shared.preferredProtocol == .rppairing,
       let port = await resolveDiscoveredRemotePairingPort(allowDisabled: true) {
        remotePairingPortCache = port
        minimuxer.set(MinimuxerParams(remotePairingPort: port))
    }
    try await ensureMinimuxerReady()
    _ = try await fetchUDID(forceLive: true)
}
''')
    replace(store,'AltStore/AppDelegate.swift','        UserDefaults.registerDefaults()\n', '''        UserDefaults.registerDefaults()
        let fwOSKey = "FWOSRecoveryLastObservedOS"
        let fwCurrentOS = ProcessInfo.processInfo.operatingSystemVersionString
        if SideSign.FWOSRecoveryAdvice.osChanged(previous: UserDefaults.standard.string(forKey: fwOSKey), current: fwCurrentOS) {
            // Keep the last usable port until discovery returns a replacement.
            // Preserve manual overrides, accounts, and both phone/Watch trust.
            UserDefaults.standard.set(true, forKey: "FWOSRecoveryPortCheckPending")
        }
        UserDefaults.standard.set(fwCurrentOS, forKey: fwOSKey)
''')
    path = 'SideStore/Core/WatchSupportSettings.swift'
    replace(store,path,'            Section("使い方") {', '''            Section("iOS更新後の接続確認") {
                Text("OS Recovery 20261125").font(.caption).foregroundColor(.secondary)
                NavigationLink("ペアリングファイルの管理") { PairingFileManagementView() }
                Text("iPhoneのロックを解除し、Wi-FiとLocalDevVPNを接続して確認します。接続先のポートを再検出します。手動指定したポートは維持します。")
                SwiftUI.Button("iPhoneの接続を確認") { checkPhone() }.disabled(busy)
                Text("SideStoreが開けない場合は、iPhoneの設定で開発者の信頼とDeveloper Modeを確認してください。署名が期限切れなら、同じApple Account・同じアプリIDでSideStoreだけを上書きします。Fairwayは削除しません。")
                Text("本当に無効になったペアリングは再作成が必要な場合があります。SettingsのPairing Fileから新しいRemote Pairingファイルを読み込みます。")
                Text("自動更新がロック中に失敗するときは、解除後に手動Refreshしてください。OSの制限を回避して必ず自動実行できるわけではありません。")
            }
            Section("使い方") {''')
    replace(store,path,'    private func register() {', '''    private func checkPhone() {
        busy = true; message = "iPhoneの接続を確認中…"
        Task { @MainActor in
            defer { busy = false }
            do {
                try await fairwayCheckPhoneConnection()
                message = "iPhoneへの接続を確認しました。次にMy AppsでSideStore、Fairwayの順にRefreshし、Watchでも起動を確認してください。"
            } catch {
                message = SideSign.FWOSRecoveryAdvice.classify(message: String(describing: error)).instruction
            }
        }
    }
    private func register() {''')

if __name__ == '__main__':
    apply(Path(sys.argv[1]).resolve())