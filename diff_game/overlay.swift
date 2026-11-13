import Cocoa
import Foundation

struct DifferenceMark: Codable {
    let id: Int
    let refX: Double?
    let refY: Double?
    let tgtX: Double?
    let tgtY: Double?
    let radius: Double
}

struct WindowBounds: Codable {
    let x: Double
    let y: Double
    let width: Double
    let height: Double
}

struct OverlayConfig: Codable {
    let bounds: WindowBounds
    let scale: Double
    let clickThrough: Bool
    let timeout: Double
    let differenceCount: Int
    let differences: [DifferenceMark]
}

class OverlayCanvasView: NSView {
    var config: OverlayConfig?
    override var isFlipped: Bool { return true }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let config = config else { return }

        let scale = config.scale > 0 ? config.scale : 1.0

        for mark in config.differences {
            let r = (mark.radius / scale) + 6.0

            // Draw on reference panel if available
            if let rx = mark.refX, let ry = mark.refY {
                drawCircleBadge(x: rx / scale, y: ry / scale, r: r, id: mark.id)
            }

            // Draw on target panel if available
            if let tx = mark.tgtX, let ty = mark.tgtY {
                drawCircleBadge(x: tx / scale, y: ty / scale, r: r, id: mark.id)
            }
        }
    }

    private func drawCircleBadge(x: Double, y: Double, r: Double, id: Int) {
        let rect = NSRect(x: x - r, y: y - r, width: 2 * r, height: 2 * r)
        let circlePath = NSBezierPath(ovalIn: rect)

        // Subtle fill highlight
        NSColor(red: 1.0, green: 0.2, blue: 0.2, alpha: 0.15).setFill()
        circlePath.fill()

        // Outer glow stroke
        let glowPath = NSBezierPath(ovalIn: rect.insetBy(dx: -1.5, dy: -1.5))
        NSColor(red: 1.0, green: 1.0, blue: 1.0, alpha: 0.6).setStroke()
        glowPath.lineWidth = 1.0
        glowPath.stroke()

        // Main red ring
        NSColor(red: 0.95, green: 0.15, blue: 0.15, alpha: 0.95).setStroke()
        circlePath.lineWidth = 2.5
        circlePath.stroke()

        // Badge pill
        let badgeText = "\(id)"
        let font = NSFont.boldSystemFont(ofSize: 11)
        let textAttrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white
        ]
        let textSize = (badgeText as NSString).size(withAttributes: textAttrs)
        let badgeW = max(18.0, textSize.width + 8.0)
        let badgeH = 16.0
        let badgeRect = NSRect(x: x - (badgeW / 2.0), y: y - r - (badgeH / 2.0), width: badgeW, height: badgeH)

        let badgePath = NSBezierPath(roundedRect: badgeRect, xRadius: 8, yRadius: 8)
        NSColor(red: 0.9, green: 0.1, blue: 0.1, alpha: 0.95).setFill()
        badgePath.fill()
        NSColor.white.setStroke()
        badgePath.lineWidth = 1.0
        badgePath.stroke()

        let textPoint = NSPoint(
            x: badgeRect.origin.x + (badgeW - textSize.width) / 2.0,
            y: badgeRect.origin.y + (badgeH - textSize.height) / 2.0 - 0.5
        )
        (badgeText as NSString).draw(at: textPoint, withAttributes: textAttrs)
    }
}

class TopPillView: NSView {
    var onClose: (() -> Void)?
    var titleText: String = ""

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        let pillPath = NSBezierPath(roundedRect: bounds, xRadius: bounds.height / 2.0, yRadius: bounds.height / 2.0)
        NSColor(white: 0.1, alpha: 0.88).setFill()
        pillPath.fill()
        NSColor(white: 0.4, alpha: 0.8).setStroke()
        pillPath.lineWidth = 1.0
        pillPath.stroke()

