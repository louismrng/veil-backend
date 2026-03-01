#!/usr/bin/env python3
"""Seed script for veil-backend development.

Registers test users matching SwiftChatUI's MockXMPPService contacts,
sets up mutual roster entries, and optionally creates group chat rooms.

Usage:
    python scripts/seed_mock_data.py --api-url http://localhost:8443
    python scripts/seed_mock_data.py --api-url http://localhost:8443 --with-rooms
"""

import argparse
import sys

import httpx

# 10 contacts matching MockXMPPService.simulatedContacts + 1 test user
USERS = [
    ("testuser", "Test User"),
    ("alice", "Alice Johnson"),
    ("bob", "Bob Smith"),
    ("carol", "Carol Williams"),
    ("david", "David Brown"),
    ("eve", "Eve Davis"),
    ("frank", "Frank Miller"),
    ("jack", "Jack Black"),
    ("joe", "Joe Smith"),
    ("karen", "Karen White"),
    ("lisa", "Lisa Johnson"),
]

DEFAULT_PASSWORD = "password123"

# Group rooms matching MockXMPPService.simulatedRooms
ROOMS = [
    ("family", "Family Chat", ["alice", "bob", "carol", "david"]),
    ("work", "Work Team", ["alice", "bob", "carol", "david", "eve", "frank"]),
    ("bookclub", "Book Club", ["lisa", "karen", "carol"]),
    ("hikers", "Weekend Hikers", ["jack", "joe", "frank", "david", "alice", "bob", "eve"]),
    ("gamenight", "Game Night", ["jack", "bob", "frank"]),
]


def register_users(api_url: str) -> bool:
    """Register all users via the FastAPI registration endpoint.

    Returns True if all registrations succeeded (or already existed).
    """
    print("=== Registering users ===")
    ok = True
    with httpx.Client(verify=False, timeout=15.0) as client:
        for username, display_name in USERS:
            try:
                resp = client.post(
                    f"{api_url}/api/v1/account/register",
                    json={"username": username, "password": DEFAULT_PASSWORD},
                )
                if resp.status_code == 201:
                    print(f"  [OK] {username} ({display_name})")
                elif resp.status_code == 409:
                    print(f"  [SKIP] {username} already exists")
                else:
                    print(f"  [FAIL] {username}: {resp.status_code} {resp.text}")
                    ok = False
            except httpx.HTTPError as e:
                print(f"  [ERROR] {username}: {e}")
                ok = False
    return ok


def setup_rosters(ejabberd_api_url: str, domain: str) -> bool:
    """Add mutual roster entries between testuser and all contacts.

    Returns True if all roster operations succeeded.
    """
    print("\n=== Setting up rosters ===")
    ok = True
    contacts = [(u, n) for u, n in USERS if u != "testuser"]

    with httpx.Client(verify=False, timeout=15.0) as client:
        for username, display_name in contacts:
            # testuser -> contact
            try:
                resp = client.post(
                    f"{ejabberd_api_url}/add_rosteritem",
                    json={
                        "localuser": "testuser",
                        "localserver": domain,
                        "user": username,
                        "server": domain,
                        "nick": display_name,
                        "group": "",
                        "subs": "both",
                    },
                )
                if resp.status_code == 200:
                    print(f"  testuser -> {username}: [OK]")
                else:
                    print(f"  testuser -> {username}: [FAIL ({resp.status_code})] {resp.text}")
                    ok = False
            except httpx.HTTPError as e:
                print(f"  testuser -> {username}: [ERROR] {e}")
                ok = False

            # contact -> testuser
            try:
                resp = client.post(
                    f"{ejabberd_api_url}/add_rosteritem",
                    json={
                        "localuser": username,
                        "localserver": domain,
                        "user": "testuser",
                        "server": domain,
                        "nick": "Test User",
                        "group": "",
                        "subs": "both",
                    },
                )
                if resp.status_code == 200:
                    print(f"  {username} -> testuser: [OK]")
                else:
                    print(f"  {username} -> testuser: [FAIL ({resp.status_code})] {resp.text}")
                    ok = False
            except httpx.HTTPError as e:
                print(f"  {username} -> testuser: [ERROR] {e}")
                ok = False
    return ok


