import Foundation
import Combine
import UserNotifications

@MainActor
final class RestTimer: ObservableObject {
    @Published var secondsRemaining: Int = 0
    @Published var isRunning: Bool = false

    private var cancellable: AnyCancellable?
    private var totalSeconds: Int = 90

    func start(seconds: Int = 90) {
        totalSeconds = seconds
        secondsRemaining = seconds
        isRunning = true
        scheduleNotification(after: seconds)
        cancellable = Timer.publish(every: 1, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                guard let self else { return }
                if self.secondsRemaining > 0 {
                    self.secondsRemaining -= 1
                } else {
                    self.stop()
                }
            }
    }

    func stop() {
        isRunning = false
        cancellable = nil
        UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: ["rest-timer"])
    }

    var progress: Double {
        guard totalSeconds > 0 else { return 0 }
        return 1.0 - Double(secondsRemaining) / Double(totalSeconds)
    }

    private func scheduleNotification(after seconds: Int) {
        UNUserNotificationCenter.current().requestAuthorization(options: [.sound, .alert]) { _, _ in }
        let content = UNMutableNotificationContent()
        content.title = "Pause beendet"
        content.body = "Nächster Satz!"
        content.sound = .default
        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: TimeInterval(seconds), repeats: false)
        let req = UNNotificationRequest(identifier: "rest-timer", content: content, trigger: trigger)
        UNUserNotificationCenter.current().add(req)
    }
}
