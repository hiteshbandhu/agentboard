import AppKit
import Combine
import SwiftUI

/// A Dynamic Island–style strip around the MacBook notch.
///
/// Hidden when nothing is running. While agents work, two slim ears sit
/// beside the notch: the working agent's app icon on the left, an animated
/// waveform (or a needs-you badge) on the right. When an agent needs you or
/// finishes, the island drops open for a few seconds. Hovering the notch
/// opens it into a short list. It never takes clicks.
@MainActor
final class NotchController {
    private var panel: NSPanel?
    private let model = NotchModel()
    private var hoverTimer: Timer?
    private var screenObserver: Any?

    func start(board: Board) {
        model.attach(board)
        rebuild()
        screenObserver = NotificationCenter.default.addObserver(
            forName: NSApplication.didChangeScreenParametersNotification, object: nil, queue: .main
        ) { [weak self] _ in MainActor.assumeIsolated { self?.rebuild() } }
        // Poll the pointer: global mouse monitors miss moves over the menu bar
        // and don't fire at all without an active event tap.
        hoverTimer = Timer.scheduledTimer(withTimeInterval: 0.08, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in self.trackHover() }
        }
    }

    func setEnabled(_ on: Bool) {
        if on { panel?.orderFrontRegardless() } else { panel?.orderOut(nil) }
    }

    func announce(_ e: BoardEvent) { model.announce(e) }

    static var notchedScreen: NSScreen? {
        NSScreen.screens.first { $0.safeAreaInsets.top > 0 && $0.auxiliaryTopLeftArea != nil }
    }

    private func rebuild() {
        panel?.orderOut(nil)
        panel = nil
        guard let screen = NotchController.notchedScreen,
              let left = screen.auxiliaryTopLeftArea, let right = screen.auxiliaryTopRightArea else {
            model.geometry = nil
            return
        }
        let geo = NotchGeometry(
            notchWidth: screen.frame.width - left.width - right.width,
            notchHeight: screen.safeAreaInsets.top
        )
        model.geometry = geo

        let frame = NSRect(x: screen.frame.midX - geo.canvas.width / 2, y: screen.frame.maxY - geo.canvas.height,
                           width: geo.canvas.width, height: geo.canvas.height)
        let p = NSPanel(contentRect: frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        p.isOpaque = false
        p.backgroundColor = .clear
        p.hasShadow = false
        p.level = .statusBar
        p.collectionBehavior = [.canJoinAllSpaces, .stationary, .fullScreenAuxiliary, .ignoresCycle]
        p.ignoresMouseEvents = true
        // The island is always black: native controls (the spinner) must
        // draw their dark-mode variant regardless of the system setting.
        p.appearance = NSAppearance(named: .darkAqua)
        let host = ClickThroughHostingView(rootView: NotchView(model: model))
        host.sizingOptions = []
        p.contentView = host
        panel = p
        setEnabled(UserDefaults.standard.bool(forKey: "notch"))
    }

    private func trackHover() {
        guard panel?.isVisible == true, let screen = NotchController.notchedScreen, let geo = model.geometry else { return }
        let m = NSEvent.mouseLocation
        let top = screen.frame.maxY
        let zone: NSRect
        if model.hovering {
            let s = geo.size(for: .expanded(rows: model.rowCount))
            zone = NSRect(x: screen.frame.midX - s.width / 2, y: top - s.height, width: s.width, height: s.height)
        } else {
            zone = NSRect(x: screen.frame.midX - geo.notchWidth / 2, y: top - geo.notchHeight,
                          width: geo.notchWidth, height: geo.notchHeight)
        }
        let inside = zone.contains(m)
        if inside != model.hovering { model.hovering = inside }
        // Clicks reach the rows only while the list is open; otherwise they
        // fall through to whatever is under the notch.
        panel?.ignoresMouseEvents = !model.hovering
    }
}

/// Takes the first click even though the panel never becomes key, so one
/// click on a row is enough.
final class ClickThroughHostingView<Content: View>: NSHostingView<Content> {
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

enum NotchMode: Equatable {
    case hidden
    case compact
    case banner
    case expanded(rows: Int)
}

struct NotchGeometry {
    var notchWidth: CGFloat
    var notchHeight: CGFloat
    /// Width of each ear beside the notch.
    let ear: CGFloat = 38
    /// The outward curve where the island meets the bezel.
    let shoulder: CGFloat = 8

    static let rowHeight: CGFloat = 56
    var canvas: CGSize { CGSize(width: max(notchWidth + 2 * ear, 480) + 2 * shoulder + 40, height: notchHeight + 20 + 4 * NotchGeometry.rowHeight + 40) }

