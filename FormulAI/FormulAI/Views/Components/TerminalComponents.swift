import SwiftUI
import Charts

// MARK: - Terminal Section (card-like wrapper with dividers)

struct TerminalSection<Content: View>: View {
    let title: String
    var tag: String? = nil
    @ViewBuilder let content: () -> Content

    @Environment(\.terminalColors) private var colors
    @Environment(\.terminalLayout) private var layout

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SectionHeader(title: title, tag: tag)
            content()
                .padding(.horizontal, layout.contentPadding)
                .padding(.bottom, layout.contentPadding)
        }
        .background(colors.bgPanel)
        .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
        .overlay(
            RoundedRectangle(cornerRadius: layout.cardRadius)
                .stroke(colors.border, lineWidth: 0.5)
        )
        .padding(.horizontal, layout.cardPadding)
        .padding(.top, layout.sectionSpacing)
    }
}

// MARK: - Section Header (green left bar + uppercase title)

struct SectionHeader: View {
    let title: String
    var tag: String? = nil

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme

    var body: some View {
        HStack(spacing: 6) {
            Rectangle()
                .fill(theme.accent)
                .frame(width: 2, height: 14)

            Text(title.uppercased())
                .font(.terminalLabel)
                .tracking(1)
                .foregroundStyle(theme.accent)

            if let tag {
                Text(tag)
                    .font(.terminalMicro)
                    .foregroundStyle(colors.textDim)
            }

            Spacer()
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 8)
    }
}

// MARK: - Team Color Bar (4px vertical stripe)

struct TeamColorBar: View {
    let teamId: String
    var width: CGFloat = 4
    var height: CGFloat = 14

    var body: some View {
        Rectangle()
            .fill(F1Team.color(forApiId: teamId))
            .frame(width: width, height: height)
            .clipShape(RoundedRectangle(cornerRadius: max(1, width / 4)))
    }
}

// MARK: - Circuit Badge

struct CircuitBadge: View {
    let type: CircuitType

    @Environment(\.terminalColors) private var colors

    var body: some View {
        let color: Color = switch type {
        case .street: colors.yellow
        case .highSpeed: colors.red
        case .technical: colors.cyan
        case .mixed: colors.textDim
        }

        Text(type.displayName.uppercased())
            .font(.terminalMicro)
            .tracking(0.5)
            .foregroundStyle(color)
            .padding(.horizontal, 5)
            .padding(.vertical, 1)
            .overlay(
                RoundedRectangle(cornerRadius: 3)
                    .stroke(color, lineWidth: 1)
            )
    }
}

// MARK: - Horizontal Bar

struct HorizontalBar: View {
    let value: Double
    let maxValue: Double
    var color: Color? = nil
    var height: CGFloat = 10

    @Environment(\.themeManager) private var theme

    var body: some View {
        GeometryReader { geo in
            let pct = maxValue > 0 ? min(value / maxValue, 1.0) : 0
            RoundedRectangle(cornerRadius: 2)
                .fill((color ?? theme.accent).opacity(0.75))
                .frame(width: geo.size.width * pct)
        }
        .frame(height: height)
        .background(
            RoundedRectangle(cornerRadius: 2)
                .fill(Color.primary.opacity(0.04))
        )
    }
}

// MARK: - Bar Chart Row

struct BarChartRow: View {
    let label: String
    let value: Double
    let maxValue: Double
    var suffix: String = "%"
    var color: Color? = nil

    @Environment(\.terminalColors) private var colors

    var body: some View {
        HStack(spacing: 6) {
            Text(label)
                .font(.terminalCaption)
                .foregroundStyle(colors.text)
                .frame(width: 80, alignment: .trailing)
                .lineLimit(1)

            HorizontalBar(value: value, maxValue: maxValue, color: color)

            Text(String(format: "%.1f%@", value, suffix))
                .font(.terminalLabel)
                .foregroundStyle(colors.textDim)
                .frame(width: 48, alignment: .trailing)
                .monospacedDigit()
        }
    }
}

// MARK: - Sparkline (SwiftCharts)

struct Sparkline: View {
    let data: [Double]
    var color: Color? = nil
    var width: CGFloat = 80
    var height: CGFloat = 24
    var animated: Bool = false

    @Environment(\.themeManager) private var theme

