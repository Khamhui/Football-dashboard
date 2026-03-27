import SwiftUI
import WidgetKit

// MARK: - Driver Standings Widget (Medium)

struct StandingsProvider: TimelineProvider {
    func placeholder(in context: Context) -> StandingsEntry {
        StandingsEntry(date: .now, standings: WidgetData.driverStandings)
    }

    func getSnapshot(in context: Context, completion: @escaping (StandingsEntry) -> Void) {
        completion(StandingsEntry(date: .now, standings: WidgetData.driverStandings))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<StandingsEntry>) -> Void) {
        let entry = StandingsEntry(date: .now, standings: WidgetData.driverStandings)
        let timeline = Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(3600)))
        completion(timeline)
    }
}

struct StandingsEntry: TimelineEntry {
    let date: Date
    let standings: [WidgetData.StandingEntry]
}

struct DriverStandingsWidgetView: View {
    let entry: StandingsEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("DRIVERS STANDINGS")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(WidgetColors.terminalGreen)
                    .tracking(0.5)
                Spacer()
                Text("2026")
                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                    .foregroundStyle(.gray)
            }
            .padding(.bottom, 6)

            ForEach(Array(entry.standings.prefix(7).enumerated()), id: \.element.id) { index, driver in
                standingRow(driver, isEven: index.isMultiple(of: 2))
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .containerBackground(.black, for: .widget)
    }

    private func standingRow(_ driver: WidgetData.StandingEntry, isEven: Bool) -> some View {
        let teamColor = Color(
            red: Double((driver.teamColorHex >> 16) & 0xFF) / 255,
            green: Double((driver.teamColorHex >> 8) & 0xFF) / 255,
            blue: Double(driver.teamColorHex & 0xFF) / 255
        )
        let isFavorite = driver.id == WidgetData.favoriteDriverId

        return HStack(spacing: 0) {
            Text("\(driver.position)")
                .font(.system(size: 10, weight: driver.position <= 3 ? .bold : .regular, design: .monospaced))
                .foregroundStyle(positionColor(driver.position))
                .frame(width: 16, alignment: .trailing)

            Rectangle()
                .fill(teamColor)
                .frame(width: 3, height: 12)
                .clipShape(RoundedRectangle(cornerRadius: 1))
                .padding(.horizontal, 6)

            Text(driver.name)
                .font(.system(size: 10, weight: isFavorite ? .bold : .regular, design: .monospaced))
                .foregroundStyle(isFavorite ? .white : Color(white: 0.8))
                .lineLimit(1)

            if isFavorite {
                Image(systemName: "heart.fill")
                    .font(.system(size: 6))
                    .foregroundStyle(teamColor)
                    .padding(.leading, 3)
            }

            Spacer()

            Text("\(driver.points)")
                .font(.system(size: 10, weight: .semibold, design: .monospaced))
                .foregroundStyle(.white)
                .monospacedDigit()
        }
        .padding(.vertical, 2.5)
        .padding(.horizontal, 4)
        .background(isEven ? Color.white.opacity(0.04) : Color.clear)
    }

    private func positionColor(_ pos: Int) -> Color {
        switch pos {
        case 1...3: WidgetColors.positionColor(pos)
        default: Color(white: 0.5)
        }
    }
}

struct DriverStandingsWidget: Widget {
    let kind = "DriverStandingsWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: StandingsProvider()) { entry in
            DriverStandingsWidgetView(entry: entry)
        }
        .configurationDisplayName("Driver Standings")
        .description("Current championship standings at a glance")
        .supportedFamilies([.systemMedium])
    }
}

#Preview("Standings", as: .systemMedium) {
    DriverStandingsWidget()
} timeline: {
    StandingsEntry(date: .now, standings: WidgetData.driverStandings)
}
