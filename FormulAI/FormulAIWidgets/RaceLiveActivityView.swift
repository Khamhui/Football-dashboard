import ActivityKit
import SwiftUI
import WidgetKit

struct RaceLiveActivity: Widget {
    private static let statusDot: CGFloat = 6

    var body: some WidgetConfiguration {
        ActivityConfiguration(for: RaceActivityAttributes.self) { context in
            lockScreenView(context: context)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    HStack(spacing: 4) {
                        Circle()
                            .fill(.green)
                            .frame(width: Self.statusDot, height: Self.statusDot)
                        Text("LAP \(context.state.currentLap)/\(context.state.totalLaps)")
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                            .foregroundStyle(.white)
                    }
                }
                DynamicIslandExpandedRegion(.trailing) {
                    Text(statusLabel(context.state.status))
                        .font(.system(size: 11, weight: .bold, design: .monospaced))
                        .foregroundStyle(statusColor(context.state.status))
                }
                DynamicIslandExpandedRegion(.center) {
                    Text("\(context.attributes.raceName) — \(context.attributes.session)")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundStyle(.gray)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("P1")
                                .font(.system(size: 9, weight: .bold, design: .monospaced))
                                .foregroundStyle(WidgetColors.gold)
                            Text(context.state.leader.uppercased())
                                .font(.system(size: 13, weight: .bold, design: .monospaced))
                                .foregroundStyle(.white)
                        }
                        Spacer()
                        VStack(alignment: .trailing, spacing: 2) {
                            Text("P\(context.state.favoriteDriverPosition)")
                                .font(.system(size: 9, weight: .bold, design: .monospaced))
                                .foregroundStyle(WidgetColors.phosphorGreen)
                            Text(context.state.favoriteDriverName.uppercased())
                                .font(.system(size: 13, weight: .bold, design: .monospaced))
                                .foregroundStyle(.white)
                        }
                    }
                }
            } compactLeading: {
                Text("P\(context.state.favoriteDriverPosition)")
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundStyle(WidgetColors.phosphorGreen)
            } compactTrailing: {
                Text("L\(context.state.currentLap)/\(context.state.totalLaps)")
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(.gray)
            } minimal: {
                Text("P\(context.state.favoriteDriverPosition)")
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundStyle(WidgetColors.phosphorGreen)
            }
        }
    }

    private func lockScreenView(context: ActivityViewContext<RaceActivityAttributes>) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Circle()
                        .fill(statusColor(context.state.status))
                        .frame(width: Self.statusDot, height: Self.statusDot)
                    Text(context.attributes.session.uppercased())
                        .font(.system(size: 10, weight: .bold, design: .monospaced))
                        .foregroundStyle(.gray)
                    Text("LAP \(context.state.currentLap)/\(context.state.totalLaps)")
                        .font(.system(size: 10, weight: .medium, design: .monospaced))
                        .foregroundStyle(.gray)
                }

                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 1) {
                        Text("P1")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(WidgetColors.gold)
                        Text(context.state.leader.uppercased())
                            .font(.system(size: 14, weight: .bold, design: .monospaced))
                            .foregroundStyle(.white)
                    }
                    VStack(alignment: .leading, spacing: 1) {
                        Text("YOUR DRIVER")
                            .font(.system(size: 9, weight: .bold, design: .monospaced))
                            .foregroundStyle(WidgetColors.phosphorGreen)
                        Text("P\(context.state.favoriteDriverPosition) \(context.state.favoriteDriverName.uppercased())")
                            .font(.system(size: 14, weight: .bold, design: .monospaced))
                            .foregroundStyle(.white)
                    }
                }
            }
            Spacer()
        }
        .padding(16)
        .activityBackgroundTint(.black)
    }

    private func statusLabel(_ status: RaceActivityAttributes.ContentState.SessionStatus) -> String {
        switch status {
        case .safetycar: "SC"
        case .redflag: "RED"
        default: "LIVE"
        }
    }

    private func statusColor(_ status: RaceActivityAttributes.ContentState.SessionStatus) -> Color {
        switch status {
        case .countdown: .gray
        case .live: .green
        case .safetycar: .yellow
        case .redflag: .red
        case .finished: .gray
        }
    }
}
