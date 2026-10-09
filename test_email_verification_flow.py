# test_email_verification_flow.py
import requests
import getpass


BASE_URL = "http://localhost:8000/api/v1"

LOGIN_URL = f"{BASE_URL}/auth/login/"
REQUEST_URL = f"{BASE_URL}/auth/email-verification/request/"
CONFIRM_URL = f"{BASE_URL}/auth/email-verification/confirm/"

TIMEOUT = 30


def print_response(title, response):
    print(f"\n--- {title} ---")
    print(f"HTTP Status: {response.status_code}")

    try:
        print(response.json())
    except ValueError:
        print(response.text)


def main():
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ")

    if not email or not password:
        print("Email and password are required.")
        return

    session = requests.Session()

    try:
        # Step 1: Login
        print("\n[1/3] Logging in...")

        login_response = session.post(
            LOGIN_URL,
            json={
                "credential": email,
                "password": password,
            },
            timeout=TIMEOUT,
        )

        print_response("Login", login_response)

        if not login_response.ok:
            print("Login failed. Stopping.")
            return

        access_token = login_response.json().get("access")

        if not access_token:
            print("Login response does not contain an access token.")
            return

        headers = {
            "Authorization": f"Bearer {access_token}",
        }

        # Step 2: Request verification email
        print("\n[2/3] Requesting verification email...")

        request_response = session.post(
            REQUEST_URL,
            headers=headers,
            timeout=TIMEOUT,
        )

        print_response("Verification request", request_response)

        if not request_response.ok:
            print("Verification request failed. Stopping.")
            return

        # Step 3: Confirm using the token from the email
        print("\nCheck your inbox for the verification email.")
        token = input("Paste the verification token: ").strip()

        if not token:
            print("Verification token is required.")
            return

        print("\n[3/3] Confirming email verification...")

        confirm_response = session.post(
            CONFIRM_URL,
            json={"token": token},
            timeout=TIMEOUT,
        )

        print_response("Verification confirmation", confirm_response)

        if confirm_response.ok:
            print("\nEmail verification completed successfully.")
        else:
            print("\nEmail verification failed.")

    except requests.RequestException as exc:
        print(f"\nRequest failed: {exc}")


if __name__ == "__main__":
    main()
