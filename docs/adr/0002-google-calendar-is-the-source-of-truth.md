# Google Calendar decides availability

Slots are removed when Google Calendar's free/busy shows the owner busy, as well as for existing bookings and holds, and every booking becomes a Google event with a Meet link. We rejected keeping our own calendar because personal commitments would double-book. The API authenticates with one stored OAuth refresh token for the owner's account, so the Google consent screen must be published "In production" or the token expires after 7 days.