    var body: some View {
        let chart = Chart {
            ForEach(Array(data.enumerated()), id: \.offset) { i, val in
                LineMark(
                    x: .value("X", i),
                    y: .value("Y", val)
                )
                .foregroundStyle(color ?? theme.accent)
                .interpolationMethod(.catmullRom)
            }
        }
        .chartXAxis(.hidden)
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
        .frame(width: width, height: height)

        if animated {
            chart.sparklineDrawAnimation()
        } else {
            chart
        }
    }
}

// MARK: - Position Badge

struct PositionBadge: View {
    let position: Int

    var body: some View {
        Text("\(position)")
            .font(.terminalCaption)
            .fontWeight(position <= 3 ? .bold : .regular)
            .foregroundStyle(Color.position(position))
            .frame(width: 24)
    }
}

// MARK: - Terminal Divider

struct TerminalDivider: View {
    @Environment(\.terminalColors) private var colors

    var body: some View {
        Rectangle()
            .fill(colors.border)
            .frame(height: 1)
    }
}

// MARK: - Zebra Row Background

struct ZebraBackground: ViewModifier {
    let index: Int

    @Environment(\.terminalColors) private var colors

    func body(content: Content) -> some View {
        content
            .background(
                index.isMultiple(of: 2)
                    ? colors.bgStripe
                    : Color.clear
            )
    }
}

extension View {
    func zebraRow(_ index: Int) -> some View {
        modifier(ZebraBackground(index: index))
    }
}

// MARK: - Hero Prediction Card

struct HeroPredictionCard: View {
    let driver: DriverPrediction
    let insight: PredictionInsight

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.terminalLayout) private var layout

    var body: some View {
        VStack(spacing: 12) {
            HStack(spacing: 10) {
                TeamColorBar(teamId: driver.teamId, width: 6, height: 50)

                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Text("PREDICTED WINNER")
                            .font(.terminalMicro)
                            .tracking(1)
                            .foregroundStyle(colors.textDim)
                        ConfidenceBadge(level: driver.confidence)
                    }

                    Text(driver.driverName.uppercased())
                        .font(.system(size: 24, weight: .bold, design: .monospaced))
                        .foregroundStyle(colors.textBright)
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    Text(String(format: "%.1f%%", driver.simWinPct))
                        .font(.system(size: 28, weight: .bold, design: .monospaced))
                        .foregroundStyle(theme.accent)

                    Text(insight.casualDescription)
                        .font(.terminalMicro)
                        .foregroundStyle(colors.textDim)
                }
            }

            Text(insight.whySentence)
                .font(.bodySmall)
                .foregroundStyle(colors.text)
                .lineSpacing(3)
        }
        .padding(layout.cardInnerPadding)
        .background(colors.bgPanel)
        .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
        .overlay(
            RoundedRectangle(cornerRadius: layout.cardRadius)
                .stroke(F1Team.color(forApiId: driver.teamId).opacity(0.3), lineWidth: 1)
        )
    }
}

// MARK: - Podium Forecast (P1/P2/P3 cards)

struct PodiumForecast: View {
    let predictions: [DriverPrediction]

    @Environment(\.terminalColors) private var colors
    @Environment(\.terminalLayout) private var layout

    var body: some View {
        HStack(spacing: 8) {
            ForEach(Array(predictions.prefix(3).enumerated()), id: \.element.id) { index, driver in
                podiumCard(driver, position: index + 1)
                    .appearAnimation(delay: Double(index) * 0.1)
            }
        }
    }

    private func podiumCard(_ driver: DriverPrediction, position: Int) -> some View {
        VStack(spacing: 6) {
            HStack(spacing: 4) {
                Text("P\(position)")
                    .font(.terminalMicro)
                    .fontWeight(.bold)
                    .foregroundStyle(Color.position(position))
                Spacer()
                Text(String(format: "%.0f%%", driver.simPodiumPct))
                    .font(.terminalLabel)
                    .foregroundStyle(colors.textDim)
                    .monospacedDigit()
                Text("podium")
                    .font(.system(size: 7, weight: .medium, design: .default))
                    .foregroundStyle(colors.textDim)
            }

            HStack(spacing: 4) {
                TeamColorBar(teamId: driver.teamId)
                Text(driver.driverName)
                    .font(.terminalCaption)
                    .fontWeight(.semibold)
                    .foregroundStyle(colors.textBright)
                    .lineLimit(1)
                Spacer()
            }

            Text(String(format: "%.1f%% win", driver.simWinPct))
                .font(.terminalMicro)
                .foregroundStyle(colors.textDim)
                .monospacedDigit()
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(layout.cardPadding)
        .background(colors.bgPanel)
        .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
        .overlay(
            RoundedRectangle(cornerRadius: layout.cardRadius)
                .stroke(colors.border, lineWidth: 0.5)
        )
    }
}

// MARK: - Plain Language Label ("1 in 4 chance" alongside percentage)

struct PlainLanguageLabel: View {
    let percentage: Double
    var prefix: String = ""

