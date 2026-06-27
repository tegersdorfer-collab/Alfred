import SwiftUI
import UIKit

@MainActor
final class NutritionViewModel: ObservableObject {
    @Published var nutrition: TodayNutritionResponse?
    @Published var goals: NutritionGoals?
    @Published var isLoading = false
    @Published var error: String?
    @Published var showCamera = false
    @Published var showManual = false
    @Published var showDescription = false
    @Published var capturedImage: UIImage?
    @Published var pickerSource: UIImagePickerController.SourceType = .camera
    @Published var photoNote = ""
    @Published var editingMeal: MealItem?
    private var isPolling = false

    var totalCalories: Double { nutrition?.totals?.totalCalories ?? 0 }
    var totalProtein: Double { nutrition?.totals?.totalProtein ?? 0 }
    var totalCarbs: Double { nutrition?.totals?.totalCarbs ?? 0 }
    var totalFat: Double { nutrition?.totals?.totalFat ?? 0 }
    var calorieTarget: Double { goals?.targetCalories ?? 2800 }
    var proteinTarget: Double { goals?.proteinG ?? 180 }
    var carbsTarget: Double { goals?.carbsG ?? 350 }
    var fatTarget: Double { goals?.fatG ?? 80 }

    func load() async {
        isLoading = true; error = nil
        do {
            async let n = NutritionAPI.shared.todayNutrition()
            async let g = NutritionAPI.shared.nutritionGoals()
            nutrition = try await n
            goals = try? await g
            if let n = nutrition { OfflineCache.shared.save(n, key: "cache_nutrition") }
        } catch {
            self.error = error.localizedDescription
            nutrition = OfflineCache.shared.load(TodayNutritionResponse.self, key: "cache_nutrition")
        }
        isLoading = false
    }

    func deleteMeal(id: Int) async {
        try? await AlfredClient.shared.delete("/api/nutrition/\(id)")
        await load()
    }

    /// Lädt das aufgenommene Foto hoch (mit Notiz) — kehrt sofort zurück, Analyse läuft im Hintergrund.
    func analyzeCaptured() async {
        guard let img = capturedImage, let jpeg = img.jpegData(compressionQuality: 0.8) else { return }
        let note = photoNote
        capturedImage = nil; photoNote = ""
        try? await NutritionAPI.shared.analyzePhoto(imageData: jpeg, annotation: note.isEmpty ? nil : note)
        await load()
        startPolling()
    }

    /// Pollt, solange eine Mahlzeit analysiert wird, und füllt die Liste selbst.
    func startPolling() {
        guard !isPolling else { return }
        isPolling = true
        Task { @MainActor in
            while (nutrition?.meals?.contains { $0.status == "analyzing" }) == true {
                try? await Task.sleep(nanoseconds: 3_000_000_000)
                await load()
            }
            isPolling = false
        }
    }

    func saveEdit(_ meal: MealItem, name: String, kcal: Double?, p: Double?, c: Double?, f: Double?) async {
        try? await NutritionAPI.shared.updateMeal(meal.id,
            UpdateMealRequest(name: name, calories: kcal, protein: p, carbs: c, fat: f))
        editingMeal = nil
        await load()
    }
}

