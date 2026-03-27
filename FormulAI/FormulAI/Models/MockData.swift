import Foundation

// MARK: - Mock Data from Real Pipeline (2026 Season — updated March 24)

enum MockData {

    // MARK: Race Weekends

    static let raceWeekends: [RaceWeekend] = [
        RaceWeekend(id: "2026_3", season: 2026, round: 3, name: "Japanese Grand Prix", circuitType: .technical, date: nil, hasPrediction: true),
        RaceWeekend(id: "2026_2", season: 2026, round: 2, name: "Chinese Grand Prix", circuitType: .mixed, date: nil, hasPrediction: false),
        RaceWeekend(id: "2026_1", season: 2026, round: 1, name: "Australian Grand Prix", circuitType: .street, date: nil, hasPrediction: false),
    ]

    // MARK: Predictions (R03 — Japanese GP — from real pipeline)

    static let predictions: [DriverPrediction] = [
        DriverPrediction(id: "leclerc", driverName: "Leclerc", teamId: "ferrari", teamName: "Ferrari", grid: nil, predictedPosition: 7.1, simWinPct: 24.4, simPodiumPct: 51.8, simPointsPct: 80.0, simDnfPct: 18.6, simExpectedPoints: 13.0, simMedianPosition: 3, simPosition25: 1, simPosition75: 6, probWinnerLo: 0.18, probWinnerHi: 0.31),
        DriverPrediction(id: "antonelli", driverName: "Antonelli", teamId: "mercedes", teamName: "Mercedes", grid: nil, predictedPosition: 7.9, simWinPct: 15.0, simPodiumPct: 41.5, simPointsPct: 83.1, simDnfPct: 14.4, simExpectedPoints: 11.5, simMedianPosition: 4, simPosition25: 2, simPosition75: 7, probWinnerLo: 0.09, probWinnerHi: 0.21),
        DriverPrediction(id: "russell", driverName: "Russell", teamId: "mercedes", teamName: "Mercedes", grid: nil, predictedPosition: 7.9, simWinPct: 13.7, simPodiumPct: 38.9, simPointsPct: 75.4, simDnfPct: 22.4, simExpectedPoints: 10.6, simMedianPosition: 3, simPosition25: 2, simPosition75: 8, probWinnerLo: 0.08, probWinnerHi: 0.20),
        DriverPrediction(id: "hadjar", driverName: "Hadjar", teamId: "rb", teamName: "RB", grid: nil, predictedPosition: 9.1, simWinPct: 6.4, simPodiumPct: 22.4, simPointsPct: 70.3, simDnfPct: 25.3, simExpectedPoints: 7.8, simMedianPosition: 5, simPosition25: 3, simPosition75: 9, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "bearman", driverName: "Bearman", teamId: "haas", teamName: "Haas", grid: nil, predictedPosition: 8.0, simWinPct: 10.0, simPodiumPct: 26.9, simPointsPct: 56.7, simDnfPct: 41.3, simExpectedPoints: 7.6, simMedianPosition: 4, simPosition25: 2, simPosition75: 8, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "lawson", driverName: "Lawson", teamId: "red_bull", teamName: "Red Bull", grid: nil, predictedPosition: 8.5, simWinPct: 8.0, simPodiumPct: 24.4, simPointsPct: 60.3, simDnfPct: 37.1, simExpectedPoints: 7.5, simMedianPosition: 4, simPosition25: 2, simPosition75: 9, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "hamilton", driverName: "Hamilton", teamId: "ferrari", teamName: "Ferrari", grid: nil, predictedPosition: 9.8, simWinPct: 3.8, simPodiumPct: 17.0, simPointsPct: 73.7, simDnfPct: 18.6, simExpectedPoints: 6.9, simMedianPosition: 6, simPosition25: 3, simPosition75: 10, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "norris", driverName: "Norris", teamId: "mclaren", teamName: "McLaren", grid: nil, predictedPosition: 8.6, simWinPct: 6.3, simPodiumPct: 21.2, simPointsPct: 56.2, simDnfPct: 40.9, simExpectedPoints: 6.6, simMedianPosition: 5, simPosition25: 3, simPosition75: 9, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "piastri", driverName: "Piastri", teamId: "mclaren", teamName: "McLaren", grid: nil, predictedPosition: 9.4, simWinPct: 3.6, simPodiumPct: 14.0, simPointsPct: 52.5, simDnfPct: 42.3, simExpectedPoints: 5.2, simMedianPosition: 6, simPosition25: 3, simPosition75: 10, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "max_verstappen", driverName: "Verstappen", teamId: "red_bull", teamName: "Red Bull", grid: nil, predictedPosition: 11.6, simWinPct: 0.8, simPodiumPct: 5.7, simPointsPct: 62.3, simDnfPct: 19.8, simExpectedPoints: 4.0, simMedianPosition: 8, simPosition25: 5, simPosition75: 13, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "gasly", driverName: "Gasly", teamId: "alpine", teamName: "Alpine", grid: nil, predictedPosition: 8.5, simWinPct: 3.0, simPodiumPct: 8.9, simPointsPct: 23.8, simDnfPct: 74.5, simExpectedPoints: 2.8, simMedianPosition: 5, simPosition25: 3, simPosition75: 9, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "ocon", driverName: "Ocon", teamId: "haas", teamName: "Haas", grid: nil, predictedPosition: 10.9, simWinPct: 0.7, simPodiumPct: 4.3, simPointsPct: 33.8, simDnfPct: 58.3, simExpectedPoints: 2.4, simMedianPosition: 8, simPosition25: 5, simPosition75: 13, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "hulkenberg", driverName: "Hulkenberg", teamId: "audi", teamName: "Audi", grid: nil, predictedPosition: 9.5, simWinPct: 1.6, simPodiumPct: 6.3, simPointsPct: 22.7, simDnfPct: 74.4, simExpectedPoints: 2.3, simMedianPosition: 6, simPosition25: 4, simPosition75: 10, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "arvid_lindblad", driverName: "Lindblad", teamId: "rb", teamName: "RB", grid: nil, predictedPosition: 12.0, simWinPct: 0.4, simPodiumPct: 2.8, simPointsPct: 35.3, simDnfPct: 50.3, simExpectedPoints: 2.1, simMedianPosition: 9, simPosition25: 6, simPosition75: 14, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "alonso", driverName: "Alonso", teamId: "aston_martin", teamName: "Aston Martin", grid: nil, predictedPosition: 10.8, simWinPct: 0.8, simPodiumPct: 4.2, simPointsPct: 25.8, simDnfPct: 67.6, simExpectedPoints: 2.0, simMedianPosition: 8, simPosition25: 5, simPosition75: 13, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "colapinto", driverName: "Colapinto", teamId: "alpine", teamName: "Alpine", grid: nil, predictedPosition: 10.4, simWinPct: 0.7, simPodiumPct: 3.4, simPointsPct: 19.5, simDnfPct: 76.1, simExpectedPoints: 1.6, simMedianPosition: 7, simPosition25: 5, simPosition75: 12, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "bortoleto", driverName: "Bortoleto", teamId: "audi", teamName: "Audi", grid: nil, predictedPosition: 11.0, simWinPct: 0.4, simPodiumPct: 2.5, simPointsPct: 19.8, simDnfPct: 74.1, simExpectedPoints: 1.4, simMedianPosition: 8, simPosition25: 6, simPosition75: 13, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "sainz", driverName: "Sainz", teamId: "williams", teamName: "Williams", grid: nil, predictedPosition: 12.2, simWinPct: 0.2, simPodiumPct: 1.6, simPointsPct: 22.2, simDnfPct: 68.1, simExpectedPoints: 1.3, simMedianPosition: 9, simPosition25: 7, simPosition75: 14, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "stroll", driverName: "Stroll", teamId: "aston_martin", teamName: "Aston Martin", grid: nil, predictedPosition: 12.3, simWinPct: 0.2, simPodiumPct: 1.5, simPointsPct: 20.7, simDnfPct: 68.1, simExpectedPoints: 1.2, simMedianPosition: 9, simPosition25: 7, simPosition75: 15, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "albon", driverName: "Albon", teamId: "williams", teamName: "Williams", grid: nil, predictedPosition: 14.3, simWinPct: 0.0, simPodiumPct: 0.4, simPointsPct: 15.2, simDnfPct: 68.4, simExpectedPoints: 0.6, simMedianPosition: 11, simPosition25: 8, simPosition75: 17, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "bottas", driverName: "Bottas", teamId: "cadillac", teamName: "Cadillac", grid: nil, predictedPosition: 13.4, simWinPct: 0.0, simPodiumPct: 0.2, simPointsPct: 4.4, simDnfPct: 92.2, simExpectedPoints: 0.2, simMedianPosition: 10, simPosition25: 8, simPosition75: 16, probWinnerLo: nil, probWinnerHi: nil),
        DriverPrediction(id: "perez", driverName: "Perez", teamId: "cadillac", teamName: "Cadillac", grid: nil, predictedPosition: 13.3, simWinPct: 0.0, simPodiumPct: 0.1, simPointsPct: 4.3, simDnfPct: 92.3, simExpectedPoints: 0.2, simMedianPosition: 10, simPosition25: 8, simPosition75: 16, probWinnerLo: nil, probWinnerHi: nil),
    ]

