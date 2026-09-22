import os
import time
import sqlite3
import secrets
import hashlib
import smtplib

from email.message import EmailMessage


# ============================================================
# DATABASE
# ============================================================

DB_NAME = "users.db"


def get_connection():
    return sqlite3.connect(DB_NAME)


def init_database():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            otp_hash TEXT,
            otp_expiry REAL,
            otp_attempts INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# Create database automatically
init_database()


# ============================================================
# PASSWORD HASHING
# ============================================================

def hash_password(password):

    return hashlib.sha256(
        password.encode()
    ).hexdigest()


# ============================================================
# REGISTER USER
# ============================================================

def register_user(email, password):

    email = email.strip().lower()

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO users
            (email, password_hash)
            VALUES (?, ?)
            """,
            (
                email,
                hash_password(password)
            )
        )

        conn.commit()

        return True, "Account created successfully."

    except sqlite3.IntegrityError:

        return False, "An account with this email already exists."

    finally:

        conn.close()


# ============================================================
# CHECK USER LOGIN
# ============================================================

def check_user(email, password):

    email = email.strip().lower()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT password_hash
        FROM users
        WHERE email = ?
        """,
        (email,)
    )

    result = cursor.fetchone()

    conn.close()

    if result is None:
        return False

    stored_hash = result[0]

    return stored_hash == hash_password(password)


# ============================================================
# GENERATE SECURE OTP
# ============================================================

def generate_otp():

    return str(
        secrets.randbelow(900000) + 100000
    )


# ============================================================
# STORE OTP
# ============================================================

def store_otp(email, otp):

    email = email.strip().lower()

    otp_hash = hashlib.sha256(
        otp.encode()
    ).hexdigest()

    # OTP valid for 60 seconds
    expiry = time.time() + 60

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE users
        SET
            otp_hash = ?,
            otp_expiry = ?,
            otp_attempts = 0
        WHERE email = ?
        """,
        (
            otp_hash,
            expiry,
            email
        )
    )

    conn.commit()
    conn.close()


# ============================================================
# VERIFY OTP
# ============================================================

def verify_otp(email, otp):

    email = email.strip().lower()

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT otp_hash, otp_expiry, otp_attempts
        FROM users
        WHERE email = ?
        """,
        (email,)
    )

    result = cursor.fetchone()

    if result is None:

        conn.close()
        return False, "Invalid OTP."

    stored_hash, expiry, attempts = result

    # Maximum 5 attempts
    if attempts >= 5:

        conn.close()

        return False, (
            "Too many incorrect attempts. "
            "Please request a new OTP."
        )

    # Check expiry
    if expiry is None or time.time() > expiry:

        conn.close()

        return False, "OTP expired. Please request a new OTP."

    entered_hash = hashlib.sha256(
        otp.encode()
    ).hexdigest()

    # Correct OTP
    if entered_hash == stored_hash:

        # Immediately invalidate OTP
        cursor.execute(
            """
            UPDATE users
            SET
                otp_hash = NULL,
                otp_expiry = NULL,
                otp_attempts = 0
            WHERE email = ?
            """,
            (email,)
        )

        conn.commit()
        conn.close()

        return True, "OTP verified successfully."

    # Wrong OTP
    attempts += 1

    cursor.execute(
        """
        UPDATE users
        SET otp_attempts = ?
        WHERE email = ?
        """,
        (
            attempts,
            email
        )
    )

    conn.commit()
    conn.close()

    remaining = 5 - attempts

    return False, (
        f"Incorrect OTP. "
        f"Attempts remaining: {remaining}"
    )


# ============================================================
# SEND OTP EMAIL
# ============================================================

def send_otp(email, otp):

    sender_email = os.getenv("OTP_EMAIL")
    sender_password = os.getenv("OTP_APP_PASSWORD")

    # --------------------------------------------------------
    # DEMO MODE
    # --------------------------------------------------------

    if not sender_email or not sender_password:

        print("\n===================================")
        print("DEMO OTP")
        print("Email:", email)
        print("OTP:", otp)
        print("===================================\n")

        return True

    try:

        message = EmailMessage()

        message["Subject"] = "HackDays Login OTP"
        message["From"] = sender_email
        message["To"] = email

        message.set_content(
            f"""
Hello,

Your OTP for HackDays login is:

{otp}

This OTP is valid for 60 seconds.

If you did not request this OTP,
please ignore this email.

Regards,
HackDays Authentication System
"""
        )

        with smtplib.SMTP(
            "smtp.gmail.com",
            587
        ) as server:

            server.starttls()

            server.login(
                sender_email,
                sender_password
            )

            server.send_message(message)

        return True

    except Exception as e:

        print("Email error:", e)

        return False