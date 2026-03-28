import SwiftUI

// MARK: - Team Identity (Premium Feature)

enum F1Team: String, CaseIterable, Identifiable {
    case mercedes, ferrari, redBull, mclaren, alpine
    case astonMartin, williams, haas, rb, audi, cadillac

    var id: String { rawValue }

    var displayName: String {
        switch self {
        case .mercedes: "Mercedes"
        case .ferrari: "Ferrari"
        case .redBull: "Red Bull"
        case .mclaren: "McLaren"
        case .alpine: "Alpine"
        case .astonMartin: "Aston Martin"
        case .williams: "Williams"
        case .haas: "Haas"
        case .rb: "RB"
        case .audi: "Audi"
        case .cadillac: "Cadillac"
        }
    }

    var color: Color {
        switch self {
        case .mercedes:    Color(hex: 0x00D2BE)
        case .ferrari:     Color(hex: 0xDC0000)
        case .redBull:     Color(hex: 0x3671C6)
        case .mclaren:     Color(hex: 0xFF8700)
        case .alpine:      Color(hex: 0x0090FF)
        case .astonMartin: Color(hex: 0x006F62)
        case .williams:    Color(hex: 0x005AFF)
        case .haas:        Color(hex: 0xB6BABD)
        case .rb:          Color(hex: 0x6692FF)
        case .audi:        Color(hex: 0x00E701)
        case .cadillac:    Color(hex: 0xC0C0C0)
        }
    }

    var apiId: String {
        switch self {
        case .redBull: "red_bull"
        case .astonMartin: "aston_martin"
        default: rawValue
        }
    }

    private static let apiIdLookup: [String: F1Team] = {
        Dictionary(uniqueKeysWithValues: allCases.map { ($0.apiId, $0) })
    }()

    static func from(apiId: String) -> F1Team? {
        apiIdLookup[apiId]
    }

    static func color(forApiId apiId: String) -> Color {
        apiIdLookup[apiId]?.color ?? Color.gray
    }
}

// MARK: - Terminal Color Tokens

struct TerminalColors {
    let bg: Color
    let bgPanel: Color
    let bgStripe: Color
    let border: Color
    let text: Color
    let textDim: Color
    let textBright: Color
    let cyan: Color
    let yellow: Color
    let red: Color
    let green: Color

    static let dark = TerminalColors(
        bg:         Color(hex: 0x000000),
        bgPanel:    Color(hex: 0x050505),
        bgStripe:   Color(hex: 0x0A0A0A),
        border:     Color(hex: 0x1A1A1A),
        text:       Color(hex: 0xCCCCCC),
        textDim:    Color(hex: 0x555555),
        textBright: Color(hex: 0xFFFFFF),
        cyan:       Color(hex: 0x00D4FF),
        yellow:     Color(hex: 0xFFCC00),
        red:        Color(hex: 0xFF3355),
        green:      Color(hex: 0x00CC44)
    )

    static let light = TerminalColors(
        bg:         Color(hex: 0xF5F0E8),
        bgPanel:    Color(hex: 0xEDE8DF),
        bgStripe:   Color(hex: 0xE8E3DA),
        border:     Color(hex: 0xD4CFC6),
        text:       Color(hex: 0x2C2820),
        textDim:    Color(hex: 0x8A8478),
        textBright: Color(hex: 0x1A1610),
        cyan:       Color(hex: 0x0066AA),
        yellow:     Color(hex: 0x996600),
        red:        Color(hex: 0xCC0022),
        green:      Color(hex: 0x006622)
    )
}

// MARK: - Theme Environment

enum AppearanceMode: String, CaseIterable {
    case system, dark, light

    var label: String {
        switch self {
        case .system: "System"
        case .dark: "Dark"
        case .light: "Light"
        }
    }

    var colorScheme: ColorScheme? {
        switch self {
        case .system: nil
        case .dark: .dark
        case .light: .light
        }
    }
}

@Observable
final class ThemeManager {
    var selectedTeam: F1Team? = nil
    var isPremium: Bool = false

