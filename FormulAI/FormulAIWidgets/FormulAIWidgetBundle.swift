import SwiftUI
import WidgetKit

@main
struct FormulAIWidgetBundle: WidgetBundle {
    var body: some Widget {
        NextRaceWidget()
        FavoriteDriverWidget()
        DriverStandingsWidget()
        RaceCalendarWidget()
        RaceLiveActivity()
    }
}