struct NutritionView: View {
    @StateObject private var vm = NutritionViewModel()
    @State private var showSourceDialog = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 16) {
                    macroSummaryCard
                    actionButtons
                    mealsList
                }
                .padding(.vertical)
            }
            .navigationTitle("Ernährung")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Button { Task { await vm.load() } } label: { Image(systemName: "arrow.clockwise") }
                }
            }
            .task { await vm.load(); vm.startPolling() }
            .refreshable { await vm.load() }
            .sheet(isPresented: $vm.showCamera, onDismiss: {
                if vm.capturedImage != nil { vm.showDescription = true }
            }) {
                ImagePicker(image: $vm.capturedImage, sourceType: vm.pickerSource).ignoresSafeArea()
            }
            .confirmationDialog("Foto wählen", isPresented: $showSourceDialog, titleVisibility: .visible) {
                if UIImagePickerController.isSourceTypeAvailable(.camera) {
                    Button("Kamera aufnehmen") { vm.pickerSource = .camera; vm.showCamera = true }
                }
                Button("Aus Galerie wählen") { vm.pickerSource = .photoLibrary; vm.showCamera = true }
                Button("Abbrechen", role: .cancel) {}
            }
            .sheet(isPresented: $vm.showDescription) {
                PhotoDescriptionSheet(image: vm.capturedImage, note: $vm.photoNote,
                    onAnalyze: { Task { await vm.analyzeCaptured() } },
                    onCancel: { vm.capturedImage = nil; vm.photoNote = "" })
            }
            .sheet(isPresented: $vm.showManual, onDismiss: { Task { await vm.load() } }) {
                ManualMealEntry()
            }
            .sheet(item: $vm.editingMeal) { meal in
                MealEditView(meal: meal) { name, kcal, p, c, f in
                    Task { await vm.saveEdit(meal, name: name, kcal: kcal, p: p, c: c, f: f) }
                }
            }
        }
    }

    private var macroSummaryCard: some View {
        VStack(spacing: 16) {
            HStack(spacing: 24) {
                calorieRing
                VStack(spacing: 10) {
                    macroBar(label: "Protein", value: vm.totalProtein, target: vm.proteinTarget, color: .blue)
                    macroBar(label: "Kohlenhydrate", value: vm.totalCarbs, target: vm.carbsTarget, color: .orange)
                    macroBar(label: "Fett", value: vm.totalFat, target: vm.fatTarget, color: .yellow)
                }
            }
            HStack {
                macroChip(String(format: "%.0fg P", vm.totalProtein), .blue)
                macroChip(String(format: "%.0fg C", vm.totalCarbs), .orange)
                macroChip(String(format: "%.0fg F", vm.totalFat), .yellow)
                Spacer()
            }
        }
        .padding()
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .padding(.horizontal)
    }

    private var calorieRing: some View {
        let progress = min(vm.totalCalories / vm.calorieTarget, 1.0)
        return ZStack {
            Circle().stroke(Color.green.opacity(0.15), lineWidth: 10)
            Circle().trim(from: 0, to: progress)
                .stroke(Color.green, style: StrokeStyle(lineWidth: 10, lineCap: .round))
                .rotationEffect(.degrees(-90))
                .animation(.easeOut, value: progress)
            VStack(spacing: 2) {
                Text(String(format: "%.0f", vm.totalCalories)).font(.title3.bold().monospacedDigit())
                Text("kcal").font(.caption2).foregroundStyle(.secondary)
                Text("/ \(Int(vm.calorieTarget))").font(.caption2).foregroundStyle(.secondary)
            }
        }
        .frame(width: 100, height: 100)
    }

    private func macroBar(label: String, value: Double, target: Double, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(label).font(.caption)
                Spacer()
                Text(String(format: "%.0f/%.0fg", value, target)).font(.caption2).foregroundStyle(.secondary)
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    RoundedRectangle(cornerRadius: 3).fill(color.opacity(0.15)).frame(height: 6)
                    RoundedRectangle(cornerRadius: 3).fill(color)
                        .frame(width: geo.size.width * min(value/target, 1.0), height: 6)
                        .animation(.easeOut, value: value)
                }
            }
            .frame(height: 6)
        }
        .frame(width: 160)
    }

    private func macroChip(_ text: String, _ color: Color) -> some View {
        Text(text).font(.caption.bold())
            .padding(.horizontal, 8).padding(.vertical, 4)
            .background(color.opacity(0.12))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    private var actionButtons: some View {
        HStack(spacing: 12) {
            Button { showSourceDialog = true } label: {
                HStack {
                    Image(systemName: "camera.fill")
                    Text("Foto")
                }
                .frame(maxWidth: .infinity).padding()
                .background(Color.green).foregroundStyle(.white)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            Button { vm.showManual = true } label: {
                HStack {
                    Image(systemName: "pencil")
                    Text("Manuell")
                }
                .frame(maxWidth: .infinity).padding()
                .background(Color(.secondarySystemBackground)).foregroundStyle(.primary)
                .clipShape(RoundedRectangle(cornerRadius: 14))
            }
        }
        .padding(.horizontal)
    }

    private var mealsList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Mahlzeiten heute")
                .font(.headline).padding(.horizontal)

            if vm.isLoading {
                ProgressView().frame(maxWidth: .infinity).padding()
            } else if let meals = vm.nutrition?.meals, !meals.isEmpty {
                ForEach(meals) { meal in
                    MealRowView(meal: meal) {
                        Task { await vm.deleteMeal(id: meal.id) }
                    }
                    .onTapGesture { if meal.status != "analyzing" { vm.editingMeal = meal } }
                }
            } else {
                ContentUnavailableView(
                    "Noch nichts geloggt",
                    systemImage: "fork.knife",
                    description: Text("Mach ein Foto oder trage manuell ein")
                )
                .padding(.top, 20)
            }
        }
    }
}