    var appearanceMode: AppearanceMode {
        didSet {
            UserDefaults.standard.set(appearanceMode.rawValue, forKey: "appearanceMode")
        }
    }

    init() {
        let stored = UserDefaults.standard.string(forKey: "appearanceMode") ?? "system"
        self.appearanceMode = AppearanceMode(rawValue: stored) ?? .system
    }

    var accent: Color {
        if isPremium, let team = selectedTeam {
            return team.color
        }
        return Color(hex: 0x50C878) // phosphor green
    }

    func colors(for scheme: ColorScheme) -> TerminalColors {
        scheme == .dark ? .dark : .light
    }
}

private struct ThemeManagerKey: EnvironmentKey {
    static let defaultValue = ThemeManager()
}

private struct TerminalColorsKey: EnvironmentKey {
    static let defaultValue = TerminalColors.dark
}

extension EnvironmentValues {
    var themeManager: ThemeManager {
        get { self[ThemeManagerKey.self] }
        set { self[ThemeManagerKey.self] = newValue }
    }

    var terminalColors: TerminalColors {
        get { self[TerminalColorsKey.self] }
        set { self[TerminalColorsKey.self] = newValue }
    }
}

// MARK: - Adaptive Layout

struct TerminalLayout: Equatable, Sendable {
    let isCompact: Bool
    let isWide: Bool
    let screenWidth: CGFloat
    let cardRadius: CGFloat = 12

    var cardPadding: CGFloat { isWide ? 16 : (isCompact ? 6 : 10) }
    var cardInnerPadding: CGFloat { isWide ? 18 : (isCompact ? 10 : 14) }
    var sectionSpacing: CGFloat { isWide ? 10 : (isCompact ? 6 : 8) }
    var contentPadding: CGFloat { isWide ? 16 : (isCompact ? 10 : 12) }

    init(screenWidth: CGFloat) {
        self.screenWidth = screenWidth
        self.isCompact = screenWidth < 380
        self.isWide = screenWidth >= 700
    }

    private init(isCompact: Bool, isWide: Bool) {
        self.isCompact = isCompact
        self.isWide = isWide
        self.screenWidth = isWide ? 1024 : (isCompact ? 370 : 393)
    }

    static let `default` = TerminalLayout(isCompact: false, isWide: false)
}

private struct TerminalLayoutKey: EnvironmentKey {
    static let defaultValue = TerminalLayout.default
}

extension EnvironmentValues {
    var terminalLayout: TerminalLayout {
        get { self[TerminalLayoutKey.self] }
        set { self[TerminalLayoutKey.self] = newValue }
    }
}

// MARK: - Terminal Fonts
// Monospace for data, labels, headers. SF Pro (default) for body/descriptions.

extension Font {
    // Monospace — data values, section headers, labels
    static let terminalTitle   = Font.system(size: 13, weight: .bold, design: .monospaced)
    static let terminalCaption = Font.system(size: 11, weight: .regular, design: .monospaced)
    static let terminalLabel   = Font.system(size: 10, weight: .medium, design: .monospaced)
    static let terminalMicro   = Font.system(size: 9, weight: .semibold, design: .monospaced)

    // SF Pro — body text, descriptions, insights, news
    static let bodySmall   = Font.system(size: 12, weight: .regular, design: .default)
    static let bodyCaption = Font.system(size: 11, weight: .regular, design: .default)
    static let bodyMicro   = Font.system(size: 10, weight: .medium, design: .default)
}

// MARK: - Position Colors

extension Color {
    static let p1 = Color(hex: 0xFFD700) // gold
    static let p2 = Color(hex: 0xC0C0C0) // silver
    static let p3 = Color(hex: 0xCD7F32) // bronze

    static func position(_ pos: Int) -> Color {
        switch pos {
        case 1: .p1
        case 2: .p2
        case 3: .p3
        default: .secondary
        }
    }
}

// MARK: - Color Hex Init

extension Color {
    init(hex: UInt, opacity: Double = 1.0) {
        self.init(
            .sRGB,
            red:   Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue:  Double(hex & 0xFF) / 255,
            opacity: opacity
        )
    }
}
