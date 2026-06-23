---
name: rezept_analyse
description: Nährwerte aus Rezept schätzen und mit Tagesziel vergleichen
triggers: [rezept, kochen, essen, mahlzeit, kalorien]
created_by: background_review
---

1. Lies das genannte Rezept/Gericht
2. Schätze Kalorien und Makronährstoffe
3. Hole aktuelle Tagesziel via get_nutrition_goal()
4. Vergleiche und empfehle ob es ins Ziel passt
