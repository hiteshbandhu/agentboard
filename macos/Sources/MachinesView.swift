import SwiftUI

// MARK: - Machines: this Mac and every host watched over SSH

struct MachinesView: View {
    @ObservedObject var board: Board
    @State private var newHost = ""
    @State private var adding = false
    @FocusState private var fieldFocused: Bool

    var body: some View {
        let machines = board.machines
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                PaneHeader(title: "Machines",
                           subtitle: "\(machines.count) machine\(machines.count == 1 ? "" : "s") · \(machines.reduce(0) { $0 + $1.agents.count }) agents") {
                    EmptyView()
                }
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 300, maximum: 520), spacing: 14, alignment: .top)],
                          alignment: .leading, spacing: 14) {
                    ForEach(machines) { m in
                        MachineCard(machine: m) { remove(m) }
                            .transition(.scale(scale: 0.96).combined(with: .opacity))
                    }
                }
                .animation(.spring(response: 0.42, dampingFraction: 0.86), value: machines.map(\.id))

                VStack(alignment: .leading, spacing: 10) {
                    Text("Watch another machine").font(Theme.display(14))
                    Text("Hall Monitor connects with your own SSH keys and runs `hallmonitor --stream` there. Install it on the machine first; no daemon or open port needed.")
                        .font(Theme.font(12.5))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    HStack {
                        TextField("user@host or an ~/.ssh/config alias", text: $newHost)
                            .textFieldStyle(.roundedBorder)
                            .focused($fieldFocused)
                            .onSubmit(add)
                        Button("Add", action: add)
                            .buttonStyle(.borderedProminent)
                            .disabled(newHost.trimmingCharacters(in: .whitespaces).isEmpty)
                    }
                    .frame(maxWidth: 520)
                }
                .padding(16)
                .background(Card())
            }
            .padding(24)
        }
        .background(Backdrop())
    }

    private func add() {
        let h = newHost.trimmingCharacters(in: .whitespaces)
        // An ssh destination, nothing that could be read as an option or a command.
        guard !h.isEmpty, !h.hasPrefix("-"), h.range(of: #"^[A-Za-z0-9._@:\[\]-]+$"#, options: .regularExpression) != nil else { return }
        var hosts = Hosts.read()
        guard !hosts.contains(h) else { newHost = ""; return }
        hosts.append(h)
        Hosts.write(hosts)
        newHost = ""
        board.restart()
    }

    private func remove(_ m: Machine) {
        guard let h = m.host else { return }
        Hosts.write(Hosts.read().filter { $0 != h })
        board.restart()
    }
}

private struct MachineCard: View {
    let machine: Machine
    let onRemove: () -> Void

    var body: some View {
        let m = machine
        let working = m.agents.filter(\.working).count
        let needs = m.agents.filter(\.needsYou).count
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 10) {
                Image(systemName: m.host == nil ? "laptopcomputer" : "server.rack")
                    .font(Theme.font(22))
                    .foregroundStyle(.white.opacity(0.8))
                    .frame(width: 30)
                VStack(alignment: .leading, spacing: 2) {
                    Text(m.name).font(Theme.display(14))
                    Text(m.host == nil ? "Local" : (m.host == m.name ? "SSH" : "SSH · \(m.host!)"))
                        .font(Theme.font(11)).foregroundStyle(.secondary)
                }
                Spacer()
                HStack(spacing: 5) {
                    Circle().fill(m.live ? Palette.working : Palette.error).frame(width: 7, height: 7)
                    Text(m.live ? "Live" : "Offline").font(Theme.font(11, .semibold))
                        .foregroundStyle(m.live ? Palette.working : Palette.error)
                }
            }
            if let e = m.error {
                Text(e).font(Theme.font(11)).foregroundStyle(Palette.error).lineLimit(2)
            }
            HStack(spacing: 18) {
                count("Agents", m.agents.count, .primary)
                count("Working", working, working > 0 ? Palette.working : .secondary)
                count("Need you", needs, needs > 0 ? Palette.needsYou : .secondary)
            }
            if !m.agents.isEmpty {
                VStack(alignment: .leading, spacing: 5) {
                    ForEach(m.agents.prefix(4), id: \.key) { s in
                        HStack(spacing: 6) {
                            Circle().fill(Palette.status(s)).frame(width: 6, height: 6)
                            Text(s.name).font(Theme.font(12.5)).lineLimit(1)
                            Spacer()
                            Text(statusWord(s.status)).font(Theme.font(11)).foregroundStyle(.secondary)
                        }
                    }
                }
            }
        }
        .padding(16)
        .background(Card(highlight: m.live ? nil : Palette.error.opacity(0.6)))
        .contextMenu {
            if m.host != nil { Button("Stop watching", role: .destructive, action: onRemove) }
        }
    }

    private func count(_ label: String, _ n: Int, _ c: Color) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("\(n)")
                .font(Theme.number(22))
                .monospacedDigit()
                .foregroundStyle(c)
                .contentTransition(.numericText(value: Double(n)))
            Text(label).font(Theme.font(11)).foregroundStyle(.secondary)
        }
        .animation(.spring(response: 0.4, dampingFraction: 0.8), value: n)
    }
}
