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

    var dataStore: DataStore?

    init() {
        self.favoriteDriverId = UserDefaults.standard.string(forKey: AppUserDefaults.favoriteDriverId) ?? "leclerc"
        self.favoriteTeamId = UserDefaults.standard.string(forKey: AppUserDefaults.favoriteTeamId) ?? "ferrari"
    }

    var favoriteDriverName: String {
        dataStore?.driverStandings.first { $0.id == favoriteDriverId }?.driverName ?? favoriteDriverId.capitalized
    }

    var favoriteTeamName: String {
        F1Team.from(apiId: favoriteTeamId)?.displayName ?? favoriteTeamId.capitalized
    }

    var favoriteDriverStanding: DriverStanding? {
        dataStore?.driverStandings.first { $0.id == favoriteDriverId }
    }

    var favoriteDriverPrediction: DriverPrediction? {
        dataStore?.predictions.first { $0.id == favoriteDriverId }
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