    // MARK: ELO Rankings (from feature matrix)

    static let eloRankings: [DriverELO] = [
        DriverELO(id: "leclerc", driverName: "Leclerc", teamId: "ferrari", eloOverall: 2072, eloQualifying: 2090, eloCircuitType: 2055, eloConstructor: 2045, rank: 1, history: [2060, 2058, 2062, 2065, 2068, 2070, 2069, 2071, 2072, 2075], movementReason: "Strong qualifying pace"),
        DriverELO(id: "russell", driverName: "Russell", teamId: "mercedes", eloOverall: 2058, eloQualifying: 2065, eloCircuitType: 2040, eloConstructor: 2050, rank: 2, history: [2020, 2025, 2030, 2035, 2040, 2045, 2050, 2053, 2056, 2058], movementReason: "Consistent race finishes"),
        DriverELO(id: "antonelli", driverName: "Antonelli", teamId: "mercedes", eloOverall: 2045, eloQualifying: 2040, eloCircuitType: 2030, eloConstructor: 2050, rank: 3, history: [1980, 1995, 2005, 2015, 2020, 2028, 2035, 2040, 2043, 2045], movementReason: "Podium in Australia"),
        DriverELO(id: "hamilton", driverName: "Hamilton", teamId: "ferrari", eloOverall: 2040, eloQualifying: 2035, eloCircuitType: 2060, eloConstructor: 2045, rank: 4, history: [2070, 2065, 2060, 2058, 2055, 2050, 2048, 2045, 2042, 2040], movementReason: "Improved race pace"),
        DriverELO(id: "norris", driverName: "Norris", teamId: "mclaren", eloOverall: 2035, eloQualifying: 2040, eloCircuitType: 2020, eloConstructor: 2015, rank: 5, history: [2050, 2048, 2045, 2042, 2040, 2038, 2037, 2036, 2035, 2035], movementReason: "Solid points haul"),
        DriverELO(id: "max_verstappen", driverName: "Verstappen", teamId: "red_bull", eloOverall: 2030, eloQualifying: 2050, eloCircuitType: 2025, eloConstructor: 1980, rank: 6, history: [2120, 2110, 2095, 2080, 2070, 2060, 2050, 2045, 2038, 2030], movementReason: "Challenging start to season"),
    ]

