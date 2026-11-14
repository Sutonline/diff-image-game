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

struct PanelBox: Codable {
    var x: Double
    var y: Double
    var width: Double
    var height: Double
}

struct OverlayConfig: Codable {
    let bounds: WindowBounds
    let scale: Double
    let clickThrough: Bool
    let timeout: Double
    let differenceCount: Int
    let differences: [DifferenceMark]
    var refBox: PanelBox?
    var tgtBox: PanelBox?
    let mode: String?       // "hud" (default) or "calibrate"
    let savePath: String?   // Path to save calibrated viewport JSON
}

enum DragAction {
    case none
    case moveRef
    case resizeRef
    case moveTgt
    case resizeTgt
}

class OverlayCanvasView: NSView {
    var config: OverlayConfig? {
        didSet {
            setupInitialRects()
        }
    }
    override var isFlipped: Bool { return true }

    var isCalibrating: Bool = false
    var refRect: NSRect = .zero
    var tgtRect: NSRect = .zero

    private var activeAction: DragAction = .none
    private var dragStartPoint: NSPoint = .zero
    private var initialDragRect: NSRect = .zero
    private let handleSize: CGFloat = 28.0

    func setupInitialRects() {
        guard let config = config else { return }
        let scale = config.scale > 0 ? config.scale : 1.0
        isCalibrating = (config.mode == "calibrate")

        if let ref = config.refBox {
            refRect = NSRect(x: ref.x / scale, y: ref.y / scale, width: ref.width / scale, height: ref.height / scale)
        } else {
            refRect = NSRect(x: 16.0, y: 170.0, width: bounds.width - 32.0, height: 200.0)
        }

        if let tgt = config.tgtBox {
            tgtRect = NSRect(x: tgt.x / scale, y: tgt.y / scale, width: tgt.width / scale, height: tgt.height / scale)
        } else {
            tgtRect = NSRect(x: 16.0, y: 420.0, width: bounds.width - 32.0, height: 200.0)
        }
        needsDisplay = true
    }

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        guard let config = config else { return }
        let scale = config.scale > 0 ? config.scale : 1.0

