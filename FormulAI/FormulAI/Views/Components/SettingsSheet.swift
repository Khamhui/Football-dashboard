import SwiftUI

struct SettingsSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.favorites) private var favorites

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    favoritesSection
                    personalSection
                    aboutSection
                }
                .padding(16)
            }
            .background(colors.bg)
            .navigationTitle("Settings")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { dismiss() } label: {
                        Image(systemName: "xmark")
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundStyle(colors.textDim)
                    }
                }
            }
        }
    }

    // MARK: - Favorites

    private var favoritesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("YOUR FAVORITES")
                .font(.terminalLabel)
                .tracking(1)
                .foregroundStyle(colors.textDim)

            HStack(spacing: 12) {
                favoriteCard(
                    label: "DRIVER",
                    value: favorites.favoriteDriverName,
                    teamId: favorites.favoriteDriverStanding?.teamId ?? favorites.favoriteTeamId
                ) {
                    driverPicker
                }

                favoriteCard(
                    label: "TEAM",
                    value: favorites.favoriteTeamName,
                    teamId: favorites.favoriteTeamId
                ) {
                    teamPicker
                }
            }
        }
    }

    private func favoriteCard<MenuContent: View>(
        label: String, value: String, teamId: String,
        @ViewBuilder menu: () -> MenuContent
    ) -> some View {
        Menu {
            menu()
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text(label)
                    .font(.terminalMicro)
                    .tracking(0.5)
                    .foregroundStyle(colors.textDim)

                HStack(spacing: 6) {
                    TeamColorBar(teamId: teamId)
                    Text(value)
                        .font(.terminalCaption)
                        .fontWeight(.semibold)
                        .foregroundStyle(colors.textBright)
                }

                Text("Change")
                    .font(.terminalMicro)
                    .foregroundStyle(theme.accent)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(colors.bgPanel)
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(F1Team.color(forApiId: teamId).opacity(0.4), lineWidth: 1)
            )
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    @ViewBuilder
    private var driverPicker: some View {
        ForEach(MockData.driverStandings) { driver in
            Button {
                favorites.favoriteDriverId = driver.id
            } label: {
                HStack {
                    Text(driver.driverName)
                    if driver.id == favorites.favoriteDriverId {
                        Image(systemName: "checkmark")
                    }
                }
            }
        }
    }

    @ViewBuilder
    private var teamPicker: some View {
        ForEach(F1Team.allCases) { team in
            Button {
                favorites.favoriteTeamId = team.apiId
            } label: {
                HStack {
                    Text(team.displayName)
                    if team.apiId == favorites.favoriteTeamId {
                        Image(systemName: "checkmark")
                    }
                }
            }
        }
    }

    // MARK: - Personal

    private var personalSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("PERSONAL")
                .font(.terminalLabel)
                .tracking(1)
                .foregroundStyle(colors.textDim)

            settingsRow(icon: "clock", label: "Timezone", value: TimeZone.current.abbreviation() ?? "UTC")

            Menu {
                ForEach(AppearanceMode.allCases, id: \.self) { mode in
                    Button {
                        theme.appearanceMode = mode
                    } label: {
                        HStack {
                            Text(mode.label)
                            if mode == theme.appearanceMode {
                                Image(systemName: "checkmark")
                            }
                        }
                    }
                }
            } label: {
                settingsRow(icon: "paintbrush", label: "Theme", value: theme.appearanceMode.label)
            }

            settingsRow(icon: "heart.fill", label: "FormulAI Pro", value: "Activate", valueColor: theme.accent)
        }
    }

    // MARK: - About

    private var aboutSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("ABOUT")
                .font(.terminalLabel)
                .tracking(1)
                .foregroundStyle(colors.textDim)

            settingsRow(icon: "envelope", label: "Contact Us", value: "")
            settingsRow(icon: "star", label: "Rate FormulAI", value: "")
            settingsRow(icon: "lock.shield", label: "Privacy Policy", value: "")

            HStack {
                Spacer()
                VStack(spacing: 4) {
                    Text("FORMULAI")
                        .font(.terminalTitle)
                        .tracking(1)
                        .foregroundStyle(theme.accent)
                    Text("v1.0.0")
                        .font(.terminalMicro)
                        .foregroundStyle(colors.textDim)
                }
                Spacer()
            }
            .padding(.top, 12)
        }
    }

    private func settingsRow(icon: String, label: String, value: String, valueColor: Color? = nil) -> some View {
        HStack {
            Image(systemName: icon)
                .font(.system(size: 14))
                .foregroundStyle(colors.textDim)
                .frame(width: 24)

            Text(label)
                .font(.bodyCaption)
                .foregroundStyle(colors.text)

            Spacer()

            if !value.isEmpty {
                Text(value)
                    .font(.bodyCaption)
                    .foregroundStyle(valueColor ?? colors.textDim)
            }

            Image(systemName: "chevron.right")
                .font(.system(size: 10))
                .foregroundStyle(colors.textDim)
        }
        .padding(.vertical, 8)
        .padding(.horizontal, 12)
        .background(colors.bgPanel)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}

#Preview {
    SettingsSheet()
        .environment(\.themeManager, ThemeManager())
        .environment(\.favorites, FavoritesManager())
        .preferredColorScheme(.dark)
}