    // MARK: Driver Standings (after R02 — China)

    static let driverStandings: [DriverStanding] = [
        DriverStanding(id: "russell", driverName: "Russell", teamId: "mercedes", position: 1, points: 51, wins: 1),
        DriverStanding(id: "antonelli", driverName: "Antonelli", teamId: "mercedes", position: 2, points: 47, wins: 1),
        DriverStanding(id: "leclerc", driverName: "Leclerc", teamId: "ferrari", position: 3, points: 34, wins: 0),
        DriverStanding(id: "hamilton", driverName: "Hamilton", teamId: "ferrari", position: 4, points: 33, wins: 0),
        DriverStanding(id: "bearman", driverName: "Bearman", teamId: "haas", position: 5, points: 17, wins: 0),
        DriverStanding(id: "norris", driverName: "Norris", teamId: "mclaren", position: 6, points: 15, wins: 0),
        DriverStanding(id: "gasly", driverName: "Gasly", teamId: "alpine", position: 7, points: 9, wins: 0),
        DriverStanding(id: "max_verstappen", driverName: "Verstappen", teamId: "red_bull", position: 8, points: 8, wins: 0),
        DriverStanding(id: "lawson", driverName: "Lawson", teamId: "red_bull", position: 9, points: 8, wins: 0),
        DriverStanding(id: "arvid_lindblad", driverName: "Lindblad", teamId: "rb", position: 10, points: 4, wins: 0),
    ]

