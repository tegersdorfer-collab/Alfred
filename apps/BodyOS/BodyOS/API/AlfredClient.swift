import Foundation

final class AlfredClient {
    static let shared = AlfredClient()

    var baseURL: String {
        UserDefaults.standard.string(forKey: "alfred_base_url") ?? "http://macbook-air-von-timo.tail7e29ff.ts.net:7779"
    }

    private let session: URLSession = {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 90
        config.waitsForConnectivity = true
        return URLSession(configuration: config)
    }()

    func get<T: Decodable>(_ path: String) async throws -> T {
        let data = try await withRetry { try await self.session.data(from: self.makeURL(path)) }
        return try decode(T.self, from: data)
    }

    func post<Body: Encodable, T: Decodable>(_ path: String, body: Body) async throws -> T {
        var req = URLRequest(url: try makeURL(path))
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let data = try await withRetry { try await self.session.data(for: req) }
        return try decode(T.self, from: data)
    }

    func postMultipart(_ path: String, imageData: Data, text: String?) async throws -> Data {
        var req = URLRequest(url: try makeURL(path))
        req.httpMethod = "POST"
        let boundary = UUID().uuidString
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        var body = Data()
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"image\"; filename=\"food.jpg\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: image/jpeg\r\n\r\n".data(using: .utf8)!)
        body.append(imageData)
        body.append("\r\n".data(using: .utf8)!)
        if let text, !text.isEmpty {
            body.append("--\(boundary)\r\n".data(using: .utf8)!)
            body.append("Content-Disposition: form-data; name=\"text\"\r\n\r\n".data(using: .utf8)!)
            body.append(text.data(using: .utf8)!)
            body.append("\r\n".data(using: .utf8)!)
        }
        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        req.httpBody = body
        return try await withRetry { try await self.session.data(for: req) }
    }

    func delete(_ path: String) async throws {
        var req = URLRequest(url: try makeURL(path))
        req.httpMethod = "DELETE"
        _ = try await withRetry { try await self.session.data(for: req) }
    }

    var isReachable: Bool {
        get async {
            guard let url = URL(string: baseURL + "/health") else { return false }
            do {
                let (_, r) = try await session.data(from: url)
                return (r as? HTTPURLResponse)?.statusCode == 200
            } catch { return false }
        }
    }

    // Retry once after 1.5s for transient Tailscale connectivity blips
    @discardableResult
    private func withRetry(_ attempt: () async throws -> (Data, URLResponse)) async throws -> Data {
        do {
            let (data, response) = try await attempt()
            try checkStatus(response, data: data)
            return data
        } catch let err as AlfredError {
            throw err
        } catch {
            try await Task.sleep(nanoseconds: 1_500_000_000)
            let (data, response) = try await attempt()
            try checkStatus(response, data: data)
            return data
        }
    }

    private func makeURL(_ path: String) throws -> URL {
        guard let url = URL(string: baseURL + path) else { throw AlfredError.invalidURL }
        return url
    }

    private func checkStatus(_ response: URLResponse, data: Data?) throws {
        guard let http = response as? HTTPURLResponse,
              !(200...299).contains(http.statusCode) else { return }
        let msg = data.flatMap { String(data: $0, encoding: .utf8) } ?? ""
        throw AlfredError.httpError(http.statusCode, msg)
    }

    private func decode<T: Decodable>(_ type: T.Type, from data: Data) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        do { return try dec.decode(T.self, from: data) }
        catch { throw AlfredError.decodingError(error.localizedDescription) }
    }
}

enum AlfredError: LocalizedError {
    case invalidURL, httpError(Int, String), decodingError(String), offline
    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Ungültige URL"
        case .httpError(let c, let m): return "HTTP \(c): \(m)"
        case .decodingError(let m): return "Parse: \(m)"
        case .offline: return "Alfred nicht erreichbar"
        }
    }
}
