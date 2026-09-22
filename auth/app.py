import streamlit.components.v1 as components
import streamlit as st
import time


from auth_backend import (
    register_user,
    check_user,
    generate_otp,
    store_otp,
    verify_otp,
    send_otp
)


# ============================================================
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="HackDays Authentication",
    page_icon="🔐",
    layout="centered"
)


# ============================================================
# SESSION STATE
# ============================================================

defaults = {

    "page": "login",

    "email": "",

    "otp_sent": False,

    "logged_in": False,

    "last_otp_time": 0
}


for key, value in defaults.items():

    if key not in st.session_state:

        st.session_state[key] = value


# ============================================================
# CSS
# ============================================================

st.markdown(
    """
    <style>

    .title {
        text-align: center;
        font-size: 34px;
        font-weight: bold;
    }

    .subtitle {
        text-align: center;
        color: #999999;
        margin-bottom: 30px;
    }

    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# SUCCESSFUL LOGIN
# ============================================================

if st.session_state.logged_in:

    st.title("✅ Login Successful")

    st.success(
        f"Welcome, {st.session_state.email}!"
    )

    st.info(
        "Your email has been verified using OTP."
    )

    if st.button(
        "🚀 Open Dashboard",
        use_container_width=True
    ):

        components.html(
            """
            <script>
                window.parent.location.href = "http://localhost:8503";
            </script>
            """,
            height=0
        )

    if st.button(
        "🚪 Logout",
        use_container_width=True
    ):

        st.session_state.logged_in = False
        st.session_state.email = ""
        st.session_state.otp_sent = False
        st.session_state.page = "login"

        st.rerun()

    st.stop()


# ============================================================
# TITLE
# ============================================================

st.markdown(
    '<div class="title">🔐 HackDays Authentication</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="subtitle">Secure OTP-based Email Verification</div>',
    unsafe_allow_html=True
)


# ============================================================
# LOGIN PAGE
# ============================================================

if st.session_state.page == "login":

    st.subheader("Login")

    email = st.text_input(
        "📧 Email",
        placeholder="Enter your registered email"
    )

    password = st.text_input(
        "🔑 Password",
        type="password",
        placeholder="Enter your password"
    )

    if st.button(
        "📨 Login & Send OTP",
        use_container_width=True
    ):

        email = email.strip().lower()

        if not email or not password:

            st.error(
                "Please enter both email and password."
            )

        elif "@" not in email:

            st.error(
                "Please enter a valid email address."
            )

        elif not check_user(email, password):

            st.error(
                "Invalid email or password."
            )

        else:

            current_time = time.time()

            # 30-second resend protection
            if (
                current_time -
                st.session_state.last_otp_time
                < 30
            ):

                remaining = int(
                    30 -
                    (
                        current_time -
                        st.session_state.last_otp_time
                    )
                )

                st.warning(
                    f"Please wait {remaining} seconds."
                )

            else:

                otp = generate_otp()

                store_otp(
                    email,
                    otp
                )

                sent = send_otp(
                    email,
                    otp
                )

                if sent:

                    st.session_state.email = email

                    st.session_state.otp_sent = True

                    st.session_state.last_otp_time = time.time()

                    st.success(
                        "OTP sent successfully!"
                    )

                    st.rerun()

                else:

                    st.error(
                        "Unable to send OTP."
                    )


    st.divider()

    st.write(
        "Don't have an account?"
    )

    if st.button(
        "📝 Create New Account",
        use_container_width=True
    ):

        st.session_state.page = "register"

        st.rerun()


# ============================================================
# REGISTRATION PAGE
# ============================================================

elif st.session_state.page == "register":

    st.subheader("📝 Create Account")

    new_email = st.text_input(
        "📧 Email",
        placeholder="Enter your email"
    )

    new_password = st.text_input(
        "🔑 Password",
        type="password",
        placeholder="Create a password"
    )

    confirm_password = st.text_input(
        "🔑 Confirm Password",
        type="password",
        placeholder="Re-enter your password"
    )

    if st.button(
        "Create Account",
        use_container_width=True
    ):

        new_email = new_email.strip().lower()

        if not new_email or not new_password:

            st.error(
                "Please fill all fields."
            )

        elif "@" not in new_email:

            st.error(
                "Please enter a valid email."
            )

        elif len(new_password) < 6:

            st.error(
                "Password must contain at least 6 characters."
            )

        elif new_password != confirm_password:

            st.error(
                "Passwords do not match."
            )

        else:

            success, message = register_user(
                new_email,
                new_password
            )

            if success:

                st.success(
                    message
                )

                st.info(
                    "You can now login with your new account."
                )

                st.session_state.page = "login"

                st.rerun()

            else:

                st.error(
                    message
                )


    st.divider()

    if st.button(
        "← Back to Login",
        use_container_width=True
    ):

        st.session_state.page = "login"

        st.rerun()


# ============================================================
# OTP VERIFICATION
# ============================================================

if st.session_state.otp_sent:

    st.divider()

    st.subheader("🔢 Verify OTP")

    st.info(
        f"OTP sent to {st.session_state.email}\n\n"
        "OTP expires after 60 seconds."
    )

    otp = st.text_input(
        "Enter 6-digit OTP",
        max_chars=6,
        placeholder="123456"
    )

    if st.button(
        "✅ Verify OTP",
        use_container_width=True
    ):

        if not otp:

            st.error(
                "Please enter the OTP."
            )

        elif len(otp) != 6 or not otp.isdigit():

            st.error(
                "OTP must contain 6 digits."
            )

        else:

            success, message = verify_otp(
                st.session_state.email,
                otp
            )

            # if success:

            #     # ------------------------------------------
            #     # OTP VERIFIED
            #     # ------------------------------------------

            #     st.session_state.logged_in = True

            #     st.session_state.otp_sent = False

            #     st.success(
            #         "🎉 Authentication successful!"
            #     )

            #     # ------------------------------------------
            #     # OPEN DASHBOARD AUTOMATICALLY
            #     # ------------------------------------------

            #     components.html(
            #         """
            #         <script>
            #             window.parent.location.href = "http://localhost:8503";
            #         </script>
            #         """,
            #         height=1
            #     )
            if success:

                st.session_state.logged_in = True
                st.session_state.otp_sent = False

                st.success("🎉 Authentication successful!")

                st.markdown(
                    """
                    <meta http-equiv="refresh" content="1;url=http://localhost:8503">
                    """,
                    unsafe_allow_html=True
                 )

                st.markdown(
                    """
                     ### 🚀 Opening Dashboard...
        
                    If it doesn't open automatically, click below:
                    """
                )

                st.link_button(
                    "🚀 Open Dashboard",
                    "http://localhost:8503",
                    use_container_width=True
                )

            else:

                st.error(
                    message
                )


    # --------------------------------------------------------
    # RESEND OTP
    # --------------------------------------------------------

    if st.button(
        "🔄 Resend OTP",
        use_container_width=True
    ):

        elapsed = (
            time.time() -
            st.session_state.last_otp_time
        )

        if elapsed < 30:

            remaining = int(
                30 - elapsed
            )

            st.warning(
                f"Please wait {remaining} seconds."
            )

        else:

            new_otp = generate_otp()

            store_otp(
                st.session_state.email,
                new_otp
            )

            sent = send_otp(
                st.session_state.email,
                new_otp
            )

            if sent:

                st.session_state.last_otp_time = time.time()

                st.success(
                    "New OTP sent!"
                )

                st.rerun()

            else:

                st.error(
                    "Unable to send OTP."
                )


# ============================================================
# SECURITY INFORMATION
# ============================================================

st.divider()

st.caption(
    "🔒 OTP expires after 60 seconds • "
    "Maximum 5 attempts • "
    "OTP invalidated after verification"
)