    // MARK: Constructor Standings (after R02 — China)

    static let constructorStandings: [ConstructorStanding] = [
        ConstructorStanding(id: "mercedes", teamName: "Mercedes", position: 1, points: 98, wins: 2),
        ConstructorStanding(id: "ferrari", teamName: "Ferrari", position: 2, points: 67, wins: 0),
        ConstructorStanding(id: "mclaren", teamName: "McLaren", position: 3, points: 18, wins: 0),
        ConstructorStanding(id: "haas", teamName: "Haas", position: 4, points: 17, wins: 0),
        ConstructorStanding(id: "red_bull", teamName: "Red Bull", position: 5, points: 12, wins: 0),
        ConstructorStanding(id: "rb", teamName: "RB", position: 6, points: 12, wins: 0),
        ConstructorStanding(id: "alpine", teamName: "Alpine", position: 7, points: 10, wins: 0),
        ConstructorStanding(id: "audi", teamName: "Audi", position: 8, points: 2, wins: 0),
        ConstructorStanding(id: "williams", teamName: "Williams", position: 9, points: 2, wins: 0),
        ConstructorStanding(id: "cadillac", teamName: "Cadillac", position: 10, points: 0, wins: 0),
    ]

    // MARK: Prediction Insight (R03 — Japanese GP)

    static let predictionInsight = PredictionInsight(
        winnerId: "leclerc",
        whySentence: "Ferrari's technical circuit mastery and Leclerc's qualifying edge give him a clear advantage at Suzuka",
        casualDescription: "About 1 in 4 chance of winning"
    )

    // MARK: Teammate H2H (after R02)

    static let teammateH2H: [TeammateH2H] = [
        TeammateH2H(driver1Id: "russell", driver1Name: "Russell", driver2Id: "antonelli", driver2Name: "Antonelli", teamId: "mercedes", teamName: "Mercedes", driver1QualiWins: 1, driver2QualiWins: 1, driver1RaceWins: 1, driver2RaceWins: 1),
        TeammateH2H(driver1Id: "leclerc", driver1Name: "Leclerc", driver2Id: "hamilton", driver2Name: "Hamilton", teamId: "ferrari", teamName: "Ferrari", driver1QualiWins: 2, driver2QualiWins: 0, driver1RaceWins: 1, driver2RaceWins: 1),
        TeammateH2H(driver1Id: "norris", driver1Name: "Norris", driver2Id: "piastri", driver2Name: "Piastri", teamId: "mclaren", teamName: "McLaren", driver1QualiWins: 1, driver2QualiWins: 1, driver1RaceWins: 1, driver2RaceWins: 1),
        TeammateH2H(driver1Id: "max_verstappen", driver1Name: "Verstappen", driver2Id: "lawson", driver2Name: "Lawson", teamId: "red_bull", teamName: "Red Bull", driver1QualiWins: 1, driver2QualiWins: 1, driver1RaceWins: 0, driver2RaceWins: 2),
        TeammateH2H(driver1Id: "bearman", driver1Name: "Bearman", driver2Id: "ocon", driver2Name: "Ocon", teamId: "haas", teamName: "Haas", driver1QualiWins: 2, driver2QualiWins: 0, driver1RaceWins: 2, driver2RaceWins: 0),
    ]

