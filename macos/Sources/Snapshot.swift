import AppKit
import SwiftUI

/// `AgentBoard --snapshot <dir>` renders the notch in each of its states to
/// transparent PNGs, for docs and the launch video, then quits. It uses the
/// same views and the same live data feed as the running app.
@MainActor
enum SnapshotMode {
    static func run(board: Board, dir: String) {
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        // Give the stream a moment to deliver a few snapshots and icons to load.
        DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
            let screen = NotchController.notchedScreen ?? NSScreen.main!
            let geo = NotchGeometry(
                notchWidth: screen.auxiliaryTopLeftArea.map { screen.frame.width - $0.width - (screen.auxiliaryTopRightArea?.width ?? 0) } ?? 185,
                notchHeight: screen.safeAreaInsets.top > 0 ? screen.safeAreaInsets.top : 32
            )
            let model = NotchModel()
            model.geometry = geo
            model.attach(board)
            board.objectWillChange.send()

            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
                render(model, geo, dir, "notch_compact")
                model.hovering = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                    render(model, geo, dir, "notch_expanded")
                    model.hovering = false
                    if let s = board.sessions.first(where: { $0.provider == "codex" }) ?? board.sessions.first {
                        var waiting = s
                        waiting.status = "waiting"
                        waiting.last = "approve: exec · pnpm playwright test"
                        model.announce(.needsYou(waiting))
                    }
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                        render(model, geo, dir, "notch_banner_needs")
                        if let s = board.sessions.first(where: { $0.provider == "claude" }) {
                            model.announce(.finished(s, after: 754))
                        }
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                            render(model, geo, dir, "notch_banner_done")
                            NSApp.terminate(nil)
                        }
                    }
                }
            }
        }
    }

    private static func render(_ model: NotchModel, _ geo: NotchGeometry, _ dir: String, _ name: String) {
        let size = geo.canvas
        let host = NSHostingView(rootView: NotchView(model: model).transaction { $0.animation = nil })
        host.frame = NSRect(origin: .zero, size: size)
        let win = NSWindow(contentRect: NSRect(x: -20000, y: -20000, width: size.width, height: size.height),
                           styleMask: [.borderless], backing: .buffered, defer: false)
        win.isOpaque = false
        win.backgroundColor = .clear
        win.appearance = NSAppearance(named: .darkAqua)
        win.contentView = host
        win.orderFrontRegardless()
        host.layoutSubtreeIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.3))
        guard let rep = host.bitmapImageRepForCachingDisplay(in: host.bounds) else { return }
        host.cacheDisplay(in: host.bounds, to: rep)
        let url = URL(fileURLWithPath: dir).appendingPathComponent(name + ".png")
        try? rep.representation(using: .png, properties: [:])?.write(to: url)
        win.orderOut(nil)
    }
}
