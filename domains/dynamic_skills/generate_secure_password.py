"""Automatisch von Alfred erstelltes Skill: Generiert ein zufälliges, sicheres Passwort mit konfigurierbarer Länge und Zeichentypen (Buchstaben, Zahlen, Sonderzeichen).
Erstellt: 2026-06-16T19:59:14
"""
from core import tools as T


import random
import string

@T.register(
    "generate_secure_password",
    "Generiert ein zufälliges, sicheres Passwort mit konfigurierbarer Länge und Zeichentypen",
    {
        "type": "object",
        "properties": {
            "length": {"type": "integer", "description": "Passwortlänge (default: 16)"},
            "use_uppercase": {"type": "boolean", "description": "Großbuchstaben einbeziehen (default: true)"},
            "use_lowercase": {"type": "boolean", "description": "Kleinbuchstaben einbeziehen (default: true)"},
            "use_digits": {"type": "boolean", "description": "Zahlen einbeziehen (default: true)"},
            "use_special": {"type": "boolean", "description": "Sonderzeichen einbeziehen (default: true)"}
        }
    },
    [],
    "utility"
)
async def generate_secure_password(length=16, use_uppercase=True, use_lowercase=True, use_digits=True, use_special=True):
    chars = ""
    if use_uppercase:
        chars += string.ascii_uppercase
    if use_lowercase:
        chars += string.ascii_lowercase
    if use_digits:
        chars += string.digits
    if use_special:
        chars += "!@#$%^&*()_+-=[]{}|;:,.<>?"
    
    if not chars:
        return "Fehler: Mindestens ein Zeichentyp muss ausgewählt sein."
    
    password = ''.join(random.choice(chars) for _ in range(length))
    return password