    func size(for mode: NotchMode) -> CGSize {
        switch mode {
        case .hidden: return CGSize(width: notchWidth, height: notchHeight)
        case .compact: return CGSize(width: notchWidth + 2 * ear, height: notchHeight)
        case .banner: return CGSize(width: max(notchWidth + 2 * ear, 420), height: notchHeight + 64)
        case .expanded(let rows): return CGSize(width: max(notchWidth + 2 * ear, 480), height: notchHeight + 14 + CGFloat(max(rows, 1)) * NotchGeometry.rowHeight)
        }
    }

    func radius(for mode: NotchMode) -> CGFloat {
        switch mode {
        case .hidden, .compact: return notchHeight * 0.32
        case .banner, .expanded: return 20
        }
    }
}

@MainActor
final class NotchModel: ObservableObject {
    @Published var geometry: NotchGeometry?
    @Published var hovering = false
    @Published private(set) var banner: BoardEvent?
    @Published private(set) var working: [Session] = []
    @Published private(set) var needsYou: [Session] = []
    @Published private(set) var visible: [Session] = []
    private var bannerTask: Task<Void, Never>?
    private var bag: Set<AnyCancellable> = []

    var rowCount: Int { min(4, max(1, visible.count)) }

    var mode: NotchMode {
        if hovering { return .expanded(rows: rowCount) }
        if banner != nil { return .banner }
        if !working.isEmpty || !needsYou.isEmpty { return .compact }
        return .hidden
    }

    private weak var board: Board?

    /// A row was clicked: go to that agent and fold the list away.
    func open(_ s: Session) {
        board?.focus(s)
        hovering = false
    }

    func attach(_ board: Board) {
        self.board = board
        board.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self, weak board] _ in
                DispatchQueue.main.async {
                    guard let self, let board else { return }
                    self.working = board.working
                    self.needsYou = board.needsYou
                    self.visible = board.sessions.filter { !$0.stale }
                }
            }
            .store(in: &bag)
    }

    func announce(_ e: BoardEvent) {
        bannerTask?.cancel()
        banner = e
        bannerTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(5))
            guard !Task.isCancelled else { return }
            self.banner = nil
        }
    }
}

struct NotchView: View {
    @ObservedObject var model: NotchModel

    var body: some View {
        if let geo = model.geometry {
            let mode = model.mode
            let size = geo.size(for: mode)
            VStack(spacing: 0) {
                island(geo: geo, mode: mode)
                    .frame(width: size.width + 2 * geo.shoulder, height: size.height, alignment: .top)
                    .background(IslandShape(radius: geo.radius(for: mode), shoulder: geo.shoulder).fill(.black))
                    .clipShape(IslandShape(radius: geo.radius(for: mode), shoulder: geo.shoulder))
                    .shadow(color: .black.opacity(mode == .compact || mode == .hidden ? 0 : 0.35), radius: 14, y: 6)
                Spacer(minLength: 0)
            }
            .frame(width: geo.canvas.width, height: geo.canvas.height, alignment: .top)
            .animation(.spring(response: 0.42, dampingFraction: 0.78), value: mode)
            .environment(\.colorScheme, .dark)
        }
    }

    @ViewBuilder
    private func island(geo: NotchGeometry, mode: NotchMode) -> some View {
        VStack(spacing: 0) {
            ears(geo: geo)
                .frame(height: geo.notchHeight)
                .opacity(mode == .hidden ? 0 : 1)
            switch mode {
            case .banner:
                if let e = model.banner { BannerRow(event: e).padding(.horizontal, 16 + geo.shoulder).transition(.blurFade) }
            case .expanded:
                AgentList(sessions: Array(model.visible.prefix(4))) { model.open($0) }
                    .padding(.horizontal, 8 + geo.shoulder)
                    .padding(.top, 4)
                    .transition(.blurFade)
            default:
                EmptyView()
            }
        }
    }

    private func ears(geo: NotchGeometry) -> some View {
        HStack(spacing: 0) {
            Group {
                if let first = model.needsYou.first ?? model.working.first {
                    AppIcon(provider: first.provider, size: 18)
                        .transition(.scale.combined(with: .opacity))
                }
            }
            .frame(width: geo.ear + geo.shoulder)

            Spacer(minLength: geo.notchWidth)

            Group {
                if !model.needsYou.isEmpty {
                    HStack(spacing: 3) {
                        Image(systemName: "exclamationmark.circle.fill")
                            .foregroundStyle(.orange)
                            .symbolEffect(.pulse)
                        if model.needsYou.count > 1 { count(model.needsYou.count) }
                    }
                } else if !model.working.isEmpty {
                    HStack(spacing: 4) {
                        Thinking(provider: model.working[0].provider)
                        if model.working.count > 1 { count(model.working.count) }
                    }
                }
            }
            .font(.system(size: 12, weight: .semibold))
            .frame(width: geo.ear + geo.shoulder)
        }
    }

