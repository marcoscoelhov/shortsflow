# Operational settings live in the hub

Operational settings are stored as allowlisted database overrides and edited in the Hub de Revisao. The environment remains the source for boot-time infrastructure and secrets: app URL, data location, database URL, provider credentials and OAuth client secrets.

This avoids treating `.env` as the daily control panel. Changing LLM routing, background music source, automation timing, score threshold or YouTube publish mode no longer requires editing files or restarting the hub. The trade-off is that the effective runtime configuration becomes `environment defaults + hub overrides`, so the hub includes a reset action that clears overrides and returns to `.env` defaults.

The override table must never accept secrets or arbitrary `Settings` fields. New hub-editable settings must be added through the explicit allowlist.