struct MealRowView: View {
    let meal: MealItem
    let onDelete: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 3).fill(Color.green).frame(width: 4)
            VStack(alignment: .leading, spacing: 4) {
                Text(meal.displayName).font(.subheadline.bold())
                if meal.status == "analyzing" {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.small)
                        Text("wird analysiert…").font(.caption).foregroundStyle(.secondary)
                    }
                } else if meal.status == "failed" {
                    Text("Analyse fehlgeschlagen — tippen zum Eintragen")
                        .font(.caption).foregroundStyle(.red)
                } else {
                    HStack(spacing: 12) {
                        if let kcal = meal.calories {
                            Text(String(format: "%.0f kcal", kcal)).font(.caption).foregroundStyle(.secondary)
                        }
                        if let p = meal.protein { macroTag(String(format: "%.0fg P", p), .blue) }
                        if let c = meal.carbs   { macroTag(String(format: "%.0fg C", c), .orange) }
                        if let f = meal.fat     { macroTag(String(format: "%.0fg F", f), .yellow) }
                    }
                }
            }
            Spacer()
        }
        .padding(12)
        .background(Color(.secondarySystemBackground))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .padding(.horizontal)
        .swipeActions(edge: .trailing) {
            Button(role: .destructive, action: onDelete) { Label("Löschen", systemImage: "trash") }
        }
    }

    private func macroTag(_ text: String, _ color: Color) -> some View {
        Text(text).font(.caption2.bold())
            .padding(.horizontal, 5).padding(.vertical, 2)
            .background(color.opacity(0.12)).foregroundStyle(color)
            .clipShape(Capsule())
    }
}

struct ManualMealEntry: View {
    @State private var name = ""
    @State private var calories = ""
    @State private var protein = ""
    @State private var carbs = ""
    @State private var fat = ""
    @State private var isSaving = false
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section("Mahlzeit") {
                    TextField("Name", text: $name)
                }
                Section("Makros") {
                    numericField("Kalorien (kcal)", binding: $calories)
                    numericField("Protein (g)", binding: $protein)
                    numericField("Kohlenhydrate (g)", binding: $carbs)
                    numericField("Fett (g)", binding: $fat)
                }
            }
            .navigationTitle("Manuell eintragen")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    if isSaving { ProgressView() }
                    else { Button("Sichern") { Task { await save() } }.fontWeight(.semibold) }
                }
            }
            .alert("Fehler", isPresented: .init(get: { error != nil }, set: { _ in error = nil })) {
                Button("OK", role: .cancel) {}
            } message: { Text(error ?? "") }
        }
    }

    private func numericField(_ label: String, binding: Binding<String>) -> some View {
        HStack {
            Text(label)
            Spacer()
            TextField("0", text: binding).keyboardType(.decimalPad).multilineTextAlignment(.trailing).frame(width: 80)
        }
    }

    private func save() async {
        guard !name.isEmpty else { error = "Name fehlt"; return }
        isSaving = true
        let req = LogMealRequest(name: name, calories: Double(calories), protein: Double(protein),
                                 carbs: Double(carbs), fat: Double(fat), notes: nil)
        do { try await NutritionAPI.shared.logMeal(req); dismiss() }
        catch { self.error = error.localizedDescription }
        isSaving = false
    }
}

