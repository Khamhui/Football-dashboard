import Foundation

enum SupabaseClient {
    static let baseURL = "https://krfhvkbavtfbhsadzhee.supabase.co/rest/v1"
    static let anonKey = "sb_publishable_m-ousnBI0myKO13SGgN0QA_6OSIDP32"

    static func fetch<T: Decodable>(_ table: String, query: String = "", as type: T.Type) async throws -> T {
        let urlString = "\(baseURL)/\(table)?\(query)"
        guard let url = URL(string: urlString) else {
            throw URLError(.badURL)
        }

        var request = URLRequest(url: url)
        request.setValue(anonKey, forHTTPHeaderField: "apikey")
        request.setValue("Bearer \(anonKey)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }
}
