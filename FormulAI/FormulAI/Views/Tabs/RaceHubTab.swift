import SwiftUI

struct RaceHubTab: View {
    let weekend: RaceWeekend

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @State private var segment: RaceHubSegment = .circuit
    @State private var selectedDriver: DriverPrediction?

    var body: some View {
        VStack(spacing: 0) {
            segmentedControl
            TerminalDivider()

            ScrollView {
                Group {
                    switch segment {
                    case .circuit: CircuitSegment(weekend: weekend)
                    case .predictions: PredictionsSegment(selectedDriver: $selectedDriver)
                    case .live: LivePlaceholder(weekend: weekend)
                    }
                }
                .transition(.opacity)
                .id(segment)
            }
        }
        .background(colors.bg)
        .sheet(item: $selectedDriver) { driver in
            DriverDetailSheet(driver: driver)
                .presentationDetents([.medium])
                .presentationDragIndicator(.visible)
        }
    }

    private var segmentedControl: some View {
        HStack(spacing: 0) {
            ForEach(RaceHubSegment.allCases, id: \.self) { seg in
                Button {
                    Haptics.select()
                    withAnimation(.easeInOut(duration: 0.2)) { segment = seg }
                } label: {
                    Text(seg.label.uppercased())
                        .font(.terminalMicro)
                        .tracking(0.5)
                        .foregroundStyle(segment == seg ? theme.accent : colors.textDim)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .overlay(alignment: .bottom) {
                            if segment == seg {
                                Rectangle()
                                    .fill(theme.accent)
                                    .frame(height: 2)
                            }
                        }
                }
            }
        }
        .background(colors.bgPanel)
    }
}

// MARK: - Circuit Segment

private struct CircuitSegment: View {
    let weekend: RaceWeekend

    @Environment(\.terminalColors) private var colors
    @Environment(\.dataStore) private var store

    private var info: CircuitInfo { store.circuitInfo ?? MockData.circuitInfo }
    private var profile: CircuitProfile { store.circuitProfile ?? MockData.circuitProfile }
    private var weather: WeatherForecast { store.weather ?? MockData.weather }

    var body: some View {
        VStack(spacing: 0) {
            circuitHeader
            circuitDescription
            coreStats
            sessionSchedule
            recentHistory
            weatherSection
            trackSpecialistsSection
        }
        .padding(.bottom, 16)
    }

    private var circuitHeader: some View {
        VStack(spacing: 8) {
            Text(info.name.uppercased())
                .font(.terminalTitle)
                .tracking(1)
                .foregroundStyle(colors.textBright)
                .multilineTextAlignment(.center)

            HStack(spacing: 12) {
                Text(info.country)
                    .font(.terminalCaption)
                    .foregroundStyle(colors.textDim)
                CircuitBadge(type: weekend.circuitType)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity)
    }

    private var circuitDescription: some View {
        TerminalSection(title: "What Makes This Circuit Unique") {
            Text(info.description)
                .font(.bodySmall)
                .foregroundStyle(colors.text)
                .lineSpacing(4)
        }
    }

    private var coreStats: some View {
        TerminalSection(title: "Circuit Stats") {
            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 8) {
                StatPair(label: "Laps", value: "\(info.laps)")
                StatPair(label: "Length", value: String(format: "%.3f km", info.lengthKm))
                StatPair(label: "Race Distance", value: String(format: "%.1f km", info.raceDistanceKm))
                StatPair(label: "Lap Record", value: info.lapRecord)
                StatPair(label: "Grid Correlation", value: String(format: "%.2f", profile.gridCorrelation))
                StatPair(label: "Overtaking Rate", value: String(format: "%.0f%%", profile.overtakingRate * 100))
            }
        }
    }

    private var sessionSchedule: some View {
        TerminalSection(title: "Session Schedule", tag: "local time") {
            VStack(spacing: 4) {
                ForEach(store.sessionSchedule) { entry in
                    SessionScheduleRow(session: entry.session, day: entry.day, time: entry.time)
                }
            }
        }
    }

