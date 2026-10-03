import AppKit
import SwiftUI

/// `HallMonitor --snapshot <dir>` renders the notch in each of its states to
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
            // Before any data: just the notch itself.
            render(model, geo, dir, "notch_hidden")
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
                            renderView(SettingsView(), size: NSSize(width: 460, height: 420), dir, "settings")
                            renderWindow(board: board, dir: dir) { NSApp.terminate(nil) }
                        }
                    }
                }
            }
        }
    }

    /// The main window, each pane, after a couple of snapshots of history.
    private static func renderWindow(board: Board, dir: String, done: @escaping () -> Void) {
        let usage = UsageStore(board: board)
        usage.load()
        let nav = Nav()
        nav.selection = board.sessions.first(where: \.working)?.key
        // Let a few snapshots arrive so the timelines and fleet chart have data.
        DispatchQueue.main.asyncAfter(deadline: .now() + 12) {
            for pane in Pane.allCases {
                nav.pane = pane
                renderView(MainView(board: board, usage: usage, nav: nav).transaction { $0.animation = nil },
                           size: NSSize(width: 1280, height: 820), dir, "window_\(pane.rawValue)", opaque: true)
            }
            done()
        }
    }

    private static func render(_ model: NotchModel, _ geo: NotchGeometry, _ dir: String, _ name: String) {
        renderView(NotchView(model: model).transaction { $0.animation = nil }, size: geo.canvas, dir, name)
    }

    private static func renderView<V: View>(_ view: V, size: NSSize, _ dir: String, _ name: String, opaque: Bool = false) {
        let host = NSHostingView(rootView: view)
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
