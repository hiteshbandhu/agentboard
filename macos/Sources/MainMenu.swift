import AppKit

/// The menu bar shown while the window is open: the standard App, Edit,
/// View and Window menus, so ⌘Q, ⌘W, ⌘M, copy/paste and full screen work
/// like in any Mac app.
@MainActor
enum MainMenu {
    static func install(openPane: @escaping (Pane) -> Void, settings: @escaping () -> Void) {
        let target = Target(openPane: openPane, settings: settings)
        Target.shared = target
        let bar = NSMenu()

        let app = NSMenu()
        app.addItem(withTitle: "About Hall Monitor", action: #selector(NSApplication.orderFrontStandardAboutPanel(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(item("Settings…", #selector(Target.settings), ",", target))
        app.addItem(.separator())
        app.addItem(withTitle: "Hide Hall Monitor", action: #selector(NSApplication.hide(_:)), keyEquivalent: "h")
        let others = app.addItem(withTitle: "Hide Others", action: #selector(NSApplication.hideOtherApplications(_:)), keyEquivalent: "h")
        others.keyEquivalentModifierMask = [.command, .option]
        app.addItem(withTitle: "Show All", action: #selector(NSApplication.unhideAllApplications(_:)), keyEquivalent: "")
        app.addItem(.separator())
        app.addItem(withTitle: "Quit Hall Monitor", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        add(bar, "Hall Monitor", app)

        let edit = NSMenu(title: "Edit")
        edit.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = edit.addItem(withTitle: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        edit.addItem(.separator())
        edit.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        edit.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        edit.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        edit.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        add(bar, "Edit", edit)

        let view = NSMenu(title: "View")
        for (i, p) in Pane.allCases.enumerated() {
            let it = item(p.title, #selector(Target.pane(_:)), "\(i + 1)", target)
            it.tag = i
            view.addItem(it)
        }
        view.addItem(.separator())
        let sidebar = view.addItem(withTitle: "Toggle Sidebar", action: #selector(NSSplitViewController.toggleSidebar(_:)), keyEquivalent: "s")
        sidebar.keyEquivalentModifierMask = [.command, .control]
        let full = view.addItem(withTitle: "Enter Full Screen", action: #selector(NSWindow.toggleFullScreen(_:)), keyEquivalent: "f")
        full.keyEquivalentModifierMask = [.command, .control]
        add(bar, "View", view)

        let window = NSMenu(title: "Window")
        window.addItem(withTitle: "Minimize", action: #selector(NSWindow.performMiniaturize(_:)), keyEquivalent: "m")
        window.addItem(withTitle: "Zoom", action: #selector(NSWindow.performZoom(_:)), keyEquivalent: "")
        window.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        add(bar, "Window", window)
        NSApp.windowsMenu = window

        NSApp.mainMenu = bar
    }

    private static func add(_ bar: NSMenu, _ title: String, _ menu: NSMenu) {
        menu.title = title
        let top = NSMenuItem(title: title, action: nil, keyEquivalent: "")
        top.submenu = menu
        bar.addItem(top)
    }

    private static func item(_ title: String, _ action: Selector, _ key: String, _ target: AnyObject) -> NSMenuItem {
        let i = NSMenuItem(title: title, action: action, keyEquivalent: key)
        i.target = target
        return i
    }

    final class Target: NSObject {
        static var shared: Target?
        let openPane: (Pane) -> Void
        let openSettings: () -> Void

        init(openPane: @escaping (Pane) -> Void, settings: @escaping () -> Void) {
            self.openPane = openPane
            self.openSettings = settings
        }

        @objc func pane(_ sender: NSMenuItem) { openPane(Pane.allCases[sender.tag]) }
        @objc func settings() { openSettings() }
    }
}
