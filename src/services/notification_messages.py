"""Message text and idempotency keys for substitution notices. Pure: no database or email."""
import hashlib


def key_for(event, substitution_id, recipient):
    raw = f"{event}|{substitution_id}|{recipient}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def assigned_to_substitute(sub):
    subject = f"Substitution assigned: {sub['subject_code']}, P{sub['period_no']}, {sub['substitution_date']}"
    body = (f"You have been assigned to cover {sub['subject_code']} for section {sub['section_code']} "
            f"on {sub['substitution_date']}, period {sub['period_no']}. "
            f"Room: {sub.get('room') or 'to be confirmed'}. "
            "Open 'Leave & absences' in your portal to accept or decline.")
    return subject, body


def absence_for_original(sub, substitute_name):
    subject = f"Your class is covered: {sub['subject_code']}, P{sub['period_no']}"
    body = (f"{substitute_name} will cover your {sub['subject_code']} class for section "
            f"{sub['section_code']} on {sub['substitution_date']}, period {sub['period_no']}.")
    return subject, body


def unassigned_for_admin(sub):
    subject = f"Unassigned class: {sub['subject_code']}, P{sub['period_no']}, {sub['substitution_date']}"
    body = (f"No eligible replacement for section {sub['section_code']}, {sub['subject_code']}, "
            f"{sub['substitution_date']}, period {sub['period_no']}. Reason: {sub.get('reasons') or 'not recorded'}.")
    return subject, body
