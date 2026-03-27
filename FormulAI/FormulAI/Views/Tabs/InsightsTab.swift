import SwiftUI

struct InsightsTab: View {
    let weekend: RaceWeekend

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.favorites) private var favorites
    @Environment(\.terminalLayout) private var layout

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                eloRankings
                teammateH2H
                probabilityChart(title: "Win Probability", tag: "top 8", data: MockData.topByWin, keyPath: \.simWinPct)
                probabilityChart(title: "Podium Probability", tag: "top 8", data: MockData.topByPodium, keyPath: \.simPodiumPct, color: colors.cyan)
                modelScorecard
                comingSoon
            }
            .padding(.bottom, 16)
        }
        .background(colors.bg)
    }

    // MARK: - ELO Power Rankings

    private var eloRankings: some View {
        TerminalSection(title: "Power Rankings", tag: "current form estimate") {
            VStack(spacing: 0) {
                Text("Higher rating = stronger recent form across qualifying, race pace, and consistency.")
                    .font(.bodyMicro)
                    .foregroundStyle(colors.textDim)
                    .padding(.bottom, 10)

                ForEach(Array(MockData.eloRankings.enumerated()), id: \.element.id) { index, driver in
                    eloCard(driver, isFavorite: driver.id == favorites.favoriteDriverId)
                        .padding(.vertical, 6)
                    if index < MockData.eloRankings.count - 1 {
                        TerminalDivider()
                    }
                }
            }
        }
    }

    private func eloTier(_ elo: Double) -> (label: String, color: Color) {
        switch elo {
        case 2060...: return ("ELITE", theme.accent)
        case 2040..<2060: return ("STRONG", colors.cyan)
        case 2020..<2040: return ("SOLID", colors.text)
        default: return ("MIDFIELD", colors.textDim)
        }
    }

    @ViewBuilder
    private func eloCard(_ driver: DriverELO, isFavorite: Bool) -> some View {
        let isHighlighted = isFavorite || driver.rank <= 3
        let tier = eloTier(driver.eloOverall)
        let delta = driver.movementDelta
        let reason = driver.movementReason.isEmpty
            ? (delta > 0 ? "Trending upward" : "Recent form dip")
            : driver.movementReason

        VStack(spacing: 6) {
            HStack(spacing: 6) {
                FavoriteIndicator(position: driver.rank, teamId: driver.teamId, isFavorite: isFavorite)
                TeamColorBar(teamId: driver.teamId)
                Text(driver.driverName)
                    .font(.terminalCaption)
                    .fontWeight(isHighlighted ? .semibold : .regular)
                    .foregroundStyle(isHighlighted ? colors.textBright : colors.text)
                Spacer()

                TerminalPill(text: tier.label, color: tier.color)

                Text("\(Int(driver.eloOverall))")
                    .font(.system(size: 16, weight: .bold, design: .monospaced))
                    .foregroundStyle(colors.textBright)
                    .monospacedDigit()
            }

            HStack(spacing: 0) {
                eloMini("QUALI", Int(driver.eloQualifying))
                eloMini("CIRCUIT", Int(driver.eloCircuitType))
                eloMini("TEAM", Int(driver.eloConstructor))
                Spacer()
                Sparkline(data: driver.history, width: 80, height: 24)
            }

            if delta != 0 {
                HStack(spacing: 4) {
                    Image(systemName: delta > 0 ? "arrow.up.right" : "arrow.down.right")
                        .font(.system(size: 9))
                        .foregroundStyle(delta > 0 ? colors.green : colors.red)
                    Text("\(delta > 0 ? "+" : "")\(delta)")
                        .font(.terminalMicro)
                        .foregroundStyle(delta > 0 ? colors.green : colors.red)
                        .monospacedDigit()
                    Text(reason)
                        .font(.bodyMicro)
                        .foregroundStyle(colors.textDim)
                    Spacer()
                }
            }
        }
    }

    private func eloMini(_ label: String, _ value: Int) -> some View {
        VStack(alignment: .leading, spacing: 1) {
            Text(label)
                .font(.terminalMicro)
                .tracking(0.5)
                .foregroundStyle(colors.textDim)
            Text("\(value)")
                .font(.terminalCaption)
                .foregroundStyle(colors.text)
                .monospacedDigit()
        }
        .frame(width: 64, alignment: .leading)
    }

    // MARK: - Teammate H2H

    private var teammateH2H: some View {
        TerminalSection(title: "Teammate Battles", tag: "head-to-head after R\(weekend.round > 1 ? weekend.round - 1 : 1)") {
            VStack(spacing: 8) {
                ForEach(MockData.teammateH2H) { h2h in
                    h2hRow(h2h)
                }
            }
        }
    }

    private func h2hRow(_ h2h: TeammateH2H) -> some View {
        VStack(spacing: 6) {
            HStack {
                TeamColorBar(teamId: h2h.teamId)
                Text(h2h.teamName.uppercased())
                    .font(.terminalMicro)
                    .tracking(0.5)
                    .foregroundStyle(colors.textDim)
                Spacer()
            }

            HStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(h2h.driver1Name)
                        .font(.terminalCaption)
                        .fontWeight(.semibold)
                        .foregroundStyle(colors.textBright)
                    HStack(spacing: 8) {
                        Text("Q: \(h2h.driver1QualiWins)")
                            .font(.terminalMicro)
                            .foregroundStyle(h2h.driver1QualiWins > h2h.driver2QualiWins ? colors.green : colors.textDim)
                        Text("R: \(h2h.driver1RaceWins)")
                            .font(.terminalMicro)
                            .foregroundStyle(h2h.driver1RaceWins > h2h.driver2RaceWins ? colors.green : colors.textDim)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                Text("vs")
                    .font(.terminalMicro)
                    .foregroundStyle(colors.textDim)
                    .padding(.horizontal, 8)

                VStack(alignment: .trailing, spacing: 2) {
                    Text(h2h.driver2Name)
                        .font(.terminalCaption)
                        .fontWeight(.semibold)
                        .foregroundStyle(colors.textBright)
                    HStack(spacing: 8) {
                        Text("Q: \(h2h.driver2QualiWins)")
                            .font(.terminalMicro)
                            .foregroundStyle(h2h.driver2QualiWins > h2h.driver1QualiWins ? colors.green : colors.textDim)
                        Text("R: \(h2h.driver2RaceWins)")
                            .font(.terminalMicro)
                            .foregroundStyle(h2h.driver2RaceWins > h2h.driver1RaceWins ? colors.green : colors.textDim)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .trailing)
            }
        }
        .padding(10)
        .background(colors.bgStripe)
        .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
    }

    // MARK: - Probability Charts

    private func probabilityChart(
        title: String, tag: String,
        data: [DriverPrediction],
        keyPath: KeyPath<DriverPrediction, Double>,
        color: Color? = nil
    ) -> some View {
        TerminalSection(title: title, tag: tag) {
            let maxVal: Double = data.first?[keyPath: keyPath] ?? 1
            VStack(spacing: 4) {
                ForEach(data) { driver in
                    BarChartRow(
                        label: driver.driverName,
                        value: driver[keyPath: keyPath],
                        maxValue: maxVal,
                        color: color
                    )
                }
            }
        }
    }

    // MARK: - Model Scorecard

    private var modelScorecard: some View {
        TerminalSection(title: "Model Report Card", tag: "\(MockData.seasonAccuracy.totalRaces) races") {
            let season = MockData.seasonAccuracy

            VStack(spacing: 12) {
                HStack(spacing: 0) {
                    accuracyStat("Winner", season.winnerRate)
                    accuracyStat("Podium", season.podiumRate)
                    accuracyStat("Top 10", season.top10Rate)
                }

                VStack(spacing: 6) {
                    ForEach(MockData.raceAccuracy) { race in
                        HStack(spacing: 8) {
                            Image(systemName: race.winnerCorrect ? "checkmark.circle.fill" : "xmark.circle")
                                .font(.system(size: 12))
                                .foregroundStyle(race.winnerCorrect ? colors.green : colors.red)

                            Text("R\(race.round)")
                                .font(.terminalMicro)
                                .foregroundStyle(colors.textDim)
                                .frame(width: 24)

                            VStack(alignment: .leading, spacing: 1) {
                                Text(race.raceName)
                                    .font(.terminalCaption)
                                    .foregroundStyle(colors.textBright)
                                Text("Predicted: \(race.winnerPredicted) → Actual: \(race.winnerActual)")
                                    .font(.bodyMicro)
                                    .foregroundStyle(colors.textDim)
                            }

                            Spacer()

                            Text("\(race.top10Accuracy)/10")
                                .font(.terminalMicro)
                                .foregroundStyle(colors.text)
                                .monospacedDigit()
                        }
                    }
                }
            }
        }
    }

    private func accuracyStat(_ label: String, _ value: Double) -> some View {
        VStack(spacing: 3) {
            Text(String(format: "%.0f%%", value))
                .font(.system(size: 18, weight: .bold, design: .monospaced))
                .foregroundStyle(value >= 50 ? colors.green : colors.textBright)
                .monospacedDigit()
            Text(label.uppercased())
                .font(.terminalMicro)
                .tracking(0.5)
                .foregroundStyle(colors.textDim)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Coming Soon (Roadmap Preview)

    private var comingSoon: some View {
        TerminalSection(title: "On the Roadmap") {
            VStack(spacing: 10) {
                roadmapItem(icon: "chart.line.uptrend.xyaxis", title: "Value Board", timeline: "Before Monaco GP")
                roadmapItem(icon: "slider.horizontal.3", title: "What-If Simulator", timeline: "Before Silverstone")
            }
        }
    }

    private func roadmapItem(icon: String, title: String, timeline: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(colors.textDim)
                .frame(width: 24)

            Text(title)
                .font(.terminalCaption)
                .foregroundStyle(colors.text)

            Spacer()

            Text(timeline)
                .font(.bodyMicro)
                .foregroundStyle(colors.textDim)
        }
    }
}

#Preview {
    InsightsTab(weekend: MockData.raceWeekends[0])
        .environment(\.themeManager, ThemeManager())
        .preferredColorScheme(.dark)
}
