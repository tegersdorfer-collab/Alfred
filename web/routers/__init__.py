"""API-Router-Module. Eingebunden in web/api.create_app()."""
from . import brain, calendar, chat, fitness, goals, habits, health, insights, journal, knowledge, meta, nutrition, spicetify, system, tasks, trigger, ui_state, voice

ROUTER_MODULES = [
    brain,
    calendar,
    chat,
    fitness,
    goals,
    habits,
    health,
    insights,
    journal,
    knowledge,
    meta,
    nutrition,
    spicetify,
    system,
    tasks,
    trigger,
    ui_state,
    voice,
]
