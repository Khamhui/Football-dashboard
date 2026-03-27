import SwiftUI
import WidgetKit

// MARK: - Favorite Driver Widget (Small)

struct FavoriteDriverProvider: TimelineProvider {
    func placeholder(in context: Context) -> FavoriteDriverEntry {
        FavoriteDriverEntry(date: .now, driver: WidgetData.driverStandings[0])
    }

    func getSnapshot(in context: Context, completion: @escaping (FavoriteDriverEntry) -> Void) {
        let driver = findFavoriteDriver()
        completion(FavoriteDriverEntry(date: .now, driver: driver))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<FavoriteDriverEntry>) -> Void) {
        let driver = findFavoriteDriver()
        let entry = FavoriteDriverEntry(date: .now, driver: driver)
        let timeline = Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(3600)))
        completion(timeline)
    }

    private func findFavoriteDriver() -> WidgetData.StandingEntry {
        let favId = WidgetData.favoriteDriverId
        return WidgetData.driverStandings.first { $0.id == favId }
            ?? WidgetData.driverStandings[0]
    }
}

struct FavoriteDriverEntry: TimelineEntry {
    let date: Date
    let driver: WidgetData.StandingEntry
}

struct FavoriteDriverWidgetView: View {
    let entry: FavoriteDriverEntry

    var body: some View {
        let teamColor = Color(
            red: Double((entry.driver.teamColorHex >> 16) & 0xFF) / 255,
            green: Double((entry.driver.teamColorHex >> 8) & 0xFF) / 255,
            blue: Double(entry.driver.teamColorHex & 0xFF) / 255
        )

        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                Rectangle()
                    .fill(teamColor)
                    .frame(width: 4, height: 16)
                    .clipShape(RoundedRectangle(cornerRadius: 1))

                Text(entry.driver.name.uppercased())
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white)
                    .lineLimit(1)
            }

            Spacer()

            Text("P\(entry.driver.position)")
                .font(.system(size: 28, weight: .bold, design: .monospaced))
                .foregroundStyle(positionColor(entry.driver.position))

            HStack(spacing: 4) {
                Text("\(entry.driver.points)")
                    .font(.system(size: 14, weight: .bold, design: .monospaced))
                    .foregroundStyle(.white)
                Text("PTS")
                    .font(.system(size: 9, weight: .semibold, design: .monospaced))
                    .foregroundStyle(.gray)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .containerBackground(.black, for: .widget)
    }

    private func positionColor(_ pos: Int) -> Color {
        WidgetColors.positionColor(pos)
    }
}

struct FavoriteDriverWidget: Widget {
    let kind = "FavoriteDriverWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: FavoriteDriverProvider()) { entry in
            FavoriteDriverWidgetView(entry: entry)
        }
        .configurationDisplayName("Favorite Driver")
        .description("Track your driver's championship position and points")
        .supportedFamilies([.systemSmall])
    }
}

#Preview("Favorite Driver", as: .systemSmall) {
    FavoriteDriverWidget()
} timeline: {
    FavoriteDriverEntry(date: .now, driver: WidgetData.driverStandings[2])
}