    @Environment(\.terminalColors) private var colors

    var body: some View {
        HStack(spacing: 6) {
            if !prefix.isEmpty {
                Text(prefix)
                    .font(.terminalCaption)
                    .foregroundStyle(colors.text)
            }

            Text(String(format: "%.1f%%", percentage))
                .font(.terminalCaption)
                .fontWeight(.semibold)
                .foregroundStyle(colors.textBright)
                .monospacedDigit()

            Text("(\(plainLanguage))")
                .font(.terminalMicro)
                .foregroundStyle(colors.textDim)
        }
    }

    private var plainLanguage: String {
        if percentage <= 0 { return "unlikely" }
        if percentage >= 95 { return "near certain" }
        let ratio = Int(round(100.0 / percentage))
        if ratio <= 1 { return "near certain" }
        return "~1 in \(ratio)"
    }
}

// MARK: - Insight Card (compact card for key insights)

struct InsightCard: View {
    let icon: String
    let title: String
    let value: String
    var detail: String? = nil

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.terminalLayout) private var layout

    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(theme.accent)
                .frame(width: 24)

            VStack(alignment: .leading, spacing: 2) {
                Text(title.uppercased())
                    .font(.terminalMicro)
                    .tracking(0.5)
                    .foregroundStyle(colors.textDim)

                Text(value)
                    .font(.terminalCaption)
                    .fontWeight(.semibold)
                    .foregroundStyle(colors.textBright)

                if let detail {
                    Text(detail)
                        .font(.terminalMicro)
                        .foregroundStyle(colors.textDim)
                }
            }

            Spacer()
        }
        .padding(layout.cardPadding)
        .background(colors.bgPanel)
        .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
        .overlay(
            RoundedRectangle(cornerRadius: layout.cardRadius)
                .stroke(colors.border, lineWidth: 0.5)
        )
    }
}

// MARK: - Terminal Header Cell (reusable table header)

struct TerminalHeaderCell: View {
    let text: String
    var width: CGFloat? = nil
    var alignment: Alignment = .leading

    @Environment(\.terminalColors) private var colors

    var body: some View {
        let label = Text(text.uppercased())
            .font(.terminalLabel)
            .tracking(0.5)
            .foregroundStyle(colors.textDim)

        if let width {
            label.frame(width: width, alignment: alignment)
        } else {
            label.frame(maxWidth: .infinity, alignment: alignment)
        }
    }
}

// MARK: - Favorite Indicator (heart or position badge)

struct FavoriteIndicator: View {
    let position: Int
    let teamId: String
    let isFavorite: Bool

    var body: some View {
        if isFavorite {
            Image(systemName: "heart.fill")
                .font(.system(size: 8))
                .foregroundStyle(F1Team.color(forApiId: teamId))
                .frame(width: 24)
        } else {
            PositionBadge(position: position)
        }
    }
}

// MARK: - Weather Condition Item

struct WeatherConditionItem: View {
    let icon: String
    let label: String
    let value: String

    @Environment(\.terminalColors) private var colors

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 16))
                .foregroundStyle(colors.cyan)
            Text(label.uppercased())
                .font(.terminalMicro)
                .tracking(0.5)
                .foregroundStyle(colors.textDim)
            Text(value)
                .font(.terminalCaption)
                .fontWeight(.semibold)
                .foregroundStyle(colors.textBright)
                .monospacedDigit()
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Weather Row (reusable across segments)

struct WeatherRow: View {
    let weather: WeatherForecast

