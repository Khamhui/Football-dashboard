import SwiftUI

struct OnboardingSheet: View {
    @Environment(\.dismiss) private var dismiss
    @Environment(\.terminalColors) private var colors
    @Environment(\.themeManager) private var theme
    @Environment(\.favorites) private var favorites
    @Environment(\.dataStore) private var store

    @State private var step = 0
    @State private var selectedDriver: String = "leclerc"
    @State private var selectedTeam: String = "ferrari"

    private let totalSteps = 4

    var body: some View {
        GeometryReader { geo in
            let isCompact = geo.size.height < 700

            VStack(spacing: 0) {
                if step > 0 {
                    progressBar
                }

                switch step {
                case 0: welcomeStep(isCompact: isCompact)
                case 1: whatWeDoStep(isCompact: isCompact)
                case 2: pickDriverStep
                case 3: pickTeamStep
                default: EmptyView()
                }
            }
        }
        .background(colors.bg)
    }

    // MARK: - Progress Bar

    private var progressBar: some View {
        HStack(spacing: 6) {
            ForEach(1..<totalSteps, id: \.self) { i in
                RoundedRectangle(cornerRadius: 2.5)
                    .fill(i <= step ? theme.accent : colors.border)
                    .frame(height: 5)
            }
        }
        .padding(.horizontal, 32)
        .padding(.top, 16)
    }

    // MARK: - Step 1: Welcome

