import SwiftUI
import WidgetKit

// MARK: - Next Race Countdown Widget (Small)

struct NextRaceProvider: TimelineProvider {
    func placeholder(in context: Context) -> NextRaceEntry {
        NextRaceEntry(date: .now, race: WidgetData.nextRace)
    }

    func getSnapshot(in context: Context, completion: @escaping (NextRaceEntry) -> Void) {
        completion(NextRaceEntry(date: .now, race: WidgetData.nextRace))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<NextRaceEntry>) -> Void) {
        let entry = NextRaceEntry(date: .now, race: WidgetData.nextRace)
        let timeline = Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(3600)))
        completion(timeline)
    }
}

struct NextRaceEntry: TimelineEntry {
    let date: Date
    let race: WidgetData.NextRace
}

struct NextRaceWidgetView: View {
    let entry: NextRaceEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("R\(entry.race.round)  \(entry.race.name.split(separator: " ").last ?? "")")
                .font(.system(size: 10, weight: .bold, design: .monospaced))
                .foregroundStyle(.white)
                .lineLimit(1)

            Spacer()

            Text("\(entry.race.daysUntil)d \(entry.race.hoursUntil)h")
                .font(.system(size: 24, weight: .bold, design: .monospaced))
                .foregroundStyle(WidgetColors.phosphorGreen)

            Text("UNTIL LIGHTS OUT")
                .font(.system(size: 8, weight: .semibold, design: .monospaced))
                .foregroundStyle(.gray)
                .tracking(0.5)
        }
        .padding(12)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
        .containerBackground(.black, for: .widget)
    }
}

struct NextRaceWidget: Widget {
    let kind = "NextRaceWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: NextRaceProvider()) { entry in
            NextRaceWidgetView(entry: entry)
        }
        .configurationDisplayName("Next Race")
        .description("Countdown to the next Grand Prix")
        .supportedFamilies([.systemSmall])
    }
}

#Preview("Next Race", as: .systemSmall) {
    NextRaceWidget()
} timeline: {
    NextRaceEntry(date: .now, race: WidgetData.nextRace)
}
