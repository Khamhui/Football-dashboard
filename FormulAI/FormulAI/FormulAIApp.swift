import SwiftUI

@main
struct FormulAIApp: App {
    @State private var themeManager = ThemeManager()
    @State private var favoritesManager = FavoritesManager()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environment(\.themeManager, themeManager)
                .environment(\.favorites, favoritesManager)
        }
    }
}