def create_rooms(ejabberd_api_url: str, domain: str) -> bool:
    """Create MUC rooms and add members.

    Returns True if all room operations succeeded.
    """
    print("\n=== Creating group rooms ===")
    ok = True
    muc_domain = f"muc.{domain}"

    with httpx.Client(verify=False, timeout=15.0) as client:
        for room_id, room_name, members in ROOMS:
            room_jid = f"{room_id}@{muc_domain}"

            # Create room with testuser as owner
            try:
                resp = client.post(
                    f"{ejabberd_api_url}/create_room_with_opts",
                    json={
                        "name": room_id,
                        "service": muc_domain,
                        "host": domain,
                        "options": [
                            {"name": "title", "value": room_name},
                            {"name": "persistent", "value": "true"},
                            {"name": "members_only", "value": "true"},
                            {"name": "allow_change_subj", "value": "true"},
                            {"name": "mam", "value": "true"},
                        ],
                    },
                )
                if resp.status_code == 200:
                    print(f"  Room {room_jid}: [OK]")
                else:
                    print(f"  Room {room_jid}: [FAIL ({resp.status_code})] {resp.text}")
                    ok = False
            except httpx.HTTPError as e:
                print(f"  Room {room_jid}: [ERROR] {e}")
                ok = False

            # Set testuser as owner
            try:
                client.post(
                    f"{ejabberd_api_url}/set_room_affiliation",
                    json={
                        "name": room_id,
                        "service": muc_domain,
                        "jid": f"testuser@{domain}",
                        "affiliation": "owner",
                    },
                )
            except httpx.HTTPError:
                pass

            # Add members
            for member in members:
                try:
                    resp = client.post(
                        f"{ejabberd_api_url}/set_room_affiliation",
                        json={
                            "name": room_id,
                            "service": muc_domain,
                            "jid": f"{member}@{domain}",
                            "affiliation": "member",
                        },
                    )
                    if resp.status_code == 200:
                        print(f"    + {member}: [OK]")
                    else:
                        print(f"    + {member}: [FAIL ({resp.status_code})] {resp.text}")
                        ok = False
                except httpx.HTTPError as e:
                    print(f"    + {member}: [ERROR] {e}")
                    ok = False
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed veil-backend with mock data")
    parser.add_argument("--api-url", default="http://localhost:8443", help="FastAPI base URL")
    parser.add_argument("--domain", default="localhost", help="XMPP domain")
    parser.add_argument("--with-rooms", action="store_true", help="Also create MUC rooms")
    args = parser.parse_args()

    # Derive ejabberd admin API URL from the FastAPI URL
    # FastAPI proxies to ejabberd, but for roster we need the ejabberd API directly
    # Default: https://localhost:5443/api
    ejabberd_api_url = f"https://{args.domain}:5443/api"
    if "://" in args.api_url:
        from urllib.parse import urlparse
        parsed = urlparse(args.api_url)
        ejabberd_api_url = f"https://{parsed.hostname}:5443/api"

    print(f"FastAPI URL: {args.api_url}")
    print(f"Ejabberd API URL: {ejabberd_api_url}")
    print(f"XMPP Domain: {args.domain}")
    print()

    had_errors = False

    if not register_users(args.api_url):
        had_errors = True

    if not setup_rosters(ejabberd_api_url, args.domain):
        had_errors = True

    if args.with_rooms:
        if not create_rooms(ejabberd_api_url, args.domain):
            had_errors = True

    print("\n=== Done ===")
    print(f"Login as: testuser / {DEFAULT_PASSWORD}")

    if had_errors:
        print("\nSome operations failed — check output above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
