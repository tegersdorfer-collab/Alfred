import SwiftUI

@MainActor
final class GraphViewModel: ObservableObject {
    @Published var sim = ForceSimulation()
    @Published var graphData: GraphData?
    @Published var isLoading = false
    @Published var error: String?
    @Published var selectedNodeId: Int?
    @Published var selectedNote: BrainNote?
    @Published var isRunning = true

    private var timer: Timer?

    func load(in size: CGSize) async {
        isLoading = true; error = nil
        do {
            let data = try await BrainAPI.shared.fetchGraph()
            graphData = data
            sim.reset(graphNodes: data.nodes, graphEdges: data.edges, in: size)
            startSimulation()
        } catch { self.error = error.localizedDescription }
        isLoading = false
    }

    func startSimulation() {
        timer?.invalidate()
        timer = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] _ in
            guard let self, isRunning else { return }
            Task { @MainActor in self.sim.tick() }
        }
    }

    func stopSimulation() {
        timer?.invalidate()
        timer = nil
    }

    func tapNode(_ nodeId: Int) async {
        if selectedNodeId == nodeId {
            selectedNodeId = nil
            selectedNote = nil
            return
        }
        selectedNodeId = nodeId
        selectedNote = try? await BrainAPI.shared.fetchNote(nodeId)
    }

    func dragNode(_ nodeId: Int, to point: CGPoint) {
        sim.pin(nodeId: nodeId, at: point)
    }

    func releaseNode(_ nodeId: Int) {
        sim.unpin(nodeId: nodeId)
    }

    deinit { timer?.invalidate() }
}

struct GraphView: View {
    @StateObject private var vm = GraphViewModel()
    @State private var size: CGSize = .zero
    @State private var showNoteSheet = false

