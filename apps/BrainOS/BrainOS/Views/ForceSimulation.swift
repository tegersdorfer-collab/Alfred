import Foundation
import CoreGraphics

struct SimNode {
    let id: Int
    var position: CGPoint
    var velocity: CGPoint = .zero
    var pinned: Bool = false
}

struct SimEdge {
    let source: Int
    let target: Int
}

final class ForceSimulation: ObservableObject {
    @Published var nodes: [SimNode] = []
    var edges: [SimEdge] = []

    private let repulsion: CGFloat = 3000
    private let springLength: CGFloat = 120
    private let springStrength: CGFloat = 0.03
    private let damping: CGFloat = 0.85
    private let centerPull: CGFloat = 0.008

    var center: CGPoint = .zero

    func reset(graphNodes: [GraphNode], graphEdges: [GraphEdge], in size: CGSize) {
        center = CGPoint(x: size.width / 2, y: size.height / 2)
        let angle = 2 * CGFloat.pi / CGFloat(max(graphNodes.count, 1))
        nodes = graphNodes.enumerated().map { i, n in
            let r = min(size.width, size.height) * 0.3
            let pos = CGPoint(
                x: center.x + r * cos(angle * CGFloat(i)),
                y: center.y + r * sin(angle * CGFloat(i))
            )
            return SimNode(id: n.id, position: pos)
        }
        edges = graphEdges.map { SimEdge(source: $0.from, target: $0.to) }
    }

    func tick() {
        guard !nodes.isEmpty else { return }

        var forces = [Int: CGPoint]()
        for node in nodes { forces[node.id] = .zero }

        // Repulsion between all pairs
        for i in nodes.indices {
            for j in nodes.indices where j != i {
                let dx = nodes[i].position.x - nodes[j].position.x
                let dy = nodes[i].position.y - nodes[j].position.y
                let dist = max(sqrt(dx*dx + dy*dy), 1)
                let f = repulsion / (dist * dist)
                forces[nodes[i].id]!.x += (dx / dist) * f
                forces[nodes[i].id]!.y += (dy / dist) * f
            }
        }

        // Spring attraction along edges
        for edge in edges {
            guard let si = nodes.firstIndex(where: { $0.id == edge.source }),
                  let ti = nodes.firstIndex(where: { $0.id == edge.target }) else { continue }
            let dx = nodes[ti].position.x - nodes[si].position.x
            let dy = nodes[ti].position.y - nodes[si].position.y
            let dist = max(sqrt(dx*dx + dy*dy), 1)
            let stretch = dist - springLength
            let f = stretch * springStrength
            let fx = (dx / dist) * f
            let fy = (dy / dist) * f
            forces[nodes[si].id]!.x += fx
            forces[nodes[si].id]!.y += fy
            forces[nodes[ti].id]!.x -= fx
            forces[nodes[ti].id]!.y -= fy
        }

        // Weak pull toward center
        for node in nodes {
            forces[node.id]!.x += (center.x - node.position.x) * centerPull
            forces[node.id]!.y += (center.y - node.position.y) * centerPull
        }

        // Integrate
        for i in nodes.indices {
            guard !nodes[i].pinned else { continue }
            nodes[i].velocity.x = (nodes[i].velocity.x + forces[nodes[i].id]!.x) * damping
            nodes[i].velocity.y = (nodes[i].velocity.y + forces[nodes[i].id]!.y) * damping
            nodes[i].position.x += nodes[i].velocity.x
            nodes[i].position.y += nodes[i].velocity.y
        }
    }

    func pin(nodeId: Int, at position: CGPoint) {
        guard let i = nodes.firstIndex(where: { $0.id == nodeId }) else { return }
        nodes[i].position = position
        nodes[i].pinned = true
    }

    func unpin(nodeId: Int) {
        guard let i = nodes.firstIndex(where: { $0.id == nodeId }) else { return }
        nodes[i].pinned = false
        nodes[i].velocity = .zero
    }
}