        if isCalibrating {
            // Draw Calibrating interactive boxes with handles and guidance
            drawCalibrationBox(
                rect: refRect,
                label: "图 1 (参考图 · 拖动挪位 / 右下角缩放)",
                color: NSColor(red: 0.15, green: 0.70, blue: 0.95, alpha: 0.90) // Cyan
            )
            drawCalibrationBox(
                rect: tgtRect,
                label: "图 2 (比对图 · 拖动挪位 / 右下角缩放)",
                color: NSColor(red: 0.95, green: 0.25, blue: 0.25, alpha: 0.90) // Red
            )
        } else {
            // Standard HUD mode
            let redColor = NSColor(red: 0.95, green: 0.20, blue: 0.20, alpha: 0.85)
            if config.refBox != nil {
                drawPanelBoundary(rect: refRect, label: "图 1 (参考区域)", color: redColor)
            }
            if config.tgtBox != nil {
                drawPanelBoundary(rect: tgtRect, label: "图 2 (比对区域)", color: redColor)
            }

            // Draw difference marks
            for mark in config.differences {
                let r = max(12.0, min(22.0, mark.radius / scale))
                if let rx = mark.refX, let ry = mark.refY {
                    drawCircleBadge(x: rx / scale, y: ry / scale, r: r, id: mark.id)
                }
                if let tx = mark.tgtX, let ty = mark.tgtY {
                    drawCircleBadge(x: tx / scale, y: ty / scale, r: r, id: mark.id)
                }
            }
        }
    }

    private func drawCalibrationBox(rect: NSRect, label: String, color: NSColor) {
        let borderPath = NSBezierPath(roundedRect: rect, xRadius: 4, yRadius: 4)

        // Semi-transparent fill tint
        color.withAlphaComponent(0.08).setFill()
        borderPath.fill()

        // Outer glow
        color.withAlphaComponent(0.35).setStroke()
        borderPath.lineWidth = 4.0
        borderPath.stroke()

        // Main line
        color.setStroke()
        borderPath.lineWidth = 2.0
        borderPath.stroke()

        // Corner badge with size readout
        let sizeInfo = "\(label) [\(Int(rect.width))×\(Int(rect.height)) pt]"
        let font = NSFont.boldSystemFont(ofSize: 10)
        let textAttrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white
        ]
        let textSize = (sizeInfo as NSString).size(withAttributes: textAttrs)
        let pillW = textSize.width + 14.0
        let pillH = 18.0
        let pillRect = NSRect(x: rect.minX + 4.0, y: rect.minY + 4.0, width: pillW, height: pillH)

        let pillPath = NSBezierPath(roundedRect: pillRect, xRadius: 4, yRadius: 4)
        color.withAlphaComponent(0.95).setFill()
        pillPath.fill()

        let textPoint = NSPoint(
            x: pillRect.origin.x + 7.0,
            y: pillRect.origin.y + (pillH - textSize.height) / 2.0 - 0.5
        )
        (sizeInfo as NSString).draw(at: textPoint, withAttributes: textAttrs)

        // Bottom-Right resize grip handle
        let handleRect = NSRect(x: rect.maxX - handleSize, y: rect.maxY - handleSize, width: handleSize, height: handleSize)
        let handlePath = NSBezierPath(roundedRect: handleRect.insetBy(dx: 2, dy: 2), xRadius: 4, yRadius: 4)
        color.withAlphaComponent(0.95).setFill()
        handlePath.fill()

        let gripAttrs: [NSAttributedString.Key: Any] = [
            .font: NSFont.boldSystemFont(ofSize: 13),
            .foregroundColor: NSColor.white
        ]
        let gripIcon = "⇲" as NSString
        let gripSize = gripIcon.size(withAttributes: gripAttrs)
        let gripPoint = NSPoint(
            x: handleRect.origin.x + (handleSize - gripSize.width) / 2.0,
            y: handleRect.origin.y + (handleSize - gripSize.height) / 2.0
        )
        gripIcon.draw(at: gripPoint, withAttributes: gripAttrs)
    }

    private func drawPanelBoundary(rect: NSRect, label: String, color: NSColor) {
        let borderPath = NSBezierPath(roundedRect: rect, xRadius: 4, yRadius: 4)

        color.withAlphaComponent(0.04).setFill()
        borderPath.fill()

        color.withAlphaComponent(0.25).setStroke()
        borderPath.lineWidth = 3.5
        borderPath.stroke()

        color.setStroke()
        borderPath.lineWidth = 1.8
        borderPath.stroke()

        let font = NSFont.boldSystemFont(ofSize: 10)
        let textAttrs: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: NSColor.white
        ]
        let textSize = (label as NSString).size(withAttributes: textAttrs)
        let pillW = textSize.width + 12.0
        let pillH = 17.0
        let pillRect = NSRect(x: rect.minX + 6.0, y: rect.minY + 4.0, width: pillW, height: pillH)

        let pillPath = NSBezierPath(roundedRect: pillRect, xRadius: 4, yRadius: 4)
        color.withAlphaComponent(0.90).setFill()
        pillPath.fill()

        let textPoint = NSPoint(
            x: pillRect.origin.x + 6.0,
            y: pillRect.origin.y + (pillH - textSize.height) / 2.0 - 0.5
        )
        (label as NSString).draw(at: textPoint, withAttributes: textAttrs)
    }

    private func drawCircleBadge(x: Double, y: Double, r: Double, id: Int) {
        let rect = NSRect(x: x - r, y: y - r, width: 2 * r, height: 2 * r)
        let circlePath = NSBezierPath(ovalIn: rect)

        NSColor(red: 1.0, green: 0.2, blue: 0.2, alpha: 0.15).setFill()
        circlePath.fill()

        let glowPath = NSBezierPath(ovalIn: rect.insetBy(dx: -1.5, dy: -1.5))
        NSColor(red: 1.0, green: 1.0, blue: 1.0, alpha: 0.6).setStroke()
        glowPath.lineWidth = 1.0
        glowPath.stroke()

        NSColor(red: 0.95, green: 0.15, blue: 0.15, alpha: 0.95).setStroke()
        circlePath.lineWidth = 2.5
        circlePath.stroke()

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

    // MARK: - Interactive Mouse Event Handling for Calibration
    override func mouseDown(with event: NSEvent) {
        guard isCalibrating else { return }
        let pt = convert(event.locationInWindow, from: nil)

        let refResizeRect = NSRect(x: refRect.maxX - handleSize, y: refRect.maxY - handleSize, width: handleSize, height: handleSize)
        let tgtResizeRect = NSRect(x: tgtRect.maxX - handleSize, y: tgtRect.maxY - handleSize, width: handleSize, height: handleSize)

        if refResizeRect.contains(pt) {
            activeAction = .resizeRef
            dragStartPoint = pt
            initialDragRect = refRect
        } else if tgtResizeRect.contains(pt) {
            activeAction = .resizeTgt
            dragStartPoint = pt
            initialDragRect = tgtRect
        } else if refRect.contains(pt) {
            activeAction = .moveRef
            dragStartPoint = pt
            initialDragRect = refRect
        } else if tgtRect.contains(pt) {
            activeAction = .moveTgt
            dragStartPoint = pt
            initialDragRect = tgtRect
        } else {
            activeAction = .none
        }
    }

    override func mouseDragged(with event: NSEvent) {
        guard isCalibrating, activeAction != .none else { return }
        let pt = convert(event.locationInWindow, from: nil)
        let dx = pt.x - dragStartPoint.x
        let dy = pt.y - dragStartPoint.y

        switch activeAction {
        case .moveRef:
            refRect.origin.x = max(0, min(bounds.width - refRect.width, initialDragRect.origin.x + dx))
            refRect.origin.y = max(0, min(bounds.height - refRect.height, initialDragRect.origin.y + dy))
            needsDisplay = true

        case .moveTgt:
            tgtRect.origin.x = max(0, min(bounds.width - tgtRect.width, initialDragRect.origin.x + dx))
            tgtRect.origin.y = max(0, min(bounds.height - tgtRect.height, initialDragRect.origin.y + dy))
            needsDisplay = true

        case .resizeRef:
            let newW = max(60, min(bounds.width - refRect.origin.x, initialDragRect.width + dx))
            let newH = max(60, min(bounds.height - refRect.origin.y, initialDragRect.height + dy))
            refRect.size.width = newW
            refRect.size.height = newH
            needsDisplay = true

        case .resizeTgt:
            let newW = max(60, min(bounds.width - tgtRect.origin.x, initialDragRect.width + dx))
            let newH = max(60, min(bounds.height - tgtRect.origin.y, initialDragRect.height + dy))
            tgtRect.size.width = newW
            tgtRect.size.height = newH
            needsDisplay = true

        case .none:
            break
        }
    }

    override func mouseUp(with event: NSEvent) {
        activeAction = .none
    }

    func saveCalibrationAndExit() {
        guard let savePath = config?.savePath else {
            NSApp.terminate(nil)
            return
        }
        let scale = config?.scale ?? 1.0
        let exportData: [String: Any] = [
            "scale": scale,
            "refBox": [
                "x": round(Double(refRect.origin.x * scale) * 10) / 10,
                "y": round(Double(refRect.origin.y * scale) * 10) / 10,
                "width": round(Double(refRect.size.width * scale) * 10) / 10,
                "height": round(Double(refRect.size.height * scale) * 10) / 10
            ],
            "tgtBox": [
                "x": round(Double(tgtRect.origin.x * scale) * 10) / 10,
                "y": round(Double(tgtRect.origin.y * scale) * 10) / 10,
                "width": round(Double(tgtRect.size.width * scale) * 10) / 10,
                "height": round(Double(tgtRect.size.height * scale) * 10) / 10
            ]
        ]
        do {
            let jsonData = try JSONSerialization.data(withJSONObject: exportData, options: .prettyPrinted)
            try jsonData.write(to: URL(fileURLWithPath: savePath))
            print("CALIBRATION_SAVED:\(savePath)")
        } catch {
            fputs("Failed to write calibration: \(error)\n", stderr)
        }
        NSApp.terminate(nil)
    }
}

