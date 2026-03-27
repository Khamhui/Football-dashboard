import SwiftUI

enum AppUserDefaults {
    static let favoriteDriverId = "favoriteDriverId"
    static let favoriteTeamId = "favoriteTeamId"
    static let hasCompletedOnboarding = "hasCompletedOnboarding"
}

@Observable
final class FavoritesManager {
    var favoriteDriverId: String {
        didSet { UserDefaults.standard.set(favoriteDriverId, forKey: AppUserDefaults.favoriteDriverId) }
    }

    var favoriteTeamId: String {
        didSet { UserDefaults.standard.set(favoriteTeamId, forKey: AppUserDefaults.favoriteTeamId) }
    }

    private static let standingsById: [String: DriverStanding] = {
        Dictionary(uniqueKeysWithValues: MockData.driverStandings.map { ($0.id, $0) })
    }()

    private static let predictionsById: [String: DriverPrediction] = {
        Dictionary(uniqueKeysWithValues: MockData.predictions.map { ($0.id, $0) })
    }()

    init() {
        self.favoriteDriverId = UserDefaults.standard.string(forKey: AppUserDefaults.favoriteDriverId) ?? "leclerc"
        self.favoriteTeamId = UserDefaults.standard.string(forKey: AppUserDefaults.favoriteTeamId) ?? "ferrari"
    }

    var favoriteDriverName: String {
        Self.standingsById[favoriteDriverId]?.driverName ?? favoriteDriverId.capitalized
    }

    var favoriteTeamName: String {
        F1Team.from(apiId: favoriteTeamId)?.displayName ?? favoriteTeamId.capitalized
    }

    var favoriteDriverStanding: DriverStanding? {
        Self.standingsById[favoriteDriverId]
    }

    var favoriteDriverPrediction: DriverPrediction? {
        Self.predictionsById[favoriteDriverId]
    }
}

private struct FavoritesManagerKey: EnvironmentKey {
    static let defaultValue = FavoritesManager()
}

extension EnvironmentValues {
    var favorites: FavoritesManager {
        get { self[FavoritesManagerKey.self] }
        set { self[FavoritesManagerKey.self] = newValue }
    }
}