    private func count(_ n: Int) -> some View {
        Text("\(n)")
            .font(.system(size: 11, weight: .semibold, design: .rounded))
            .foregroundStyle(.white)
            .contentTransition(.numericText())
    }
}

private struct BannerRow: View {
    let event: BoardEvent

    var body: some View {
        let s = event.session
        HStack(spacing: 10) {
            AppIcon(provider: s.provider, size: 34)
            VStack(alignment: .leading, spacing: 1) {
                Text(s.name)
                    .font(.system(size: 13, weight: .semibold))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                Text(line)
                    .font(.system(size: 11))
                    .foregroundStyle(.white.opacity(0.6))
                    .lineLimit(1)
            }
            Spacer(minLength: 8)
            Image(systemName: symbol)
                .font(.system(size: 20))
                .foregroundStyle(tint)
                .symbolEffect(.bounce, value: s.key)
        }
        .frame(height: 52)
    }

    private var line: String {
        switch event {
        case .needsYou(let s): return "Needs you · " + (s.last.map { $0.replacingOccurrences(of: "↳ ", with: "") } ?? s.project)
        case .finished(let s, let after): return (after > 60 ? "Finished after \(shortDuration(after))" : "Finished") + " · \(s.project)"
        case .started(let s): return "Started · \(s.project)"
        }
    }

    private var symbol: String {
        switch event {
        case .needsYou: return "exclamationmark.circle.fill"
        case .finished: return "checkmark.circle.fill"
        case .started: return "play.circle.fill"
        }
    }

    private var tint: Color {
        switch event {
        case .needsYou: return .orange
        default: return .green
        }
    }
}

private struct AgentList: View {
    let sessions: [Session]
    let onOpen: (Session) -> Void
    @State private var hovered: String?

    var body: some View {
        VStack(spacing: 0) {
            if sessions.isEmpty {
                Text("No agents running")
                    .font(.system(size: 12))
                    .foregroundStyle(.white.opacity(0.5))
                    .frame(height: NotchGeometry.rowHeight)
            }
            ForEach(sessions, id: \.key) { s in
                AgentRow(session: s)
                    .frame(height: NotchGeometry.rowHeight)
                    .padding(.horizontal, 6)
                    .background(RoundedRectangle(cornerRadius: 10).fill(.white.opacity(hovered == s.key && s.host == nil ? 0.08 : 0)))
                    .contentShape(Rectangle())
                    .onHover { hovered = $0 ? s.key : (hovered == s.key ? nil : hovered) }
                    .onTapGesture { onOpen(s) }
                    .help(s.host == nil ? "Open" : "Runs on \(s.host!)")
            }
        }
    }
}

/// One agent: name and status, what it's doing now, and where.
private struct AgentRow: View {
    let session: Session

    var body: some View {
        let s = session
        HStack(alignment: .top, spacing: 10) {
            Image(nsImage: ProjectIcon.badged(cwd: s.cwd, host: s.host, provider: s.provider, size: 30))
                .interpolation(.high)
                .frame(width: 30, height: 30)
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(s.name)
                        .font(.system(size: 12.5, weight: .semibold))
                        .foregroundStyle(.white)
                        .lineLimit(1)
                    Spacer(minLength: 8)
                    if s.runningSubagents > 0 {
                        HStack(spacing: 2) {
                            Image(systemName: "arrow.triangle.branch")
                            Text("\(s.runningSubagents)").monospacedDigit()
                        }
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.green.opacity(0.9))
                        .help(s.subagents?.label ?? "")
                    }
                    if s.working { Thinking(provider: s.provider).font(.system(size: 11)) }
                    TimelineView(.periodic(from: .now, by: 1)) { ctx in
                        Text(status(ctx.date))
                            .font(.system(size: 11, weight: .medium))
                            .monospacedDigit()
                            .foregroundStyle(color)
                    }
                }
                Text(activity)
                    .font(.system(size: 11))
                    .foregroundStyle(.white.opacity(s.working || s.needsYou ? 0.78 : 0.5))
                    .lineLimit(1)
                    .truncationMode(.tail)
                Text(meta)
                    .font(.system(size: 10))
                    .foregroundStyle(.white.opacity(0.38))
                    .lineLimit(1)
            }
        }
    }

    private var activity: String {
        if let last = session.last, !last.isEmpty {
            return last.hasPrefix("↳ ") ? "“" + plain(String(last.dropFirst(2))) + "”" : "▸ " + last
        }
        if let p = session.prompt { return "Asked “\(p)”" }
        return "No activity yet"
    }

    /// Drops markdown emphasis and code marks from a reply snippet.
    private func plain(_ s: String) -> String {
        s.replacingOccurrences(of: "**", with: "")
            .replacingOccurrences(of: "`", with: "")
            .replacingOccurrences(of: #"^#+\s*"#, with: "", options: .regularExpression)
            .replacingOccurrences(of: " - ", with: " · ")
    }

    private var meta: String {
        var parts = [session.project]
        if let m = session.model, !m.isEmpty { parts.append(Model.display(m)) }
        if let c = session.context_tokens, c > 0 { parts.append("\(c / 1000)k context") }
        if let sa = session.subagents, sa.total > 0, session.runningSubagents == 0 { parts.append(sa.label) }
        if let h = session.host, !h.isEmpty { parts.append(h) }
        return parts.joined(separator: " · ")
    }

    private func status(_ now: Date) -> String {
        let word = statusWord(session.status)
        guard let since = session.status_since else { return word }
        return "\(word) · \(shortDuration(now.timeIntervalSince(since)))"
    }

    private var color: Color {
        switch session.status {
        case "busy": return .green
        case "waiting": return .orange
        case "error": return .red
        default: return .white.opacity(0.5)
        }
    }
}