    var body: some View {
        HStack(spacing: 16) {
            WeatherConditionItem(icon: "thermometer.medium", label: "Temp", value: "\(weather.tempC)°C")
            WeatherConditionItem(icon: "cloud.rain", label: "Rain", value: "\(weather.rainPct)%")
            WeatherConditionItem(icon: "wind", label: "Wind", value: "\(weather.windKmh) km/h")
            WeatherConditionItem(icon: "humidity", label: "Humidity", value: "\(weather.humidityPct)%")
        }
    }
}

// MARK: - Session Schedule Row

struct SessionScheduleRow: View {
    let session: String
    let day: String
    let time: String
    var isHighlighted: Bool = false

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme

    var body: some View {
        HStack {
            if isHighlighted {
                Circle()
                    .fill(theme.accent)
                    .frame(width: 6, height: 6)
            }

            Text(session)
                .font(.terminalCaption)
                .fontWeight(isHighlighted ? .bold : .semibold)
                .foregroundStyle(colors.textBright)
                .frame(width: 80, alignment: .leading)

            Text(day)
                .font(.terminalMicro)
                .foregroundStyle(colors.textDim)
                .frame(width: 30)

            Spacer()

            Text(time)
                .font(.terminalCaption)
                .fontWeight(isHighlighted ? .semibold : .regular)
                .foregroundStyle(isHighlighted ? theme.accent : colors.text)
                .monospacedDigit()
        }
    }
}

// MARK: - Terminal Pill (generic bordered badge)

struct TerminalPill: View {
    let text: String
    let color: Color

    var body: some View {
        Text(text)
            .font(.system(size: 8, weight: .bold, design: .monospaced))
            .tracking(0.3)
            .foregroundStyle(color)
            .padding(.horizontal, 5)
            .padding(.vertical, 2)
            .overlay(
                RoundedRectangle(cornerRadius: 3)
                    .stroke(color.opacity(0.5), lineWidth: 0.5)
            )
    }
}

// MARK: - Confidence Badge

struct ConfidenceBadge: View {
    let level: ConfidenceLevel

    @Environment(\.terminalColors) private var colors

    private var badgeColor: Color {
        switch level {
        case .high: colors.green
        case .moderate: colors.text
        case .volatile: colors.yellow
        case .coinFlip: colors.red
        }
    }

    var body: some View {
        TerminalPill(text: level.rawValue, color: badgeColor)
    }
}

// MARK: - Movement Row (arrow + team bar + driver + delta + reason)

struct MovementRow: View {
    let driverName: String
    let teamId: String
    let delta: Double
    let formattedDelta: String
    let reason: String

    @Environment(\.terminalColors) private var colors

    private var deltaColor: Color { delta > 0 ? colors.green : colors.red }

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(deltaColor)
                .frame(width: 16)
                .pulseOnAppear()

            TeamColorBar(teamId: teamId)

            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 4) {
                    Text(driverName)
                        .font(.terminalCaption)
                        .fontWeight(.semibold)
                        .foregroundStyle(colors.textBright)
                    Text(formattedDelta)
                        .font(.terminalMicro)
                        .foregroundStyle(deltaColor)
                        .monospacedDigit()
                }
                Text(reason)
                    .font(.bodyMicro)
                    .foregroundStyle(colors.textDim)
            }

            Spacer()
        }
    }
}

// MARK: - Stat Pair (uppercase label + bold value)

struct StatPair: View {
    let label: String
    let value: String

    @Environment(\.terminalColors) private var colors

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label.uppercased())
                .font(.terminalMicro)
                .tracking(0.5)
                .foregroundStyle(colors.textDim)
            Text(value)
                .font(.terminalCaption)
                .fontWeight(.semibold)
                .foregroundStyle(colors.textBright)
                .monospacedDigit()
        }
    }
}

// MARK: - Confidence Helper

extension DriverPrediction {
    var confidence: ConfidenceLevel {
        if simWinPct >= 20 { return .high }
        if simWinPct >= 10 { return .moderate }
        if simWinPct >= 3 { return .volatile }
        return .coinFlip
    }
}

// MARK: - DNF Color Helper

extension TerminalColors {
    func dnfColor(for percentage: Double, accent: Color) -> Color {
        if percentage >= 50 { return red }
        if percentage >= 30 { return yellow }
        return accent
    }
}
