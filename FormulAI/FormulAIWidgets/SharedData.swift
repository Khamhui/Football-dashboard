import Foundation
import SwiftUI

enum WidgetColors {
    static let phosphorGreen = Color(red: 0.314, green: 0.784, blue: 0.471)
    static let gold = Color(red: 1, green: 0.84, blue: 0)
    static let silver = Color(red: 0.75, green: 0.75, blue: 0.75)
    static let bronze = Color(red: 0.8, green: 0.5, blue: 0.2)
    static let terminalGreen = Color(red: 0, green: 1, blue: 0.53)
    static let cancelRed = Color(red: 1, green: 0.2, blue: 0.33)

    static func positionColor(_ position: Int) -> Color {
        switch position {
        case 1: gold
        case 2: silver
        case 3: bronze
        default: .white
        }
    }
}

enum WidgetData {

    // MARK: - Favorite Driver/Team

    static var favoriteDriverId: String {
        UserDefaults.standard.string(forKey: "favoriteDriverId") ?? "leclerc"
    }

    static var favoriteTeamId: String {
        UserDefaults.standard.string(forKey: "favoriteTeamId") ?? "ferrari"
    }

    // MARK: - Next Race

    struct NextRace {
        let name: String
        let round: Int
        let season: Int
        let circuitType: String
        let daysUntil: Int
        let hoursUntil: Int
    }

    static let nextRace = NextRace(
        name: "Japanese Grand Prix",
        round: 3,
        season: 2026,
        circuitType: "Technical",
        daysUntil: 3,
        hoursUntil: 20
    )

    // MARK: - Driver Standings

    struct StandingEntry: Identifiable {
        let id: String
        let name: String
        let teamColorHex: UInt
        let points: Int
        let position: Int
    }

    static let driverStandings: [StandingEntry] = [
        StandingEntry(id: "russell", name: "Russell", teamColorHex: 0x00D2BE, points: 51, position: 1),
        StandingEntry(id: "antonelli", name: "Antonelli", teamColorHex: 0x00D2BE, points: 47, position: 2),
        StandingEntry(id: "leclerc", name: "Leclerc", teamColorHex: 0xDC0000, points: 34, position: 3),
        StandingEntry(id: "hamilton", name: "Hamilton", teamColorHex: 0xDC0000, points: 33, position: 4),
        StandingEntry(id: "bearman", name: "Bearman", teamColorHex: 0xB6BABD, points: 17, position: 5),
        StandingEntry(id: "norris", name: "Norris", teamColorHex: 0xFF8700, points: 15, position: 6),
        StandingEntry(id: "gasly", name: "Gasly", teamColorHex: 0x0090FF, points: 9, position: 7),
        StandingEntry(id: "verstappen", name: "Verstappen", teamColorHex: 0x3671C6, points: 8, position: 8),
        StandingEntry(id: "lawson", name: "Lawson", teamColorHex: 0x3671C6, points: 8, position: 9),
        StandingEntry(id: "lindblad", name: "Lindblad", teamColorHex: 0x6692FF, points: 4, position: 10),
    ]

    // MARK: - Race Calendar

    struct CalendarEntry: Identifiable {
        let id: String
        let round: Int
        let name: String
        let shortName: String
        let dateRange: String
        let isCompleted: Bool
        let isCancelled: Bool
        let isNext: Bool
    }

    static let calendar: [CalendarEntry] = [
        CalendarEntry(id: "r1", round: 1, name: "Australian Grand Prix", shortName: "AUS", dateRange: "MAR 8-10", isCompleted: true, isCancelled: false, isNext: false),
        CalendarEntry(id: "r2", round: 2, name: "Chinese Grand Prix", shortName: "CHN", dateRange: "MAR 15-17", isCompleted: true, isCancelled: false, isNext: false),
        CalendarEntry(id: "r3", round: 3, name: "Japanese Grand Prix", shortName: "JPN", dateRange: "MAR 27-29", isCompleted: false, isCancelled: false, isNext: true),
        CalendarEntry(id: "r4", round: 4, name: "Bahrain Grand Prix", shortName: "BHR", dateRange: "APR 12-14", isCompleted: false, isCancelled: false, isNext: false),
        CalendarEntry(id: "r5", round: 5, name: "Saudi Arabian Grand Prix", shortName: "KSA", dateRange: "APR 19-21", isCompleted: false, isCancelled: true, isNext: false),
        CalendarEntry(id: "r6", round: 6, name: "Miami Grand Prix", shortName: "MIA", dateRange: "MAY 3-5", isCompleted: false, isCancelled: false, isNext: false),
    ]
}
