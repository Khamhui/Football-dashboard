import SwiftUI

@main
struct FormulAIApp: App {
    @State private var themeManager = ThemeManager()
    @State private var favoritesManager = FavoritesManager()
    @State private var dataStore = DataStore()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.themeManager, themeManager)
                .environment(\.favorites, favoritesManager)
                .environment(\.dataStore, dataStore)
                .task {
                    favoritesManager.dataStore = dataStore
                    await dataStore.fetchAll()
                }
        }
    }
}
