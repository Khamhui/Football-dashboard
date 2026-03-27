import SwiftUI

struct StandingsTab: View {
    let weekend: RaceWeekend

    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.favorites) private var favorites

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                championshipProbability
                driverStandings
                constructorStandings
            }
            .padding(.bottom, 16)
        }
        .background(colors.bg)
    }

    // MARK: - Championship Probability

    private var championshipProbability: some View {
        let probs = MockData.championshipProbabilities
        let maxProb = probs.first?.probability ?? 1

        return TerminalSection(title: "Championship Probability", tag: "based on 10,000 simulations of remaining 21 races") {
            VStack(spacing: 4) {
                ForEach(probs) { driver in
                    HStack(spacing: 6) {
                        TeamColorBar(teamId: driver.teamId)
                        Text(driver.driverName)
                            .font(.terminalCaption)
                            .foregroundStyle(colors.text)
                            .frame(width: 80, alignment: .leading)
                            .lineLimit(1)

                        HorizontalBar(
                            value: driver.probability,
                            maxValue: maxProb,
                            color: F1Team.color(forApiId: driver.teamId).opacity(0.8)
                        )

                        Text(String(format: "%.1f%%", driver.probability))
                            .font(.terminalCaption)
                            .fontWeight(.semibold)
                            .foregroundStyle(colors.textBright)
                            .monospacedDigit()
                            .frame(width: 48, alignment: .trailing)
                    }
                }
            }
        }
    }

    // MARK: - Driver Standings

    private var driverStandings: some View {
        let standings = MockData.driverStandings
        let maxPts = standings.first?.points ?? 1

        return TerminalSection(title: "Drivers Championship", tag: "2026") {
            VStack(spacing: 0) {
                ForEach(Array(standings.enumerated()), id: \.element.id) { index, driver in
                    StandingRow(
                        position: driver.position,
                        name: driver.driverName,
                        teamId: driver.teamId,
                        wins: driver.wins,
                        points: driver.points,
                        maxPoints: maxPts,
                        barColor: theme.accent,
                        isFavorite: driver.id == favorites.favoriteDriverId
                    )
                    .zebraRow(index)
                }
            }
        }
    }

    // MARK: - Constructor Standings

    private var constructorStandings: some View {
        let standings = MockData.constructorStandings
        let maxPts = standings.first?.points ?? 1

        return TerminalSection(title: "Constructors", tag: "2026") {
            VStack(spacing: 0) {
                ForEach(Array(standings.enumerated()), id: \.element.id) { index, team in
                    StandingRow(
                        position: team.position,
                        name: team.teamName,
                        teamId: team.id,
                        wins: team.wins,
                        points: team.points,
                        maxPoints: maxPts,
                        barColor: F1Team.color(forApiId: team.id),
                        isFavorite: team.id == favorites.favoriteTeamId
                    )
                    .zebraRow(index)
                }
            }
        }
    }
}

// MARK: - Shared Standing Row

private struct StandingRow: View {
    let position: Int
    let name: String
    let teamId: String
    let wins: Int
    let points: Double
    let maxPoints: Double
    let barColor: Color
    var isFavorite: Bool = false

    @Environment(\.terminalColors) private var colors

    private var isHighlighted: Bool { isFavorite || position <= 3 }

    var body: some View {
        VStack(spacing: 4) {
            HStack(spacing: 0) {
                FavoriteIndicator(position: position, teamId: teamId, isFavorite: isFavorite)

                HStack(spacing: 5) {
                    TeamColorBar(teamId: teamId)
                    Text(name)
                        .font(.terminalCaption)
                        .fontWeight(isHighlighted ? .semibold : .regular)
                        .foregroundStyle(isHighlighted ? colors.textBright : colors.text)
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                if wins > 0 {
                    HStack(spacing: 2) {
                        Image(systemName: "trophy.fill")
                            .font(.system(size: 9))
                        Text("\(wins)")
                            .font(.terminalCaption)
                    }
                    .foregroundStyle(colors.yellow)
                    .frame(width: 36)
                } else {
                    Spacer().frame(width: 36)
                }

                Text(String(format: "%.0f", points))
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundStyle(colors.textBright)
                    .monospacedDigit()
                    .frame(width: 40, alignment: .trailing)
            }

            HorizontalBar(value: points, maxValue: maxPoints, color: barColor, height: 4)
                .padding(.leading, 30)
        }
        .padding(.vertical, 5)
        .background(isFavorite ? F1Team.color(forApiId: teamId).opacity(0.08) : Color.clear)
    }
}

#Preview {
    StandingsTab(weekend: MockData.raceWeekends[0])
        .environment(\.themeManager, ThemeManager())
        .preferredColorScheme(.dark)
}