    private func welcomeStep(isCompact: Bool) -> some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: isCompact ? 14 : 20) {
                Text("FORMULAI")
                    .font(.system(size: isCompact ? 26 : 32, weight: .bold, design: .monospaced))
                    .tracking(3)
                    .foregroundStyle(theme.accent)

                VStack(spacing: 8) {
                    Text("Race predictions, redefined.")
                        .font(.system(size: isCompact ? 14 : 16, weight: .semibold, design: .monospaced))
                        .foregroundStyle(colors.textBright)

                    Text("Powered by the most advanced\nprediction algorithm on mobile\nand 75 years of racing data.")
                        .font(.bodySmall)
                        .foregroundStyle(colors.textDim)
                        .multilineTextAlignment(.center)
                        .lineSpacing(4)
                }
            }

            Spacer()

            ctaButton("GET STARTED") {
                withAnimation(.easeInOut(duration: 0.3)) { step = 1 }
            }
        }
    }

    // MARK: - Step 2: What Powers FormulAI

    private func whatWeDoStep(isCompact: Bool) -> some View {
        VStack(spacing: 0) {
            Spacer()

            VStack(spacing: isCompact ? 18 : 28) {
                VStack(spacing: 8) {
                    Text("WHAT POWERS FORMULAI")
                        .font(.terminalTitle)
                        .tracking(1)
                        .foregroundStyle(colors.textBright)

                    Text("The most advanced prediction\nengine on mobile")
                        .font(.bodySmall)
                        .foregroundStyle(colors.textDim)
                        .multilineTextAlignment(.center)
                        .lineSpacing(3)
                }

                VStack(alignment: .leading, spacing: isCompact ? 16 : 24) {
                    featureRow(
                        icon: "chart.bar.doc.horizontal",
                        title: "75 years of data",
                        description: "Every race, every driver, every circuit since 1950",
                        isCompact: isCompact
                    )
                    featureRow(
                        icon: "dice",
                        title: "10,000 simulations per race",
                        description: "Monte Carlo modeling for win, podium, and points probabilities",
                        isCompact: isCompact
                    )
                    featureRow(
                        icon: "trophy",
                        title: "96.6% winner accuracy",
                        description: "Proven across hundreds of races with real results",
                        isCompact: isCompact
                    )
                    featureRow(
                        icon: "waveform.path.ecg",
                        title: "Live race predictions",
                        description: "Probabilities update every lap during qualifying and race",
                        isCompact: isCompact
                    )
                }
                .padding(.horizontal, 32)
            }

            Spacer()

            ctaButton("NEXT") {
                withAnimation(.easeInOut(duration: 0.3)) { step = 2 }
            }
        }
    }

    private func featureRow(icon: String, title: String, description: String, isCompact: Bool) -> some View {
        HStack(alignment: .top, spacing: isCompact ? 12 : 16) {
            let iconSize: CGFloat = isCompact ? 34 : 40

            Image(systemName: icon)
                .font(.system(size: isCompact ? 14 : 16, weight: .semibold))
                .foregroundStyle(theme.accent)
                .frame(width: iconSize, height: iconSize)
                .background(theme.accent.opacity(0.12))
                .clipShape(RoundedRectangle(cornerRadius: isCompact ? 8 : 10))

            VStack(alignment: .leading, spacing: isCompact ? 2 : 4) {
                Text(title)
                    .font(.system(size: isCompact ? 12 : 13, weight: .bold, design: .monospaced))
                    .foregroundStyle(colors.textBright)

                Text(description)
                    .font(.system(size: isCompact ? 10 : 11, weight: .regular, design: .default))
                    .foregroundStyle(colors.textDim)
                    .lineSpacing(isCompact ? 2 : 3)
            }
        }
    }

    // MARK: - Step 3: Pick Driver

    private var pickDriverStep: some View {
        VStack(spacing: 12) {
            VStack(spacing: 6) {
                Text("WHO'S YOUR DRIVER?")
                    .font(.terminalTitle)
                    .tracking(1)
                    .foregroundStyle(colors.textBright)

                Text("Track their performance and get\npersonalized predictions")
                    .font(.bodySmall)
                    .foregroundStyle(colors.textDim)
                    .multilineTextAlignment(.center)
            }
            .padding(.top, 20)

            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(store.driverStandings) { driver in
                        selectionRow(
                            label: driver.driverName,
                            subtitle: F1Team.from(apiId: driver.teamId)?.displayName,
                            teamId: driver.teamId,
                            isSelected: selectedDriver == driver.id,
                            accentColor: F1Team.color(forApiId: driver.teamId)
                        ) {
                            selectedDriver = driver.id
                        }
                    }
                }
                .padding(.horizontal, 16)
            }

            ctaButton("NEXT") {
                favorites.favoriteDriverId = selectedDriver
                withAnimation(.easeInOut(duration: 0.3)) { step = 3 }
            }
        }
    }

    // MARK: - Step 4: Pick Team

    private var pickTeamStep: some View {
        VStack(spacing: 12) {
            VStack(spacing: 6) {
                Text("AND YOUR TEAM?")
                    .font(.terminalTitle)
                    .tracking(1)
                    .foregroundStyle(colors.textBright)

                Text("Your home screen and widgets\nwill highlight their results")
                    .font(.bodySmall)
                    .foregroundStyle(colors.textDim)
                    .multilineTextAlignment(.center)
            }
            .padding(.top, 20)

            ScrollView {
                LazyVStack(spacing: 4) {
                    ForEach(F1Team.allCases) { team in
                        selectionRow(
                            label: team.displayName,
                            subtitle: nil,
                            teamId: team.apiId,
                            isSelected: selectedTeam == team.apiId,
                            accentColor: team.color
                        ) {
                            selectedTeam = team.apiId
                        }
                    }
                }
                .padding(.horizontal, 16)
            }

            ctaButton("LET'S GO") {
                favorites.favoriteTeamId = selectedTeam
                UserDefaults.standard.set(true, forKey: AppUserDefaults.hasCompletedOnboarding)
                dismiss()
            }
        }
    }

    // MARK: - Shared Components

    private func selectionRow(
        label: String,
        subtitle: String?,
        teamId: String,
        isSelected: Bool,
        accentColor: Color,
        action: @escaping () -> Void
    ) -> some View {
        Button { Haptics.select(); action() } label: {
            HStack(spacing: 10) {
                TeamColorBar(teamId: teamId)

                VStack(alignment: .leading, spacing: 1) {
                    Text(label)
                        .font(.terminalCaption)
                        .fontWeight(isSelected ? .bold : .regular)
                        .foregroundStyle(isSelected ? colors.textBright : colors.text)

                    if let subtitle {
                        Text(subtitle)
                            .font(.terminalMicro)
                            .foregroundStyle(colors.textDim)
                    }
                }

                Spacer()

                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 16))
                    .foregroundStyle(isSelected ? accentColor : colors.textDim)
            }
            .padding(.vertical, 10)
            .padding(.horizontal, 12)
            .background(isSelected ? accentColor.opacity(0.1) : Color.clear)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
    }

    private func ctaButton(_ label: String, action: @escaping () -> Void) -> some View {
        Button { Haptics.impact(); action() } label: {
            Text(label)
                .font(.terminalLabel)
                .tracking(1)
                .foregroundStyle(colors.bg)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(theme.accent)
                .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .padding(.horizontal, 32)
        .padding(.bottom, 24)
    }
}

#Preview("iPhone 17 Pro") {
    OnboardingSheet()
        .environment(\.themeManager, ThemeManager())
        .environment(\.favorites, FavoritesManager())
        .preferredColorScheme(.dark)
}

#Preview("Compact") {
    OnboardingSheet()
        .environment(\.themeManager, ThemeManager())
        .environment(\.favorites, FavoritesManager())
        .preferredColorScheme(.dark)
        .frame(height: 650)
}
