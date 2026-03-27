import SwiftUI
import WidgetKit

// MARK: - Race Calendar Widget (Large)

struct CalendarProvider: TimelineProvider {
    func placeholder(in context: Context) -> CalendarEntry {
        CalendarEntry(date: .now, races: WidgetData.calendar)
    }

    func getSnapshot(in context: Context, completion: @escaping (CalendarEntry) -> Void) {
        completion(CalendarEntry(date: .now, races: WidgetData.calendar))
    }

    func getTimeline(in context: Context, completion: @escaping (Timeline<CalendarEntry>) -> Void) {
        let entry = CalendarEntry(date: .now, races: WidgetData.calendar)
        let timeline = Timeline(entries: [entry], policy: .after(.now.addingTimeInterval(86400)))
        completion(timeline)
    }
}

struct CalendarEntry: TimelineEntry {
    let date: Date
    let races: [WidgetData.CalendarEntry]
}

struct RaceCalendarWidgetView: View {
    let entry: CalendarEntry

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("2026 RACE CALENDAR")
                    .font(.system(size: 9, weight: .bold, design: .monospaced))
                    .foregroundStyle(WidgetColors.terminalGreen)
                    .tracking(0.5)
                Spacer()
                Text("FORMULAI")
                    .font(.system(size: 8, weight: .bold, design: .monospaced))
                    .foregroundStyle(Color(white: 0.3))
                    .tracking(1)
            }
            .padding(.bottom, 8)

            ForEach(entry.races) { race in
                calendarRow(race)
            }

            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .containerBackground(.black, for: .widget)
    }

    private func calendarRow(_ race: WidgetData.CalendarEntry) -> some View {
        HStack(spacing: 0) {
            Text("R\(race.round)")
                .font(.system(size: 9, weight: .semibold, design: .monospaced))
                .foregroundStyle(race.isNext ? WidgetColors.terminalGreen : Color(white: 0.4))
                .frame(width: 22, alignment: .leading)

            if race.isNext {
                Image(systemName: "arrow.right")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(WidgetColors.terminalGreen)
                    .frame(width: 14)
            } else if race.isCompleted {
                Image(systemName: "checkmark")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(Color(white: 0.35))
                    .frame(width: 14)
            } else if race.isCancelled {
                Image(systemName: "xmark")
                    .font(.system(size: 7, weight: .bold))
                    .foregroundStyle(WidgetColors.cancelRed)
                    .frame(width: 14)
            } else {
                Spacer().frame(width: 14)
            }

            Text(race.name)
                .font(.system(size: 10, weight: race.isNext ? .bold : .regular, design: .monospaced))
                .foregroundStyle(
                    race.isCancelled ? WidgetColors.cancelRed.opacity(0.6) :
                    race.isCompleted ? Color(white: 0.45) :
                    race.isNext ? .white :
                    Color(white: 0.7)
                )
                .lineLimit(1)
                .strikethrough(race.isCancelled, color: WidgetColors.cancelRed.opacity(0.4))

            Spacer()

            Text(race.dateRange)
                .font(.system(size: 9, weight: .regular, design: .monospaced))
                .foregroundStyle(Color(white: 0.4))
                .monospacedDigit()
        }
        .padding(.vertical, 4)
        .padding(.horizontal, 4)
        .background(race.isNext ? WidgetColors.terminalGreen.opacity(0.08) : Color.clear)
    }
}

struct RaceCalendarWidget: Widget {
    let kind = "RaceCalendarWidget"

    var body: some WidgetConfiguration {
        StaticConfiguration(kind: kind, provider: CalendarProvider()) { entry in
            RaceCalendarWidgetView(entry: entry)
        }
        .configurationDisplayName("Race Calendar")
        .description("Upcoming races at a glance")
        .supportedFamilies([.systemLarge])
    }
}

#Preview("Calendar", as: .systemLarge) {
    RaceCalendarWidget()
} timeline: {
    CalendarEntry(date: .now, races: WidgetData.calendar)
}
