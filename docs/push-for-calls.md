# Push Notifications for Calls

This guide explains how to set up VoIP push notifications so that incoming SIP calls wake up offline iOS and Android clients.

## How It Works

```
Caller → Kamailio INVITE → callee not registered?
         │                        │
         │                        ▼
         │                  Kamailio POSTs to
         │                  api:8443/api/v1/push/call-notify
         │                        │
         │                        ▼
         │                  API looks up push tokens
         │                  in push_registrations table
         │                        │
         │               ┌────────┴────────┐
         │               ▼                 ▼
         │          APNs VoIP push    FCM high-priority
         │          (iOS)             data message (Android)
         │                                 │
         ▼                                 ▼
    Kamailio returns              Client wakes up,
    480 Temporarily               re-registers with SIP,
    Unavailable                   caller retries INVITE
```

1. A SIP INVITE arrives at Kamailio for a callee who is not currently registered.
2. Kamailio's `route[PUSH]` posts a JSON webhook to the API's `/api/v1/push/call-notify` endpoint (internal Docker network, no JWT).
3. The API looks up all push tokens for that callee in the `push_registrations` table.
4. For each token it sends a platform-specific push (APNs VoIP or FCM data-only).
5. Kamailio responds `480 Temporarily Unavailable` to the caller. The client app is expected to retry after receiving the push and re-registering.

The push payload contains **only** `caller_name`, `call_id`, and `call_type` — no message content.

---

## iOS (APNs) Setup

### 1. Create an APNs Key

1. Go to [Apple Developer → Certificates, Identifiers & Profiles → Keys](https://developer.apple.com/account/resources/authkeys/list).
2. Click **+**, enable **Apple Push Notifications service (APNs)**, and create the key.
3. Download the `.p8` file (you can only download it once).
4. Note the **Key ID** (10-character string shown on the key page).
5. Note your **Team ID** (top-right of the developer portal, or Account → Membership).

### 2. Configure Your App

Your iOS app must:
- Register a `PKPushRegistry` with type `.voIP` to receive VoIP pushes.
- Report an incoming call to `CallKit` immediately upon receiving the push (required by Apple or the app will be terminated).
- On launch/login, send the VoIP push token to `POST /api/v1/push/register` with `platform: "ios"`.

### 3. Set Environment Variables

Place the `.p8` key file somewhere the API container can read it (the default path is `/etc/veil/apns_key.p8`).

```env
APNS_KEY_PATH=/etc/veil/apns_key.p8    # Path to the .p8 key file inside the container
APNS_KEY_ID=ABC123DEFG                  # 10-character Key ID from Apple
APNS_TEAM_ID=TEAMID1234                 # Your Apple Developer Team ID
APNS_BUNDLE_ID=com.yourcompany.veil     # Your app's bundle identifier
```

If deploying with Docker Compose, mount the key file as a volume:

```yaml
# docker-compose.yml — api service
volumes:
  - ./secrets/apns_key.p8:/etc/veil/apns_key.p8:ro
```

### 4. Sandbox vs Production

By default the APNs client connects to the **sandbox** gateway (for development builds). Set this to `false` for production/TestFlight:

```env
APNS_USE_SANDBOX=false
```

---

## Android (FCM) Setup

### 1. Create a Firebase Project

1. Go to the [Firebase Console](https://console.firebase.google.com/) and create a project (or use an existing one).
2. Add your Android app (package name must match your app).
3. Download `google-services.json` and add it to your Android app module.

### 2. Generate a Service Account Key

1. In the Firebase Console go to **Project Settings → Service Accounts**.
2. Click **Generate new private key**. This downloads a JSON file.
3. Place this file somewhere the API container can read it (default: `/etc/veil/fcm_service_account.json`).

### 3. Configure Your App

Your Android app must:
- Include `firebase-messaging` dependency.
- Implement a `FirebaseMessagingService` that handles data messages with `type: "call"`.
- Show a full-screen incoming call notification (or use `ConnectionService` / `TelecomManager` on Android 10+).
- On launch/login, send the FCM token to `POST /api/v1/push/register` with `platform: "android"`.

### 4. Set Environment Variables

```env
FCM_SERVICE_ACCOUNT_PATH=/etc/veil/fcm_service_account.json
```

Mount it in Docker Compose:

```yaml
# docker-compose.yml — api service
volumes:
  - ./secrets/fcm_service_account.json:/etc/veil/fcm_service_account.json:ro
```

---

## Client API Calls

### Register a Push Token

After login, the client registers its device push token:

```
POST /api/v1/push/register
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "jid": "alice@example.com",
  "device_id": "550e8400-e29b-41d4-a716-446655440000",
  "platform": "ios",
  "push_token": "<apns-voip-token-or-fcm-token>",
  "app_id": "com.yourcompany.veil"
}
```

- `device_id`: a stable UUID per device (persisted in the app's local storage).
- `platform`: `"ios"` or `"android"`.
- `push_token`: the VoIP push token (iOS) or FCM registration token (Android).

### Deregister on Logout

```
DELETE /api/v1/push/register
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "jid": "alice@example.com",
  "device_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Push Payload

The payload sent to the device contains only:

| Field | Description |
|-------|-------------|
| `caller_name` | Display name (or username) of the caller |
| `call_id` | SIP Call-ID for correlation |
| `call_type` | `"audio"` or `"video"` |

No message content or metadata beyond this is included.

On **iOS**, the push arrives as a PushKit VoIP notification. On **Android**, it arrives as a high-priority FCM data message with an additional `type: "call"` field.

---

## Bad Token Cleanup

The API automatically removes push tokens that are rejected by APNs or FCM (e.g. uninstalled apps, expired tokens). No manual cleanup is needed.

---

## Verifying It Works

1. Register a user and log in to get a JWT.
2. Register a push token via `POST /api/v1/push/register`.
3. Make sure the user is **not** registered with Kamailio (SIP offline).
4. Have another user send a SIP INVITE to the offline user.
5. Check the API logs — you should see the push webhook arrive and the push being sent.
6. Check Kamailio logs for the `Push webhook result` xlog line.

To test without a real device, you can call the webhook directly:

```bash
curl -X POST http://localhost:8443/api/v1/push/call-notify \
  -H "Content-Type: application/json" \
  -d '{
    "callee_username": "bob",
    "caller_username": "alice",
    "caller_display_name": "Alice",
    "call_id": "test-call-123",
    "call_type": "audio"
  }'
```

---

## Troubleshooting

| Symptom | Check |
|---------|-------|
| `APNs not configured` in logs | `APNS_KEY_PATH`, `APNS_KEY_ID`, and `APNS_TEAM_ID` must all be set and the `.p8` file must exist at the path |
| `APNs rejected push: BadDeviceToken` | The push token is invalid — make sure the app is sending the VoIP token (from `PKPushRegistry`), not the regular remote notification token |
| `APNs rejected push: TopicDisallowed` | `APNS_BUNDLE_ID` doesn't match the app, or the key isn't enabled for push |
| Sandbox vs production mismatch | Development builds use sandbox APNs; TestFlight/App Store use production. Set `APNS_USE_SANDBOX` accordingly |
| `FCM not configured` in logs | `FCM_SERVICE_ACCOUNT_PATH` must point to a valid Firebase service account JSON |
| `FCM token unregistered` | The app was uninstalled or the token expired — the token is auto-cleaned |
| Push sent but app doesn't wake | iOS: verify `PKPushRegistry` + `CallKit` integration. Android: verify `FirebaseMessagingService` handles data-only messages and the app has unrestricted battery optimization |
| `No push registrations found` | The callee never called `/push/register`, or logged out (which deregisters) |