        let textAttrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.systemFont(ofSize: 11, weight: .medium),
            .foregroundColor: NSColor.white
        ]
        let title = "🎯 \(titleText) (点击穿透已开启 · ESC关闭)" as NSString
        let textSize = title.size(withAttributes: textAttrs)
        let textPos = NSPoint(x: 14.0, y: (bounds.height - textSize.height) / 2.0)
        title.draw(at: textPos, withAttributes: textAttrs)
    }

    override func mouseDown(with event: NSEvent) {
        onClose?()
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var canvasWindow: NSWindow!
    var pillWindow: NSWindow?
    let config: OverlayConfig

    init(config: OverlayConfig) {
        self.config = config
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        guard let primaryScreen = NSScreen.screens.first else {
            exit(1)
        }

        let primaryH = primaryScreen.frame.height
        let bounds = config.bounds

        // Cocoa coordinates: Y=0 at bottom of primary screen
        let cocoaY = primaryH - (bounds.y + bounds.height)
        let windowFrame = NSRect(x: bounds.x, y: cocoaY, width: bounds.width, height: bounds.height)

        // 1. Transparent Canvas Window (Floating directly above game window)
        canvasWindow = NSWindow(
            contentRect: windowFrame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        canvasWindow.level = .floating
        canvasWindow.isOpaque = false
        canvasWindow.backgroundColor = .clear
        canvasWindow.hasShadow = false
        canvasWindow.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        // Enable click-through so user can click directly on the game underneath!
        canvasWindow.ignoresMouseEvents = config.clickThrough

        let canvasView = OverlayCanvasView(frame: NSRect(x: 0, y: 0, width: bounds.width, height: bounds.height))
        canvasView.config = config
        canvasWindow.contentView = canvasView
        canvasWindow.makeKeyAndOrderFront(nil)

        // 2. Top Pill Toolbar (Clickable, displays diff count & close hint)
        let pillW = min(bounds.width - 20.0, 310.0)
        let pillH = 26.0
        let pillFrame = NSRect(
            x: bounds.x + (bounds.width - pillW) / 2.0,
            y: cocoaY + bounds.height - pillH - 6.0,
            width: pillW,
            height: pillH
        )

        let pillWin = NSWindow(
            contentRect: pillFrame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        pillWin.level = .modalPanel
        pillWin.isOpaque = false
        pillWin.backgroundColor = .clear
        pillWin.hasShadow = true
        pillWin.ignoresMouseEvents = false

        let pillView = TopPillView(frame: NSRect(x: 0, y: 0, width: pillW, height: pillH))
        pillView.titleText = "找到 \(config.differenceCount) 处差异"
        pillView.onClose = {
            self.dismiss()
        }
        pillWin.contentView = pillView
        pillWin.makeKeyAndOrderFront(nil)
        self.pillWindow = pillWin

        // Monitor Global / Local Key for ESC
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if event.keyCode == 53 { // ESC key
                self.dismiss()
                return nil
            }
            return event
        }

        // Auto dismiss timer
        let timeout = config.timeout > 0 ? config.timeout : 15.0
        DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
            self.dismiss()
        }
    }

    func dismiss() {
        NSAnimationContext.runAnimationGroup({ context in
            context.duration = 0.25
            self.canvasWindow.animator().alphaValue = 0.0
            self.pillWindow?.animator().alphaValue = 0.0
        }, completionHandler: {
            NSApp.terminate(nil)
        })
    }
}

// Main execution
let args = CommandLine.arguments
if args.count < 2 {
    fputs("Usage: overlay <config.json>\n", stderr)
    exit(1)
}

let configPath = args[1]
do {
    let data = try Data(contentsOf: URL(fileURLWithPath: configPath))
    let config = try JSONDecoder().decode(OverlayConfig.self, from: data)

    let app = NSApplication.shared
    let delegate = AppDelegate(config: config)
    app.delegate = delegate
    app.setActivationPolicy(.accessory)
    app.run()
} catch {
    fputs("Error loading config: \(error)\n", stderr)
    exit(1)
}
