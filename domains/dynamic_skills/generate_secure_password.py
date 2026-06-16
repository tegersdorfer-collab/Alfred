"""Automatisch von Alfred erstelltes Skill: Generiert ein zufälliges, sicheres Passwort mit konfigurierbarer Länge und Zeichentypen.
Erstellt: 2026-06-16T19:59:21
"""
from core import tools as T


import random
import string

@T.register(
    "generate_secure_password",
    "Generiert ein zufälliges, sicheres Passwort",
    {
        "type": "object",
        "properties": {
            "length": {"type": "integer", "description": "Passwortlänge"}
        },
        "required": ["length"]
    },
    ["length"],
    "utility"
)
async def generate_secure_password(length):
    chars = string.ascii_uppercase + string.ascii_lowercase + string.digits + "!@#$%^&*()_+-=[]{}|;:,.<>?"
    password = ''.join(random.choice(chars) for _ in range(int(length)))
    return password
