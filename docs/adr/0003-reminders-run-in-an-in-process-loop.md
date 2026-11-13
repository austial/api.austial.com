# Reminders use our own asyncio loop, not the framework's @Cron

The framework's `@Cron` worker fires only once per run, so `ReminderService` runs its own 60-second loop from the application lifecycle hooks. Reminders are sent by the API container itself with no separate worker. This is only safe with a single container: a second one would send duplicate reminders, which is why scaling out needs a shared lock first.