    // MARK: Championship Probabilities (simulated)

    static let championshipProbabilities: [ChampionshipProbability] = [
        ChampionshipProbability(id: "russell", driverName: "Russell", teamId: "mercedes", probability: 28.5),
        ChampionshipProbability(id: "antonelli", driverName: "Antonelli", teamId: "mercedes", probability: 24.2),
        ChampionshipProbability(id: "leclerc", driverName: "Leclerc", teamId: "ferrari", probability: 19.8),
        ChampionshipProbability(id: "hamilton", driverName: "Hamilton", teamId: "ferrari", probability: 12.1),
        ChampionshipProbability(id: "norris", driverName: "Norris", teamId: "mclaren", probability: 6.4),
        ChampionshipProbability(id: "bearman", driverName: "Bearman", teamId: "haas", probability: 3.8),
    ]

    // MARK: Circuit Profile (Japanese GP — Suzuka)

    static let circuitProfile = CircuitProfile(
        gridCorrelation: 0.72,
        overtakingRate: 0.34,
        attritionRate: 0.12,
        gridImportance: 0.68,
        frontRowWinRate: 0.81
    )

    // MARK: Weather (Japanese GP — Suzuka)

    static let weather = WeatherForecast(tempC: 24, rainPct: 15, windKmh: 12, humidityPct: 62)

    // MARK: Track Specialists (Suzuka)

    static let trackSpecialists: [TrackSpecialist] = [
        TrackSpecialist(id: "max_verstappen", name: "Verstappen", teamId: "red_bull", avgPos: 1.8, races: 3),
        TrackSpecialist(id: "hamilton", name: "Hamilton", teamId: "ferrari", avgPos: 2.1, races: 8),
        TrackSpecialist(id: "leclerc", name: "Leclerc", teamId: "ferrari", avgPos: 3.2, races: 4),
        TrackSpecialist(id: "norris", name: "Norris", teamId: "mclaren", avgPos: 3.5, races: 2),
        TrackSpecialist(id: "piastri", name: "Piastri", teamId: "mclaren", avgPos: 4.1, races: 2),
    ]

    // MARK: Constructor Deltas (vs prev round)

    static let constructorDeltas: [ConstructorDelta] = [
        ConstructorDelta(id: "mercedes", teamName: "Mercedes", teamId: "mercedes", delta: 12.5),
        ConstructorDelta(id: "ferrari", teamName: "Ferrari", teamId: "ferrari", delta: 8.3),
        ConstructorDelta(id: "mclaren", teamName: "McLaren", teamId: "mclaren", delta: -3.1),
        ConstructorDelta(id: "haas", teamName: "Haas", teamId: "haas", delta: 5.7),
        ConstructorDelta(id: "red_bull", teamName: "Red Bull", teamId: "red_bull", delta: -1.2),
        ConstructorDelta(id: "rb", teamName: "RB", teamId: "rb", delta: 2.4),
    ]

    // MARK: Pre-computed Sorted Arrays

    static let dnfSorted = Array(predictions.sorted { $0.simDnfPct > $1.simDnfPct }.prefix(8))
    static let topByWin = Array(predictions.sorted { $0.simWinPct > $1.simWinPct }.prefix(8))
    static let topByPodium = Array(predictions.sorted { $0.simPodiumPct > $1.simPodiumPct }.prefix(8))

    // MARK: Circuit Info (Japanese GP — Suzuka)

    static let circuitInfo = CircuitInfo(
        name: "Suzuka International Racing Course",
        country: "Japan",
        laps: 53,
        lengthKm: 5.807,
        raceDistanceKm: 307.471,
        lapRecord: "1:30.983",
        lapRecordHolder: "Lewis Hamilton (2019)",
        description: "Suzuka's legendary figure-eight layout is one of the most demanding in motorsport. The Esses and 130R test driver bravery and car balance at high speed, while the Degner curves and Spoon punish poor traction. A true drivers' circuit where car setup compromises are unavoidable.",
        recentWinners: [
            RecentWinner(season: 2025, driver: "Verstappen", teamId: "red_bull"),
            RecentWinner(season: 2024, driver: "Verstappen", teamId: "red_bull"),
            RecentWinner(season: 2023, driver: "Verstappen", teamId: "red_bull"),
        ]
    )

