import hashlib
import html as _html
import hmac
import secrets
import string
from datetime import datetime, timezone, timedelta
import streamlit as st
from src.database.config import supabase
from src.services.email_service import _send

OTP_TTL         = timedelta(minutes=10)
MAX_ATTEMPTS    = 5
RESEND_COOLDOWN = timedelta(seconds=30)


def generate_otp(length=6):
    """Cryptographically secure numeric OTP"""
    return ''.join(secrets.choice(string.digits) for _ in range(length))


def _hash_otp(email, otp, purpose):
    return hashlib.sha256(f"{email.lower()}:{purpose}:{otp}".encode()).hexdigest()


def _parse_ts(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def send_otp_email(email: str, otp: str, purpose: str, name: str = "User"):
    """Send OTP verification email"""
    purpose_map = {
        "student_email":  "Student Email Verification",
        "parent_email":   "Parent Email Verification",
        "teacher_email":  "Teacher Email Verification",
    }
    purpose_label = purpose_map.get(purpose, "Email Verification")

    plain = f"""Dear {name},

Your OTP for {purpose_label} is: {otp}

This OTP is valid for 10 minutes only.
Do not share this OTP with anyone.

SnapClass Team
"""
    name = _html.escape(str(name))
    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"/></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:30px 0;">
 <tr><td align="center">
  <table width="500" cellpadding="0" cellspacing="0"
   style="background:#fff;border-radius:12px;overflow:hidden;
          box-shadow:0 4px 14px rgba(0,0,0,.1);">

   <tr><td style="background:linear-gradient(135deg,#6C3FC5,#E8386D);
                  padding:24px;text-align:center;">
     <h1 style="color:#fff;margin:0;font-size:24px;">📷 SnapClass</h1>
     <p style="color:#e0d7ff;margin:5px 0 0;font-size:13px;">
       Email Verification</p>
   </td></tr>

   <tr><td style="padding:30px 36px 10px;">
     <p style="color:#333;font-size:15px;margin:0;">
       Dear <strong>{name}</strong>,</p>
     <p style="color:#555;font-size:14px;margin:10px 0;">
       Your OTP for <strong>{purpose_label}</strong> is:</p>
   </td></tr>

   <tr><td style="padding:10px 36px;">
     <div style="background:#f0eeff;border-radius:12px;padding:20px;
                 text-align:center;border:2px dashed #6C3FC5;">
       <span style="font-size:42px;font-weight:bold;
                    color:#6C3FC5;letter-spacing:12px;">{otp}</span>
     </div>
   </td></tr>

   <tr><td style="padding:16px 36px 10px;">
     <p style="color:#e74c3c;font-size:13px;margin:0;">
       ⏰ This OTP expires in <strong>10 minutes</strong>.</p>
     <p style="color:#999;font-size:12px;margin:8px 0 0;">
       Do not share this OTP with anyone. SnapClass will never ask for your OTP.</p>
   </td></tr>

   <tr><td style="background:#f0eeff;padding:14px 36px;text-align:center;
                  border-top:1px solid #e0d7ff;">
     <p style="color:#9370DB;font-size:12px;margin:0;font-weight:bold;">
       SnapClass — Making Attendance Smarter with AI</p>
   </td></tr>

  </table>
 </td></tr>
</table>
</body></html>"""

    _send(email, f"🔐 Your SnapClass OTP: {otp}", html, plain)


def save_otp(email: str, otp: str, purpose: str):
    """Save hashed OTP (replaces any earlier OTP for this email+purpose)"""
    supabase.table('otp_verifications')\
        .delete()\
        .eq('email', email)\
        .eq('purpose', purpose)\
        .execute()

    supabase.table('otp_verifications').insert({
        'email':       email,
        'otp':         _hash_otp(email, otp, purpose),
        'purpose':     purpose,
        'is_verified': False,
        'attempts':    0
    }).execute()


def verify_otp(email: str, otp_input: str, purpose: str):
    """Returns (is_valid: bool, message: str). Enforces expiry + attempt limit."""
    try:
        res = supabase.table('otp_verifications')\
            .select('*')\
            .eq('email', email)\
            .eq('purpose', purpose)\
            .eq('is_verified', False)\
            .execute()

        if not res.data:
            return False, "OTP not found. Please click Send OTP first."

        record = res.data[0]

        created = _parse_ts(record.get('created_at'))
        if created and datetime.now(timezone.utc) - created > OTP_TTL:
            supabase.table('otp_verifications').delete().eq('id', record['id']).execute()
            return False, "OTP expired. Please request a new one."

        attempts = record.get('attempts') or 0
        if attempts >= MAX_ATTEMPTS:
            supabase.table('otp_verifications').delete().eq('id', record['id']).execute()
            return False, "Too many wrong attempts. Please request a new OTP."

        expected = record['otp']
        given    = _hash_otp(email, otp_input.strip(), purpose)
        if not hmac.compare_digest(expected, given):
            supabase.table('otp_verifications')\
                .update({'attempts': attempts + 1})\
                .eq('id', record['id']).execute()
            left = MAX_ATTEMPTS - attempts - 1
            return False, f"Invalid OTP. {left} attempt(s) left."

        supabase.table('otp_verifications')\
            .update({'is_verified': True})\
            .eq('id', record['id'])\
            .execute()

        return True, "Email verified successfully!"

    except Exception as e:
        return False, f"Verification failed: {str(e)}"


def is_email_verified(email: str, purpose: str):
    """Check if email is already verified in this session"""
    verified_emails = st.session_state.get('verified_emails', {})
    return verified_emails.get(f"{email}_{purpose}", False)


def mark_email_verified(email: str, purpose: str):
    """Mark email as verified in session"""
    if 'verified_emails' not in st.session_state:
        st.session_state.verified_emails = {}
    st.session_state.verified_emails[f"{email}_{purpose}"] = True


def send_and_save_otp(email: str, purpose: str, name: str = "User"):
    """Generate, save and send OTP (with resend cooldown)"""
    existing = supabase.table('otp_verifications')\
        .select('created_at')\
        .eq('email', email).eq('purpose', purpose).execute()
    if existing.data:
        created = _parse_ts(existing.data[0].get('created_at'))
        if created and datetime.now(timezone.utc) - created < RESEND_COOLDOWN:
            raise ValueError("Please wait 30 seconds before requesting another OTP.")

    otp = generate_otp()
    save_otp(email, otp, purpose)
    send_otp_email(email, otp, purpose, name)
    return True
