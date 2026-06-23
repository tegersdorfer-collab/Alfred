---
name: workout_empfehlung_bei_hrv
description: HRV und Schlaf prüfen bevor Workout empfohlen wird
triggers: [training, workout, hrv, sport, gym]
---
1. Rufe get_recent_health(days=1) auf um HRV und Schlaf zu lesen
2. Falls HRV < 40 oder Schlaf < 6h → leichtes Training oder Ruhe empfehlen
3. Falls HRV > 60 und Schlaf > 7h → intensives Training empfehlen
4. Erkläre kurz die Begründung (HRV Wert + Schlaf Stunden)
