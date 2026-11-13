# Bookers prove their email with a 6-digit code

A visitor's slot is held for 15 minutes and becomes a booking only when they enter the code we emailed. There are no accounts. We chose this over unverified bookings, which would fill the calendar with fake or mistyped addresses, and over passwords or social login, which add friction for a one-off call. Codes are stored only as an HMAC with `CODE_PEPPER`, so changing the pepper invalidates open codes and every manage link.