    var body: some View {
        ZStack {
            Color(.systemBackground).ignoresSafeArea()

            if vm.isLoading {
                ProgressView("Lade Graph…")
            } else if let err = vm.error {
                VStack(spacing: 12) {
                    Image(systemName: "network.slash").font(.largeTitle).foregroundColor(.secondary)
                    Text(err).font(.subheadline).foregroundColor(.secondary).multilineTextAlignment(.center)
                    Button("Nochmal") { Task { await vm.load(in: size) } }
                }
                .padding()
            } else {
                GeometryReader { geo in
                    graphCanvas(size: geo.size)
                        .onAppear {
                            size = geo.size
                            vm.sim.center = CGPoint(x: geo.size.width / 2, y: geo.size.height / 2)
                        }
                }
                .ignoresSafeArea(edges: .bottom)

                // Info card for selected node
                if let note = vm.selectedNote {
                    VStack {
                        Spacer()
                        selectedNoteCard(note)
                            .padding(.horizontal, 20)
                            .padding(.bottom, 100)
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                }
            }
        }
        .navigationTitle("Graph")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    vm.isRunning.toggle()
                    if vm.isRunning { vm.startSimulation() }
                } label: {
                    Image(systemName: vm.isRunning ? "pause.circle" : "play.circle")
                }
            }
            ToolbarItem(placement: .secondaryAction) {
                Button("Reload") { Task { await vm.load(in: size) } }
            }
        }
        .task { await vm.load(in: size) }
        .sheet(isPresented: $showNoteSheet, onDismiss: { vm.selectedNote = nil; vm.selectedNodeId = nil }) {
            if let note = vm.selectedNote {
                NoteEditorView(note: note)
            }
        }
        .animation(.easeInOut(duration: 0.3), value: vm.selectedNodeId)
    }

    private func graphCanvas(size: CGSize) -> some View {
        Canvas { ctx, _ in
            guard let data = vm.graphData else { return }

            // Draw edges
            for edge in data.edges {
                guard let src = vm.sim.nodes.first(where: { $0.id == edge.from }),
                      let tgt = vm.sim.nodes.first(where: { $0.id == edge.to }) else { continue }
                var path = Path()
                path.move(to: src.position)
                path.addLine(to: tgt.position)
                ctx.stroke(path, with: .color(.gray.opacity(0.3)), lineWidth: 1)
            }

            // Draw nodes
            for node in vm.sim.nodes {
                guard let gn = data.nodes.first(where: { $0.id == node.id }) else { continue }
                let r: CGFloat = CGFloat(gn.size ?? 10) * 0.6 + 6
                let isSelected = vm.selectedNodeId == node.id
                let cat = gn.group ?? "inbox"
                let color = categoryColors[cat] ?? .gray

                let rect = CGRect(x: node.position.x - r, y: node.position.y - r, width: r * 2, height: r * 2)
                ctx.fill(Path(ellipseIn: rect), with: .color(color.opacity(isSelected ? 1 : 0.7)))
                if isSelected {
                    ctx.stroke(Path(ellipseIn: rect.insetBy(dx: -2, dy: -2)), with: .color(color), lineWidth: 2)
                }

                // Label
                let label = gn.label ?? gn.title ?? ""
                if !label.isEmpty {
                    ctx.draw(
                        Text(label).font(.system(size: 9)).foregroundColor(.primary),
                        at: CGPoint(x: node.position.x, y: node.position.y + r + 8)
                    )
                }
            }
        }
        .gesture(
            DragGesture(minimumDistance: 0)
                .onChanged { val in
                    guard let data = vm.graphData else { return }
                    let hit = vm.sim.nodes.first { node in
                        let gn = data.nodes.first { $0.id == node.id }
                        let r: CGFloat = CGFloat(gn?.size ?? 10) * 0.6 + 8
                        let dx = node.position.x - val.location.x
                        let dy = node.position.y - val.location.y
                        return sqrt(dx*dx + dy*dy) < r
                    }
                    if let n = hit { vm.dragNode(n.id, to: val.location) }
                }
                .onEnded { val in
                    guard let data = vm.graphData else { return }
                    // If tap (small movement), select node
                    let dist = sqrt(pow(val.translation.width, 2) + pow(val.translation.height, 2))
                    if dist < 5 {
                        let hit = vm.sim.nodes.first { node in
                            let gn = data.nodes.first { $0.id == node.id }
                            let r: CGFloat = CGFloat(gn?.size ?? 10) * 0.6 + 8
                            let dx = node.position.x - val.location.x
                            let dy = node.position.y - val.location.y
                            return sqrt(dx*dx + dy*dy) < r
                        }
                        if let n = hit {
                            Task { await vm.tapNode(n.id) }
                        } else {
                            vm.selectedNodeId = nil
                            vm.selectedNote = nil
                        }
                    } else {
                        // Release dragged node
                        let hit = vm.sim.nodes.first { node in
                            let gn = data.nodes.first { $0.id == node.id }
                            let r: CGFloat = CGFloat(gn?.size ?? 10) * 0.6 + 8
                            let dx = node.position.x - val.location.x
                            let dy = node.position.y - val.location.y
                            return sqrt(dx*dx + dy*dy) < r
                        }
                        if let n = hit { vm.releaseNode(n.id) }
                    }
                }
        )
    }

    private func selectedNoteCard(_ note: BrainNote) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Circle()
                    .fill(Color.forCategory(note.category))
                    .frame(width: 10, height: 10)
                Text(note.title).font(.headline)
                Spacer()
                Button { showNoteSheet = true } label: {
                    Image(systemName: "arrow.up.right.square")
                }
                Button { vm.selectedNodeId = nil; vm.selectedNote = nil } label: {
                    Image(systemName: "xmark.circle.fill").foregroundColor(.secondary)
                }
            }
            if !note.content.isEmpty {
                Text(note.content.prefix(120))
                    .font(.subheadline)
                    .foregroundColor(.secondary)
                    .lineLimit(3)
            }
        }
        .padding(14)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .shadow(radius: 8)
    }
}
