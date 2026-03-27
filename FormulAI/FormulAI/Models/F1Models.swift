import Foundation

// MARK: - Race Weekend

struct RaceWeekend: Identifiable, Hashable {
    let id: String
    let season: Int
    let round: Int
    let name: String
    let circuitType: CircuitType
    let date: Date?
    let hasPrediction: Bool

    var label: String { "\(season) R\(round) — \(name)" }
}

enum CircuitType: String, Codable {
    case street, highSpeed = "high_speed", technical, mixed

    var displayName: String {
        switch self {
        case .street: "Street"
        case .highSpeed: "High-Speed"
        case .technical: "Technical"
        case .mixed: "Mixed"
        }
    }
}

// MARK: - Prediction

struct DriverPrediction: Identifiable {
    let id: String
    let driverName: String
    let teamId: String
    let teamName: String
    let grid: Int?
    let predictedPosition: Double
    let simWinPct: Double
    let simPodiumPct: Double
    let simPointsPct: Double
    let simDnfPct: Double
    let simExpectedPoints: Double
    let simMedianPosition: Int
    let simPosition25: Int
    let simPosition75: Int
    let probWinnerLo: Double?
    let probWinnerHi: Double?
}

// MARK: - ELO

struct DriverELO: Identifiable {
    let id: String
    let driverName: String
    let teamId: String
    let eloOverall: Double
    let eloQualifying: Double
    let eloCircuitType: Double
    let eloConstructor: Double
    let rank: Int
    let history: [Double]
    var movementReason: String = ""

    var movementDelta: Int {
        guard history.count >= 2 else { return 0 }
        return Int(history[history.count - 1] - history[history.count - 2])
    }
}

// MARK: - Standings

struct DriverStanding: Identifiable {
    let id: String
    let driverName: String
    let teamId: String
    let position: Int
    let points: Double
    let wins: Int
}

struct ConstructorStanding: Identifiable {
    let id: String
    let teamName: String
    let position: Int
    let points: Double
    let wins: Int
}

// MARK: - Circuit Context

struct CircuitProfile {
    let gridCorrelation: Double
    let overtakingRate: Double
    let attritionRate: Double
    let gridImportance: Double
    let frontRowWinRate: Double
}

// MARK: - Race Hub

enum RaceHubSegment: String, CaseIterable {
    case circuit, predictions, live

    var label: String {
        switch self {
        case .circuit: "Circuit"
        case .predictions: "Predictions"
        case .live: "Live"
        }
    }
}

// MARK: - Circuit Info

struct CircuitInfo {
    let name: String
    let country: String
    let laps: Int
    let lengthKm: Double
    let raceDistanceKm: Double
    let lapRecord: String
    let lapRecordHolder: String
    let description: String
    let recentWinners: [RecentWinner]
}

struct PredictionInsight {
    let winnerId: String
    let whySentence: String
    let casualDescription: String
}

// MARK: - Teammate H2H

struct TeammateH2H: Identifiable {
    var id: String { "\(driver1Id)-\(driver2Id)" }
    let driver1Id: String
    let driver1Name: String
    let driver2Id: String
    let driver2Name: String
    let teamId: String
    let teamName: String
    let driver1QualiWins: Int
    let driver2QualiWins: Int
    let driver1RaceWins: Int
    let driver2RaceWins: Int
}

// MARK: - Weather Forecast

struct WeatherForecast {
    let tempC: Int
    let rainPct: Int
    let windKmh: Int
    let humidityPct: Int
}

// MARK: - Track Specialist

struct TrackSpecialist: Identifiable {
    let id: String
    let name: String
    let teamId: String
    let avgPos: Double
    let races: Int
}

// MARK: - Constructor Delta

struct ConstructorDelta: Identifiable {
    let id: String
    let teamName: String
    let teamId: String
    let delta: Double
}

// MARK: - News Headline

struct NewsHeadline: Identifiable {
    let id = UUID()
    let source: String
    let title: String
    let timeAgo: String
    var impact: String? = nil
}

// MARK: - Recent Winner

struct RecentWinner: Identifiable {
    var id: String { "\(season)-\(driver)" }
    let season: Int
    let driver: String
    let teamId: String
}

// MARK: - Session Schedule Entry

struct SessionScheduleEntry: Identifiable {
    var id: String { session }
    let session: String
    let day: String
    let time: String
}

// MARK: - Who to Watch

struct WhoToWatch: Identifiable {
    var id: String { name }
    let name: String
    let teamId: String
    let insight: String
}

// MARK: - Model Movement (probability deltas)

enum MovementMetric: String {
    case win, podium, points

    var displayName: String { rawValue }
}

struct ModelMovement: Identifiable {
    var id: String { driverId }
    let driverId: String
    let driverName: String
    let teamId: String
    let metric: MovementMetric
    let delta: Double
    let reason: String
}

// MARK: - Confidence Level

enum ConfidenceLevel: String {
    case high = "HIGH CONF"
    case moderate = "MODERATE"
    case volatile = "VOLATILE"
    case coinFlip = "COIN FLIP"
}

// MARK: - Championship Probability

struct ChampionshipProbability: Identifiable {
    let id: String
    let driverName: String
    let teamId: String
    let probability: Double
}

// MARK: - Model Accuracy (post-race scorecard)

struct RaceAccuracy: Identifiable {
    var id: String { raceName }
    let raceName: String
    let round: Int
    let winnerPredicted: String
    let winnerActual: String
    let winnerCorrect: Bool
    let podiumAccuracy: Int
    let top10Accuracy: Int
}

struct SeasonAccuracy {
    let winnerRate: Double
    let podiumRate: Double
    let top10Rate: Double
    let totalRaces: Int
}