    private var recentHistory: some View {
        TerminalSection(title: "Recent Winners") {
            VStack(spacing: 4) {
                ForEach(info.recentWinners) { winner in
                    HStack {
                        Text("\(winner.season)")
                            .font(.terminalCaption)
                            .foregroundStyle(colors.textDim)
                            .monospacedDigit()
                        TeamColorBar(teamId: winner.teamId)
                        Text(winner.driver)
                            .font(.terminalCaption)
                            .fontWeight(.semibold)
                            .foregroundStyle(colors.textBright)
                        Spacer()
                    }
                }
            }
        }
    }

    private var weatherSection: some View {
        TerminalSection(title: "Weather Forecast", tag: "race day") {
            WeatherRow(weather: weather)
        }
    }

    private var trackSpecialistsSection: some View {
        TerminalSection(title: "Track Specialists") {
            VStack(spacing: 0) {
                ForEach(Array(store.trackSpecialists.enumerated()), id: \.element.id) { index, spec in
                    HStack(spacing: 0) {
                        HStack(spacing: 5) {
                            TeamColorBar(teamId: spec.teamId)
                            Text(spec.name)
                                .font(.terminalCaption)
                                .foregroundStyle(colors.text)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)

                        Text(String(format: "%.1f", spec.avgPos))
                            .font(.terminalCaption)
                            .fontWeight(.semibold)
                            .foregroundStyle(spec.avgPos <= 2 ? colors.green : colors.textBright)
                            .monospacedDigit()
                            .frame(width: 60, alignment: .trailing)

                        Text("\(spec.races) races")
                            .font(.terminalMicro)
                            .foregroundStyle(colors.textDim)
                            .frame(width: 56, alignment: .trailing)
                    }
                    .padding(.vertical, 4)
                    .zebraRow(index)
                }
            }
        }
    }
}

// MARK: - Predictions Segment

private struct PredictionsSegment: View {
    @Binding var selectedDriver: DriverPrediction?

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.favorites) private var favorites
    @Environment(\.terminalLayout) private var layout
    @Environment(\.dataStore) private var store

    @State private var showFullGrid = false

    private var predictions: [DriverPrediction] { store.predictions }

    private var visiblePredictions: [DriverPrediction] {
        if showFullGrid { return predictions }
        let top10 = Array(predictions.prefix(10))
        guard let favId = Optional(favorites.favoriteDriverId),
              !top10.contains(where: { $0.id == favId }),
              let favDriver = predictions.first(where: { $0.id == favId }) else {
            return top10
        }
        return top10 + [favDriver]
    }

    var body: some View {
        VStack(spacing: 0) {
            if let winner = predictions.first {
                HeroPredictionCard(driver: winner, insight: store.predictionInsight)
                    .padding(.horizontal, layout.cardPadding)
                    .padding(.top, layout.sectionSpacing)
            }

            if layout.isWide {
                HStack(alignment: .top, spacing: 0) {
                    raceGrid
                        .frame(maxWidth: .infinity)
                    dnfRiskChart
                        .frame(width: 340)
                }
            } else {
                raceGrid
                dnfRiskChart
            }
        }
        .padding(.bottom, 16)
    }

    private var raceGrid: some View {
        TerminalSection(title: "Race Grid", tag: showFullGrid ? "22 drivers" : "top 10") {
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        TerminalHeaderCell(text: "#", width: 22, alignment: .center)
                        TerminalHeaderCell(text: "Driver")
                        TerminalHeaderCell(text: "Win", width: 44, alignment: .trailing)
                        TerminalHeaderCell(text: "Podium", width: 50, alignment: .trailing)
                        TerminalHeaderCell(text: "Ret%", width: 40, alignment: .trailing)
                        TerminalHeaderCell(text: "Pts", width: 40, alignment: .trailing)
                    }
                    .padding(.bottom, 4)

                    let visible = visiblePredictions
                    ForEach(Array(visible.enumerated()), id: \.element.id) { index, driver in
                        let actualPosition = (predictions.firstIndex(where: { $0.id == driver.id }) ?? index) + 1
                        Button { Haptics.tap(); selectedDriver = driver } label: {
                            DriverGridRow(
                                driver: driver,
                                position: actualPosition,
                                showDnf: true,
                                isFavorite: driver.id == favorites.favoriteDriverId
                            )
                            .zebraRow(index)
                        }
                        .buttonStyle(.plain)
                    }

                    Button {
                        Haptics.tap()
                        withAnimation(.easeInOut(duration: 0.3)) { showFullGrid.toggle() }
                    } label: {
                        HStack(spacing: 6) {
                            Text(showFullGrid ? "Show Top 10" : "Show All 22 Drivers")
                                .font(.bodyCaption)
                                .fontWeight(.medium)
                                .foregroundStyle(theme.accent)
                            Image(systemName: showFullGrid ? "chevron.up" : "chevron.down")
                                .font(.system(size: 10, weight: .semibold))
                                .foregroundStyle(theme.accent)
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.top, 12)
                    }
                    .buttonStyle(.plain)
                }
            }
    }

    private var dnfRiskChart: some View {
        TerminalSection(title: "Retirement Risk", tag: "top 8") {
            let dnfSorted = store.predictions.sorted { $0.simDnfPct > $1.simDnfPct }.prefix(8).map { $0 }
            let maxVal = dnfSorted.first?.simDnfPct ?? 1
            VStack(spacing: 4) {
                ForEach(dnfSorted) { driver in
                    BarChartRow(
                        label: driver.driverName,
                        value: driver.simDnfPct,
                        maxValue: maxVal,
                        color: colors.dnfColor(for: driver.simDnfPct, accent: theme.accent)
                    )
                }
            }
        }
    }
}

