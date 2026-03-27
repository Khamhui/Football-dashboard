import ActivityKit
import Foundation

struct RaceActivityAttributes: ActivityAttributes {
    let raceName: String
    let round: Int
    let session: String

    struct ContentState: Codable, Hashable {
        let leader: String
        let leaderTeamId: String
        let favoriteDriverPosition: Int
        let favoriteDriverName: String
        let favoriteDriverTeamId: String
        let currentLap: Int
        let totalLaps: Int
        let status: SessionStatus
        let lastUpdate: Date

        enum SessionStatus: String, Codable, Hashable {
            case countdown
            case live
            case safetycar
            case redflag
            case finished
        }
    }
}