/// Each tool's own "thinking" animation: Claude Code's cycling ✻ glyph in
/// clay, Codex's typing ellipsis.
struct Thinking: View {
    let provider: String
    private static let frames = ["·", "✢", "✳", "✶", "✻", "✽", "✻", "✶", "✳", "✢"]

    var body: some View {
        if provider == "claude" {
            TimelineView(.periodic(from: .now, by: 0.12)) { ctx in
                let i = Int(ctx.date.timeIntervalSinceReferenceDate / 0.12) % Thinking.frames.count
                Text(Thinking.frames[i])
                    .font(.system(size: 14, weight: .bold))
                    .foregroundStyle(Color(nsColor: Provider.color("claude")))
                    .frame(width: 14)
            }
        } else {
            Image(systemName: "ellipsis")
                .font(.system(size: 13, weight: .bold))
                .foregroundStyle(Color(nsColor: Provider.color(provider)))
                .symbolEffect(.variableColor.iterative.dimInactiveLayers)
        }
    }
}

/// Flat top flush with the screen edge, small concave shoulders where it
/// meets the bezel, and rounded bottom corners, like the Dynamic Island.
struct IslandShape: Shape {
    var radius: CGFloat
    var shoulder: CGFloat

    var animatableData: CGFloat {
        get { radius }
        set { radius = newValue }
    }

    func path(in r: CGRect) -> Path {
        let s = shoulder
        let rad = min(radius, (r.height) / 2, (r.width - 2 * s) / 2)
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.minY))
        p.addQuadCurve(to: CGPoint(x: r.minX + s, y: r.minY + s), control: CGPoint(x: r.minX + s, y: r.minY))
        p.addLine(to: CGPoint(x: r.minX + s, y: r.maxY - rad))
        p.addQuadCurve(to: CGPoint(x: r.minX + s + rad, y: r.maxY), control: CGPoint(x: r.minX + s, y: r.maxY))
        p.addLine(to: CGPoint(x: r.maxX - s - rad, y: r.maxY))
        p.addQuadCurve(to: CGPoint(x: r.maxX - s, y: r.maxY - rad), control: CGPoint(x: r.maxX - s, y: r.maxY))
        p.addLine(to: CGPoint(x: r.maxX - s, y: r.minY + s))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.minY), control: CGPoint(x: r.maxX - s, y: r.minY))
        p.closeSubpath()
        return p
    }
}

extension AnyTransition {
    /// Content comes in after the island has mostly grown, and leaves before
    /// it starts shrinking, so text never outlives its background.
    static var blurFade: AnyTransition {
        .asymmetric(
            insertion: .modifier(active: BlurFade(amount: 1), identity: BlurFade(amount: 0))
                .animation(.easeOut(duration: 0.22).delay(0.14)),
            removal: .modifier(active: BlurFade(amount: 1), identity: BlurFade(amount: 0))
                .animation(.easeIn(duration: 0.1))
        )
    }
}

private struct BlurFade: ViewModifier {
    let amount: CGFloat
    func body(content: Content) -> some View {
        content
            .blur(radius: 6 * amount)
            .opacity(1 - amount)
            .scaleEffect(1 - 0.06 * amount, anchor: .top)
    }
}
