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
    @State private var selectedWeekend: RaceWeekend?
    @State private var showSettings = false
    @State private var showOnboarding = !UserDefaults.standard.bool(forKey: AppUserDefaults.hasCompletedOnboarding)
    @State private var layout = TerminalLayout.default
    @State private var showScanLine = true

    @Environment(\.colorScheme) private var scheme
    @Environment(\.themeManager) private var theme
    @Environment(\.dataStore) private var store

    private var currentWeekend: RaceWeekend {
        selectedWeekend ?? store.races.last ?? MockData.raceWeekends[0]
    }

    var body: some View {
        let colors = theme.colors(for: scheme)

        VStack(spacing: 0) {
            topBar(colors)

            TabView(selection: $selectedTab) {
                Tab(AppTab.home.label, systemImage: AppTab.home.icon, value: .home) {
                    HomeTab(weekend: currentWeekend)
                }

                Tab(AppTab.raceHub.label, systemImage: AppTab.raceHub.icon, value: .raceHub) {
                    RaceHubTab(weekend: currentWeekend)
                }

                Tab(AppTab.insights.label, systemImage: AppTab.insights.icon, value: .insights) {
                    InsightsTab(weekend: currentWeekend)
                }

                Tab(AppTab.standings.label, systemImage: AppTab.standings.icon, value: .standings) {
                    StandingsTab(weekend: currentWeekend)
                }
            }
            .tint(theme.accent)
        }
        .background(colors.bg)
        .overlay { if showScanLine { BootScanLine(color: theme.accent) } }
        .environment(\.terminalColors, colors)
        .environment(\.terminalLayout, layout)
        .onGeometryChange(for: CGFloat.self, of: { geo in
            geo.size.width
        }, action: { width in
            let newLayout = TerminalLayout(screenWidth: width)
            if newLayout != layout { layout = newLayout }
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
                selected: Binding(
                    get: { currentWeekend },
                    set: { selectedWeekend = $0 }
                ),
                weekends: store.races.isEmpty ? MockData.raceWeekends : store.races
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
