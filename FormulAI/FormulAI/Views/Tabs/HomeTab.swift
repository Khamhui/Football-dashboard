import SwiftUI

struct HomeTab: View {
    let weekend: RaceWeekend

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.favorites) private var favorites
    @Environment(\.terminalLayout) private var layout
    @Environment(\.dataStore) private var store

    var body: some View {
        ScrollView {
            if layout.isWide {
                VStack(spacing: 8) {
                    HStack(alignment: .top, spacing: 12) {
                        VStack(spacing: 8) {
                            yourDriverCard
                            weekendHeadline
                            podiumTeaser
                        }
                        .frame(maxWidth: .infinity)

                        VStack(spacing: 8) {
                            whatChanged
                            newsSection
                        }
                        .frame(maxWidth: .infinity)
                    }
                    .padding(.horizontal, layout.cardPadding)
                }
            } else {
                VStack(spacing: 8) {
                    yourDriverCard
                    weekendHeadline
                    podiumTeaser
                    whatChanged
                    newsSection
                }
            }
        }
        .padding(.bottom, 16)
        .background(colors.bg)
    }

    private var yourDriverCard: some View {
        let standing = favorites.favoriteDriverStanding
        let prediction = favorites.favoriteDriverPrediction

        return HStack(spacing: 12) {
            TeamColorBar(teamId: favorites.favoriteTeamId, width: 5, height: 56)

            VStack(alignment: .leading, spacing: 4) {
                Text("YOUR DRIVER")
                    .font(.terminalMicro)
                    .tracking(1)
                    .foregroundStyle(colors.textDim)

                Text(favorites.favoriteDriverName.uppercased())
                    .font(.system(size: 18, weight: .bold, design: .monospaced))
                    .foregroundStyle(colors.textBright)
            }

            Spacer()

            if let standing {
                VStack(alignment: .trailing, spacing: 4) {
                    Text("P\(standing.position)")
                        .font(.system(size: 20, weight: .bold, design: .monospaced))
                        .foregroundStyle(Color.position(standing.position))

                    Text("\(Int(standing.points)) pts")
                        .font(.terminalCaption)
                        .foregroundStyle(colors.textDim)
                        .monospacedDigit()
                }
            }

            if let prediction {
                VStack(alignment: .trailing, spacing: 4) {
                    Text(String(format: "%.0f%%", prediction.simPodiumPct))
                        .font(.system(size: 16, weight: .bold, design: .monospaced))
                        .foregroundStyle(theme.accent)

                    Text("podium")
                        .font(.terminalMicro)
                        .foregroundStyle(colors.textDim)
                }
            }
        }
        .padding(layout.cardInnerPadding)
        .background(colors.bgPanel)
        .overlay(
            RoundedRectangle(cornerRadius: layout.cardRadius)
                .stroke(F1Team.color(forApiId: favorites.favoriteTeamId).opacity(0.3), lineWidth: 1)
        )
        .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
        .padding(.horizontal, layout.cardPadding)
        .padding(.top, 8)
    }

    private var weekendHeadline: some View {
        let insight = store.predictionInsight

        return VStack(alignment: .leading, spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(weekend.name.uppercased())
                        .font(.terminalTitle)
                        .foregroundStyle(colors.textBright)

                    HStack(spacing: 8) {
                        Text("\(weekend.season) R\(weekend.round)")
                            .font(.terminalLabel)
                            .foregroundStyle(colors.textDim)
                        CircuitBadge(type: weekend.circuitType)
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    Text("STARTS IN")
                        .font(.terminalMicro)
                        .tracking(0.5)
                        .foregroundStyle(colors.textDim)

                    Text("3d 20h")
                        .font(.system(size: 22, weight: .bold, design: .monospaced))
                        .foregroundStyle(theme.accent)
                }
            }

            Rectangle()
                .fill(colors.border)
                .frame(height: 0.5)

            Text(insight.whySentence)
                .font(.bodySmall)
                .foregroundStyle(colors.text)
                .lineSpacing(3)

            Text(insight.casualDescription)
                .font(.bodyMicro)
                .foregroundStyle(colors.textDim)
        }
        .padding(layout.cardInnerPadding)
        .background(colors.bgPanel)
        .overlay(RoundedRectangle(cornerRadius: layout.cardRadius).stroke(colors.border, lineWidth: 0.5))
        .clipShape(RoundedRectangle(cornerRadius: layout.cardRadius))
        .padding(.horizontal, layout.cardPadding)
    }

    private var podiumTeaser: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("PREDICTED PODIUM")
                    .font(.terminalMicro)
                    .tracking(1)
                    .foregroundStyle(colors.textDim)
                Spacer()
                HStack(spacing: 4) {
                    Text("Full predictions")
                        .font(.terminalMicro)
                        .foregroundStyle(theme.accent)
                    Image(systemName: "chevron.right")
                        .font(.system(size: 8))
                        .foregroundStyle(theme.accent)
                }
            }

            PodiumForecast(predictions: Array(store.predictions.prefix(3)))
        }
        .padding(.horizontal, layout.cardPadding)
    }

    private var whatChanged: some View {
        TerminalSection(title: "What Changed", tag: store.lastFetched.map { "updated \(Self.timeAgo($0))" } ?? "") {
            VStack(spacing: 6) {
                ForEach(store.modelMovements) { move in
                    MovementRow(
                        driverName: move.driverName,
                        teamId: move.teamId,
                        delta: move.delta,
                        formattedDelta: String(format: "%+.1f%% %@", move.delta, move.metric.displayName),
                        reason: move.reason
                    )
                }
            }
        }
    }

    private var newsSection: some View {
        TerminalSection(title: "Latest News", tag: "RSS") {
            VStack(spacing: 0) {
                ForEach(Array(store.newsHeadlines.enumerated()), id: \.element.id) { index, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text(item.source.uppercased())
                            .font(.terminalMicro)
                            .foregroundStyle(colors.cyan)
                            .frame(width: 56, alignment: .leading)

                        VStack(alignment: .leading, spacing: 3) {
                            Text(item.title)
                                .font(.bodyCaption)
                                .foregroundStyle(colors.text)
                                .lineLimit(2)

                            HStack(spacing: 6) {
                                Text(item.timeAgo)
                                    .font(.bodyMicro)
                                    .foregroundStyle(colors.textDim)

                                if let impact = item.impact {
                                    Text(impact)
                                        .font(.system(size: 9, weight: .semibold, design: .monospaced))
                                        .foregroundStyle(theme.accent)
                                        .padding(.horizontal, 5)
                                        .padding(.vertical, 1)
                                        .background(theme.accent.opacity(0.1))
                                        .clipShape(RoundedRectangle(cornerRadius: 3))
                                }
                            }
                        }

                        Spacer()
                    }
                    .padding(.vertical, 8)
                    .zebraRow(index)
                }
            }
        }
    }

    private static func timeAgo(_ date: Date) -> String {
        let seconds = Int(-date.timeIntervalSinceNow)
        if seconds < 60 { return "just now" }
        if seconds < 3600 { return "\(seconds / 60) min ago" }
        return "\(seconds / 3600)h ago"
    }
}

#Preview("Dark") {
    HomeTab(weekend: MockData.raceWeekends[0])
        .environment(\.themeManager, ThemeManager())
        .environment(\.favorites, FavoritesManager())
        .preferredColorScheme(.dark)
}

#Preview("Light") {
    HomeTab(weekend: MockData.raceWeekends[0])
        .environment(\.themeManager, ThemeManager())
        .environment(\.favorites, FavoritesManager())
        .preferredColorScheme(.light)
}
