import Foundation

// MARK: - API Models

struct BrainNote: Decodable, Identifiable {
    let id: Int
    let title: String
    let content: String
    let category: String
    let tags: [String]?
    let pinned: Bool?
    let createdAt: String?
    let updatedAt: String?
    let links: [Int]?
}

struct GraphData: Decodable {
    let nodes: [GraphNode]
    let edges: [GraphEdge]
}

struct GraphNode: Decodable, Identifiable {
    let id: Int
    let label: String?
    let title: String?
    let group: String?
    let color: String?
    let size: Double?
}

struct GraphEdge: Decodable, Identifiable {
    var id: String { "\(from)-\(to)" }
    let from: Int
    let to: Int
}

struct BacklinkItem: Decodable, Identifiable {
    let id: Int
    let title: String
    let category: String
}

struct SearchResult: Decodable, Identifiable {
    let id: Int
    let title: String
    let content: String
    let category: String
}

// MARK: - Request models

struct CreateNoteRequest: Encodable {
    let title: String
    let content: String
    let category: String
    let tags: [String]
    let pinned: Bool
}

struct UpdateNoteRequest: Encodable {
    let title: String
    let content: String
    let category: String
    let tags: [String]
    let pinned: Bool
}

struct OkResponse: Decodable {
    let ok: Bool?
    let id: Int?
}

// MARK: - Category constants

let brainCategories = ["inbox", "project", "area", "resource", "daily", "quote"]

let categoryColors: [String: Color] = [
    "inbox":    .gray,
    "project":  .blue,
    "area":     .green,
    "resource": .orange,
    "daily":    .purple,
    "quote":    .pink,
]

import SwiftUI
extension Color {
    static func forCategory(_ cat: String) -> Color {
        categoryColors[cat] ?? .gray
    }
}
