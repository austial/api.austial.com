# Reminders use our own asyncio loop, not the framework's @Cron

The framework's `@Cron` worker fires only once per run, so `ReminderService` runs its own 60-second loop from the application lifecycle hooks. Reminders are sent by the API container itself with no separate worker. Each reminder is claimed with a conditional update on `reminder_sent_at` before sending, so a second container does not send duplicates. Rate limits and the booking lock are still in memory, so scaling out needs a shared store for those.
