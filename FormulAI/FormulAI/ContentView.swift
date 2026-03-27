import SwiftUI

enum AppTab: String, CaseIterable {
    case home, raceHub, insights, standings

    var label: String {
        switch self {
        case .home: "Home"
        case .raceHub: "Race Hub"
        case .insights: "Insights"
        case .standings: "Standings"
        }
    }

    var icon: String {
        switch self {
        case .home: "house.fill"
        case .raceHub: "flag.checkered"
        case .insights: "chart.xyaxis.line"
        case .standings: "chart.bar.fill"
        }
    }
}

struct ContentView: View {
    @State private var selectedTab: AppTab = .home
    @State private var selectedWeekend: RaceWeekend = MockData.raceWeekends[0]
    @State private var showSettings = false
    @State private var showOnboarding = !UserDefaults.standard.bool(forKey: AppUserDefaults.hasCompletedOnboarding)
    @State private var layout = TerminalLayout.default
    @State private var showScanLine = true

    @Environment(\.colorScheme) private var scheme
    @Environment(\.themeManager) private var theme

    var body: some View {
        let colors = theme.colors(for: scheme)

        VStack(spacing: 0) {
            topBar(colors)

            TabView(selection: $selectedTab) {
                Tab(AppTab.home.label, systemImage: AppTab.home.icon, value: .home) {
                    HomeTab(weekend: selectedWeekend)
                }

                Tab(AppTab.raceHub.label, systemImage: AppTab.raceHub.icon, value: .raceHub) {
                    RaceHubTab(weekend: selectedWeekend)
                }

                Tab(AppTab.insights.label, systemImage: AppTab.insights.icon, value: .insights) {
                    InsightsTab(weekend: selectedWeekend)
                }

                Tab(AppTab.standings.label, systemImage: AppTab.standings.icon, value: .standings) {
                    StandingsTab(weekend: selectedWeekend)
                }
            }
            .tint(theme.accent)
        }
        .background(colors.bg)
        .overlay { if showScanLine { BootScanLine(color: theme.accent) } }
        .environment(\.terminalColors, colors)
        .environment(\.terminalLayout, layout)
        .onGeometryChange(for: Bool.self, of: { geo in
            geo.size.width < 380
        }, action: { isCompact in
            layout = TerminalLayout(screenWidth: isCompact ? 370 : 393)
        })
        .preferredColorScheme(theme.appearanceMode.colorScheme)
        .task {
            try? await Task.sleep(for: .seconds(1))
            showScanLine = false
        }
        .sheet(isPresented: $showSettings) {
            SettingsSheet()
        }
        .fullScreenCover(isPresented: $showOnboarding) {
            OnboardingSheet()
        }
    }

    private func topBar(_ colors: TerminalColors) -> some View {
        HStack {
            Text("FORMULAI")
                .font(.terminalTitle)
                .tracking(1)
                .foregroundStyle(theme.accent)

            Spacer()

            RaceSelector(
                selected: $selectedWeekend,
                weekends: MockData.raceWeekends
            )

            Button { showSettings = true } label: {
                Image(systemName: "gearshape")
                    .font(.system(size: 15))
                    .foregroundStyle(colors.textDim)
            }
            .padding(.leading, 8)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(colors.bgPanel)
        .overlay(alignment: .bottom) {
            TerminalDivider()
        }
    }
}

#Preview("Dark") {
    ContentView()
        .environment(\.themeManager, ThemeManager())
        .environment(\.favorites, FavoritesManager())
        .preferredColorScheme(.dark)
}

#Preview("Light") {
    ContentView()
        .environment(\.themeManager, ThemeManager())
        .environment(\.favorites, FavoritesManager())
        .preferredColorScheme(.light)
}
