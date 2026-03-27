import SwiftUI

struct RaceSelector: View {
    @Binding var selected: RaceWeekend
    let weekends: [RaceWeekend]

    @Environment(\.terminalColors) private var colors

    var body: some View {
        Menu {
            ForEach(weekends) { weekend in
                Button {
                    selected = weekend
                } label: {
                    HStack {
                        Text(weekend.label)
                        if weekend.hasPrediction {
                            Text("★")
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 6) {
                VStack(alignment: .leading, spacing: 1) {
                    Text(selected.name)
                        .font(.terminalCaption)
                        .fontWeight(.semibold)
                        .foregroundStyle(colors.cyan)

                    HStack(spacing: 6) {
                        Text("\(selected.season) R\(selected.round)")
                            .font(.terminalLabel)
                            .foregroundStyle(colors.textDim)

                        CircuitBadge(type: selected.circuitType)
                    }
                }

                Image(systemName: "chevron.up.chevron.down")
                    .font(.system(size: 10))
                    .foregroundStyle(colors.textDim)
            }
        }
    }
}