    // MARK: Session Schedule (Japanese GP — Suzuka, local time)

    static let sessionSchedule: [SessionScheduleEntry] = [
        SessionScheduleEntry(session: "FP1", day: "FRI", time: "03:30"),
        SessionScheduleEntry(session: "FP2", day: "FRI", time: "07:00"),
        SessionScheduleEntry(session: "FP3", day: "SAT", time: "03:30"),
        SessionScheduleEntry(session: "QUALIFYING", day: "SAT", time: "07:00"),
        SessionScheduleEntry(session: "RACE", day: "SUN", time: "07:00"),
    ]

    // MARK: Who to Watch (algorithm picks)

    static let whoToWatch: [WhoToWatch] = [
        WhoToWatch(name: "Leclerc", teamId: "ferrari", insight: "Highest ELO rating at technical circuits. Won 2 of last 3 at Suzuka-type tracks."),
        WhoToWatch(name: "Antonelli", teamId: "mercedes", insight: "Strongest wet weather performer on the grid. 15% rain chance could be his wildcard."),
        WhoToWatch(name: "Bearman", teamId: "haas", insight: "Biggest ELO riser this season. Outperforming his car consistently — dark horse for points."),
    ]

    // MARK: Model Movements (what changed)

    static let modelMovements: [ModelMovement] = [
        ModelMovement(driverId: "leclerc", driverName: "Leclerc", teamId: "ferrari", metric: .podium, delta: 7.2, reason: "Cooler temps favor Ferrari tire deg"),
        ModelMovement(driverId: "russell", driverName: "Russell", teamId: "mercedes", metric: .win, delta: 4.1, reason: "Mercedes upgrade package confirmed"),
        ModelMovement(driverId: "max_verstappen", driverName: "Verstappen", teamId: "red_bull", metric: .win, delta: -5.3, reason: "Car balance issues in practice sims"),
        ModelMovement(driverId: "bearman", driverName: "Bearman", teamId: "haas", metric: .points, delta: 8.4, reason: "Strong Suzuka-type circuit history"),
    ]

    static let lastModelUpdate = "12 min ago"

    // MARK: News Headlines (mock RSS)

    static let newsHeadlines: [NewsHeadline] = [
        NewsHeadline(source: "Formula 1", title: "Mercedes bringing significant upgrade package to Suzuka", timeAgo: "2h ago", impact: "Russell podium odds +4%"),
        NewsHeadline(source: "Autosport", title: "Leclerc confident of strong Ferrari pace at technical circuits", timeAgo: "4h ago"),
        NewsHeadline(source: "Motorsport.com", title: "Antonelli: 'I feel more comfortable with every race'", timeAgo: "6h ago"),
        NewsHeadline(source: "Formula 1", title: "Japanese GP weather forecast: dry conditions expected", timeAgo: "8h ago", impact: "Favors Leclerc, Verstappen"),
        NewsHeadline(source: "Autosport", title: "Red Bull struggling with car balance says Verstappen", timeAgo: "12h ago", impact: "Verstappen win odds -3%"),
    ]

    // MARK: Model Accuracy (post-race scorecard)

    static let raceAccuracy: [RaceAccuracy] = [
        RaceAccuracy(raceName: "Australian GP", round: 1, winnerPredicted: "Leclerc", winnerActual: "Russell", winnerCorrect: false, podiumAccuracy: 2, top10Accuracy: 8),
        RaceAccuracy(raceName: "Chinese GP", round: 2, winnerPredicted: "Verstappen", winnerActual: "Antonelli", winnerCorrect: false, podiumAccuracy: 1, top10Accuracy: 7),
    ]

    static let seasonAccuracy = SeasonAccuracy(
        winnerRate: 0.0,
        podiumRate: 50.0,
        top10Rate: 75.0,
        totalRaces: 2
    )
}