// MARK: - Live Pre-Race Hub

private struct LivePlaceholder: View {
    let weekend: RaceWeekend

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.terminalLayout) private var layout
    @Environment(\.dataStore) private var store

    private var weather: WeatherForecast { store.weather ?? MockData.weather }

    var body: some View {
        VStack(spacing: 0) {
            nextSessionCountdown
            sessionScheduleCompact
            whoToWatch
            weatherConditions
            notifyCTA
        }
        .padding(.bottom, 16)
    }

    private var nextSessionCountdown: some View {
        VStack(spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: "antenna.radiowaves.left.and.right")
                    .font(.system(size: 14))
                    .foregroundStyle(theme.accent)
                Text("NEXT SESSION")
                    .font(.terminalMicro)
                    .tracking(1)
                    .foregroundStyle(theme.accent)
            }

            Text("\(weekend.name) — FP1")
                .font(.terminalTitle)
                .foregroundStyle(colors.textBright)

            Text("3d 18h 30m")
                .font(.system(size: 32, weight: .bold, design: .monospaced))
                .foregroundStyle(theme.accent)

            Text("Live timing and predictions activate\nwhen the session begins")
                .font(.bodyMicro)
                .foregroundStyle(colors.textDim)
                .multilineTextAlignment(.center)
                .lineSpacing(3)
        }
        .padding(.vertical, 24)
        .frame(maxWidth: .infinity)
    }

    private var sessionScheduleCompact: some View {
        TerminalSection(title: "Session Schedule", tag: "local time") {
            VStack(spacing: 4) {
                ForEach(Array(store.sessionSchedule.enumerated()), id: \.element.id) { index, entry in
                    SessionScheduleRow(session: entry.session, day: entry.day, time: entry.time, isHighlighted: index == 0)
                }
            }
        }
    }

    private var whoToWatch: some View {
        TerminalSection(title: "Who to Watch", tag: "algorithm picks") {
            VStack(spacing: 8) {
                ForEach(store.whoToWatch) { pick in
                    watchCard(name: pick.name, teamId: pick.teamId, insight: pick.insight)
                }
            }
        }
    }

    private func watchCard(name: String, teamId: String, insight: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            TeamColorBar(teamId: teamId)
            VStack(alignment: .leading, spacing: 3) {
                Text(name.uppercased())
                    .font(.terminalCaption)
                    .fontWeight(.bold)
                    .foregroundStyle(colors.textBright)
                Text(insight)
                    .font(.bodyMicro)
                    .foregroundStyle(colors.textDim)
                    .lineSpacing(2)
            }
        }
    }

    private var weatherConditions: some View {
        TerminalSection(title: "Current Conditions", tag: "Suzuka") {
            WeatherRow(weather: weather)
        }
    }

    private var notifyCTA: some View {
        Button {} label: {
            HStack(spacing: 8) {
                Image(systemName: "bell.badge")
                    .font(.system(size: 13))
                Text("Notify me when FP1 starts")
                    .font(.bodyMicro)
            }
            .foregroundStyle(theme.accent)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 12)
            .background(theme.accent.opacity(0.1))
            .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
            .overlay(
                RoundedRectangle(cornerRadius: layout.cardRadius)
                    .stroke(theme.accent.opacity(0.3), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
        .padding(.horizontal, layout.cardPadding)
        .padding(.top, layout.sectionSpacing)
    }
}

// MARK: - Shared Driver Row (reused by predictions)

struct DriverGridRow: View {
    let driver: DriverPrediction
    let position: Int
    var showTeamName: Bool = false
    var showDnf: Bool = false
    var isFavorite: Bool = false

    @Environment(\.terminalColors) private var colors

    var body: some View {
        let teamColor = F1Team.color(forApiId: driver.teamId)

        HStack(spacing: 0) {
            FavoriteIndicator(position: position, teamId: driver.teamId, isFavorite: isFavorite)

            HStack(spacing: 4) {
                TeamColorBar(teamId: driver.teamId)
                if showTeamName {
                    VStack(alignment: .leading, spacing: 1) {
                        driverNameText
                        Text(driver.teamName)
                            .font(.terminalMicro)
                            .foregroundStyle(colors.textDim)
                            .lineLimit(1)
                    }
                } else {
                    driverNameText
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)

            Text(String(format: "%.1f", driver.simWinPct))
                .font(.terminalCaption)
                .fontWeight(driver.simWinPct >= 10 ? .bold : .regular)
                .monospacedDigit()
                .foregroundStyle(driver.simWinPct >= 10 ? colors.green : colors.textDim)
                .frame(width: 44, alignment: .trailing)

            Text(String(format: "%.1f", driver.simPodiumPct))
                .font(.terminalCaption)
                .monospacedDigit()
                .foregroundStyle(colors.text)
                .frame(width: 50, alignment: .trailing)

            if showDnf {
                Text(String(format: "%.0f", driver.simDnfPct))
                    .font(.terminalCaption)
                    .monospacedDigit()
                    .foregroundStyle(colors.dnfColor(for: driver.simDnfPct, accent: colors.text))
                    .frame(width: 40, alignment: .trailing)
            }

            Text(String(format: "%.1f", driver.simExpectedPoints))
                .font(.terminalCaption)
                .fontWeight(.semibold)
                .monospacedDigit()
                .foregroundStyle(colors.textBright)
                .frame(width: 40, alignment: .trailing)
        }
        .padding(.vertical, showTeamName ? 5 : 4)
        .background(isFavorite ? teamColor.opacity(0.08) : Color.clear)
        .contentShape(Rectangle())
    }

    private var isHighlighted: Bool { isFavorite || position <= 3 }

    private var driverNameText: some View {
        Text(driver.driverName)
            .font(.terminalCaption)
            .fontWeight(isHighlighted ? .semibold : .regular)
            .foregroundStyle(isHighlighted ? colors.textBright : colors.text)
            .lineLimit(1)
    }
}

#Preview("Dark") {
    RaceHubTab(weekend: MockData.raceWeekends[0])
        .environment(\.themeManager, ThemeManager())
        .preferredColorScheme(.dark)
}