class TopPillView: NSView {
    var onClose: (() -> Void)?
    var onSave: (() -> Void)?
    var isCalibrating: Bool = false
    var titleText: String = ""

    override func draw(_ dirtyRect: NSRect) {
        super.draw(dirtyRect)
        let pillPath = NSBezierPath(roundedRect: bounds, xRadius: bounds.height / 2.0, yRadius: bounds.height / 2.0)
        NSColor(white: 0.12, alpha: 0.92).setFill()
        pillPath.fill()
        NSColor(white: 0.45, alpha: 0.85).setStroke()
        pillPath.lineWidth = 1.0
        pillPath.stroke()

        if isCalibrating {
            // Calibration prompt & Save button
            let title = "⚙️ 拖拽红框微调位置与大小 | [ 回车键保存 ] [ ESC取消 ]" as NSString
            let textAttrs: [NSAttributedString.Key: Any] = [
                .font: NSFont.boldSystemFont(ofSize: 11),
                .foregroundColor: NSColor(red: 0.3, green: 0.95, blue: 0.4, alpha: 1.0)
            ]
            let textSize = title.size(withAttributes: textAttrs)
            let textPos = NSPoint(x: 14.0, y: (bounds.height - textSize.height) / 2.0)
            title.draw(at: textPos, withAttributes: textAttrs)
        } else {
            let textAttrs: [NSAttributedString.Key: Any] = [
                .font: NSFont.systemFont(ofSize: 11, weight: .medium),
                .foregroundColor: NSColor.white
            ]
            let title = "🎯 \(titleText) (点击穿透已开启 · ESC关闭)" as NSString
            let textSize = title.size(withAttributes: textAttrs)
            let textPos = NSPoint(x: 14.0, y: (bounds.height - textSize.height) / 2.0)
            title.draw(at: textPos, withAttributes: textAttrs)
        }
    }

