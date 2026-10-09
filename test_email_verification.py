# test_email_verification.py
import requests
import getpass

BASE_URL = "http://localhost:8000/api/v1"

SIGNUP_URL = f"{BASE_URL}/auth/register/"
LOGIN_URL = f"{BASE_URL}/auth/login/"
VERIFICATION_URL = f"{BASE_URL}/auth/email-verification/request/"


def print_response(title, response):
    print(f"\n--- {title} ---")
    print(f"Status: {response.status_code}")

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

    # Step 1: Sign up
    print("\n[1/3] Signing up...")

    signup_payload = {
        "first_name": email,
        "email": email,
        "password": password,
        "confirm_password": password,
    }

    try:
        signup_response = session.post(
            SIGNUP_URL,
            json=signup_payload,
            timeout=30,
        )
        print_response("Signup", signup_response)

        if signup_response.status_code in (200, 201):
            print("Signup successful.")
        else:
            print("Signup did not succeed; attempting login.")
            print("This may happen if the account already exists.")

        # Step 2: Login
        print("\n[2/3] Logging in...")

        login_payload = {
            "credential": email,
            "password": password,
        }

        login_response = session.post(
            LOGIN_URL,
            json=login_payload,
            timeout=30,
        )
        print_response("Login", login_response)

        if not login_response.ok:
            print("Login failed. Verification request skipped.")
            return

        login_data = login_response.json()
        access_token = login_data.get("access")

        if not access_token:
            print("No access token found in the login response.")
            return

        # Step 3: Request email verification
        print("\n[3/3] Requesting email verification...")

        verification_response = session.post(
            VERIFICATION_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        print_response("Email verification request", verification_response)

        if verification_response.ok:
            print("\nFlow completed. Check your inbox.")
        else:
            print("\nVerification request was not successful.")

    except requests.RequestException as exc:
        print(f"\nAPI request failed: {exc}")


if __name__ == "__main__":
    main()
