# Booking API

The backend behind services.austial.com: it offers call times, confirms bookings and records leads.

## Booking

**Slot**:
A start time a visitor can pick for a discovery call, derived from the weekly hours, the buffer, the notice rule and the calendar.
_Avoid_: Time, appointment slot

**Hold**:
A slot reserved for one visitor for a short time while they verify their email. It expires if the code is not entered.
_Avoid_: Reservation, lock, pending booking

**Verification code**:
The 6-digit number emailed to the visitor that turns a Hold into a Booking.
_Avoid_: OTP, PIN, token

**Booking**:
A confirmed discovery call at a Slot, with a calendar event and a Meet link.
_Avoid_: Appointment, reservation

**Manage link**:
The emailed link a visitor uses to view, reschedule or cancel their Booking, with no account.
_Avoid_: Magic link, portal

## Leads

**Lead**:
A Brief received from the form, kept with the visitor's contact details and chosen services.
_Avoid_: Submission, inquiry

**Honeypot**:
A hidden form field that real visitors leave empty; a filled one marks the submission as automated and it is dropped silently.
_Avoid_: Trap field