    override func mouseDown(with event: NSEvent) {
        if isCalibrating {
            onSave?()
        } else {
            onClose?()
        }
    }
}

class AppDelegate: NSObject, NSApplicationDelegate {
    var canvasWindow: NSWindow!
    var pillWindow: NSWindow?
    var canvasView: OverlayCanvasView!
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
        let isCalibrating = (config.mode == "calibrate")

        let cocoaY = primaryH - (bounds.y + bounds.height)
        let windowFrame = NSRect(x: bounds.x, y: cocoaY, width: bounds.width, height: bounds.height)

        canvasWindow = NSWindow(
            contentRect: windowFrame,
            styleMask: [.borderless],
            backing: .buffered,
            defer: false
        )
        canvasWindow.level = isCalibrating ? .modalPanel : .floating
        canvasWindow.isOpaque = false
        canvasWindow.backgroundColor = .clear
        canvasWindow.hasShadow = false
        canvasWindow.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]

        // In calibrate mode, window MUST receive mouse events for dragging/resizing
        canvasWindow.ignoresMouseEvents = isCalibrating ? false : config.clickThrough

        canvasView = OverlayCanvasView(frame: NSRect(x: 0, y: 0, width: bounds.width, height: bounds.height))
        canvasView.config = config
        canvasWindow.contentView = canvasView
        canvasWindow.makeKeyAndOrderFront(nil)

        // Top Pill Toolbar
        let pillW = isCalibrating ? min(bounds.width - 20.0, 360.0) : min(bounds.width - 20.0, 310.0)
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
        pillWin.level = .screenSaver
        pillWin.isOpaque = false
        pillWin.backgroundColor = .clear
        pillWin.hasShadow = true
        pillWin.ignoresMouseEvents = false

        let pillView = TopPillView(frame: NSRect(x: 0, y: 0, width: pillW, height: pillH))
        pillView.isCalibrating = isCalibrating
        pillView.titleText = "找到 \(config.differenceCount) 处差异"
        pillView.onClose = {
            self.dismiss()
        }
        pillView.onSave = {
            self.canvasView.saveCalibrationAndExit()
        }
        pillWin.contentView = pillView
        pillWin.makeKeyAndOrderFront(nil)
        self.pillWindow = pillWin

        // Monitor Local Keys: Enter (36) saves calibration; ESC (53) dismisses
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            if isCalibrating && event.keyCode == 36 { // Return / Enter
                self.canvasView.saveCalibrationAndExit()
                return nil
            } else if event.keyCode == 53 { // ESC
                self.dismiss()
                return nil
            }
            return event
        }

        // Auto dismiss timer only in HUD mode
        if !isCalibrating {
            let timeout = config.timeout > 0 ? config.timeout : 15.0
            DispatchQueue.main.asyncAfter(deadline: .now() + timeout) {
                self.dismiss()
            }
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

// Main entry
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