struct ImagePicker: UIViewControllerRepresentable {
    @Binding var image: UIImage?
    let sourceType: UIImagePickerController.SourceType
    @Environment(\.dismiss) private var dismiss

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let p = UIImagePickerController()
        p.sourceType = sourceType
        p.delegate = context.coordinator
        return p
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}
    func makeCoordinator() -> Coordinator { Coordinator(self) }

    class Coordinator: NSObject, UIImagePickerControllerDelegate, UINavigationControllerDelegate {
        let parent: ImagePicker
        init(_ parent: ImagePicker) { self.parent = parent }
        func imagePickerController(_ picker: UIImagePickerController, didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]) {
            parent.image = info[.originalImage] as? UIImage
            parent.dismiss()
        }
        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) { parent.dismiss() }
    }
}

struct PhotoDescriptionSheet: View {
    let image: UIImage?
    @Binding var note: String
    let onAnalyze: () -> Void
    let onCancel: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                if let img = image {
                    Image(uiImage: img).resizable().scaledToFill()
                        .frame(height: 200).clipped()
                        .clipShape(RoundedRectangle(cornerRadius: 16))
                }
                TextField("Beschreibung (optional, z.B. 2 Portionen Nudeln)", text: $note, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                Button { onAnalyze(); dismiss() } label: {
                    Label("Analysieren", systemImage: "sparkles")
                        .frame(maxWidth: .infinity).padding()
                        .background(Color.green).foregroundStyle(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 14))
                }
                Text("Läuft im Hintergrund — du kannst sofort weitermachen.")
                    .font(.caption).foregroundStyle(.secondary)
                Spacer()
            }
            .padding()
            .navigationTitle("Foto")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { onCancel(); dismiss() } }
            }
        }
    }
}

struct MealEditView: View {
    let meal: MealItem
    let onSave: (String, Double?, Double?, Double?, Double?) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var kcal = ""
    @State private var protein = ""
    @State private var carbs = ""
    @State private var fat = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Mahlzeit") { TextField("Name", text: $name) }
                Section("Makros") {
                    field("Kalorien (kcal)", $kcal)
                    field("Protein (g)", $protein)
                    field("Kohlenhydrate (g)", $carbs)
                    field("Fett (g)", $fat)
                }
            }
            .navigationTitle("Bearbeiten")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Abbrechen") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Button("Sichern") {
                        onSave(name.isEmpty ? meal.displayName : name,
                               Double(kcal), Double(protein), Double(carbs), Double(fat))
                        dismiss()
                    }.fontWeight(.semibold)
                }
            }
            .onAppear {
                name = meal.displayName
                kcal = meal.calories.map { String(format: "%.0f", $0) } ?? ""
                protein = meal.protein.map { String(format: "%.0f", $0) } ?? ""
                carbs = meal.carbs.map { String(format: "%.0f", $0) } ?? ""
                fat = meal.fat.map { String(format: "%.0f", $0) } ?? ""
            }
        }
    }

    private func field(_ label: String, _ binding: Binding<String>) -> some View {
        HStack {
            Text(label); Spacer()
            TextField("0", text: binding).keyboardType(.decimalPad)
                .multilineTextAlignment(.trailing).frame(width: 80)
        }
    }
}
