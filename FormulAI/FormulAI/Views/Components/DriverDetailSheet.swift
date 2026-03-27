import SwiftUI

struct DriverDetailSheet: View {
    let driver: DriverPrediction

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.dataStore) private var store

    var body: some View {
        let eloHistory = store.eloRatings.first(where: { $0.id == driver.id })?.history ?? []

        VStack(spacing: 0) {
            HStack(spacing: 8) {
                TeamColorBar(teamId: driver.teamId)
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(driver.driverName)
                            .font(.terminalTitle)
                            .foregroundStyle(colors.textBright)
                        ConfidenceBadge(level: driver.confidence)
                    }
                    Text(driver.teamName)
                        .font(.terminalCaption)
                        .foregroundStyle(colors.textDim)
                }
                Spacer()
                if !eloHistory.isEmpty {
                    VStack(alignment: .trailing, spacing: 2) {
                        Sparkline(data: eloHistory, width: 64, height: 20)
                        Text("ELO TREND")
                            .font(.system(size: 7, weight: .medium, design: .monospaced))
                            .foregroundStyle(colors.textDim)
                    }
                }
            }
            .padding(16)

            TerminalDivider()

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
                detailStat("Win%", String(format: "%.1f%%", driver.simWinPct))
                detailStat("Podium%", String(format: "%.1f%%", driver.simPodiumPct))
                detailStat("Points%", String(format: "%.1f%%", driver.simPointsPct))
                detailStat("E[Points]", String(format: "%.1f", driver.simExpectedPoints))
                detailStat("DNF Risk", String(format: "%.1f%%", driver.simDnfPct))
                detailStat("Pred. Pos", String(format: "%.1f", driver.predictedPosition))
                detailStat("Median", "\(driver.simMedianPosition)")
                detailStat("Range", "\(driver.simPosition25)–\(driver.simPosition75)")
                if let grid = driver.grid {
                    detailStat("Grid", "\(grid)")
                }
            }
            .padding(16)

            if let lo = driver.probWinnerLo, let hi = driver.probWinnerHi {
                TerminalDivider()
                HStack {
                    Text("WIN CONFIDENCE")
                        .font(.terminalLabel)
                        .tracking(0.5)
                        .foregroundStyle(colors.textDim)
                    Spacer()
                    PlainLanguageLabel(percentage: lo * 100)
                    Text("–")
                        .font(.terminalCaption)
                        .foregroundStyle(colors.textDim)
                    Text(String(format: "%.0f%%", hi * 100))
                        .font(.terminalCaption)
                        .fontWeight(.semibold)
                        .foregroundStyle(colors.textBright)
                }
                .padding(16)
            }

            TerminalDivider()

            Button {} label: {
                HStack(spacing: 8) {
                    Image(systemName: "arrow.left.arrow.right")
                        .font(.system(size: 12))
                    Text("Compare with teammate")
                        .font(.bodyMicro)
                }
                .foregroundStyle(theme.accent)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 12)
            }
            .buttonStyle(.plain)

            Spacer()
        }
        .background(colors.bg)
    }

    private func detailStat(_ label: String, _ value: String) -> some View {
        VStack(spacing: 3) {
            Text(label.uppercased())
                .font(.terminalMicro)
                .tracking(0.5)
                .foregroundStyle(colors.textDim)
            Text(value)
                .font(.system(size: 16, weight: .bold, design: .monospaced))
                .foregroundStyle(colors.textBright)
                .monospacedDigit()
        }
    }
}
