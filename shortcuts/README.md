# Four iOS Shortcuts automations

Keep whichcard running on your computer. Replace `<host>` with its trusted LAN
IP or private Tailscale host; use HTTPS if you configured a private HTTPS proxy.
Test `http://<host>:8787/api/now?category=dining` in Safari first. These are manual
recipes: signed `.shortcut` files cannot be generated here. No bank login or API
key is needed. Network calls go only to your own server.

For each recipe, open **Shortcuts → Automation → + → Create Personal Automation**
(the label may be simply **New Automation**). Choose **Run Immediately**, or turn
off **Ask Before Running** where that switch is shown; confirm **Don't Ask** if
prompted. iOS may still require approval for location-based automations.

## 1. When Uber Eats opens

1. Trigger: **App → Choose → Uber Eats → Is Opened** (not Is Closed).
2. Action: **Get Contents of URL**. URL:
   `http://<host>:8787/api/now?app=ubereats`. Method: **GET**. No headers/body.
3. Action: **Get Dictionary Value**. Mode **Value**, key `notification_text`,
   dictionary input **Contents of URL** from step 2.
4. Action: **Show Notification**. Body: **Dictionary Value** from step 3.
   Title (optional): `whichcard`. Save the automation.

## 2. When Wallet opens

1. Trigger: **App → Choose → Wallet → Is Opened**.
2. **Get Contents of URL**, method **GET**:
   `http://<host>:8787/api/now?app=wallet`.
3. **Get Dictionary Value**: key `notification_text`, input **Contents of URL**.
4. **Show Notification**: body **Dictionary Value**, title `whichcard`.
   This context is deliberately broad; use Now to enter a merchant/amount when
   the flat-rate result or bonus priority does not match the intended purchase.

## 3. On arrival at a pinned place

1. In whichcard **Settings → Pinned places**, enter a name, merchant ID,
   latitude, longitude and radius in meters. The location button can fill the
   coordinates in a secure browser context.
2. In Shortcuts Automation choose **Arrive**, choose that same address/location,
   and select **Any Time**. Use the arrival radius appropriate for that venue.
3. Add **Get Contents of URL**, method **GET**. Replace coordinates with the
   exact pinned coordinates, for example:
   `http://<host>:8787/api/now?lat=37.7858&lon=-122.4064`.
4. **Get Dictionary Value**: key `notification_text`, input **Contents of URL**.
5. **Show Notification**: body **Dictionary Value**, title `whichcard`.
   Pinned places resolve before airports. Within 3 km of a known airport, the
   coordinate endpoint can instead return an unverified lounge-access summary.

## 4. Daily 8 am summary

1. Trigger: **Time of Day → 8:00 AM → Repeat Daily**. Use the phone's local time.
2. **Get Contents of URL**, method **GET**:
   `http://<host>:8787/api/now?summary=true`.
3. **Get Dictionary Value**: key `notification_text`, input **Contents of URL**.
4. **Show Notification**: body **Dictionary Value**, title `whichcard today`.
   The response summarizes bonus risk and unused credits, with the full details
   available in Wallet and Ask.

## Connectivity and privacy

The phone and computer must be able to reach each other. On Wi-Fi, use the
computer's LAN address; away from home, a private Tailscale connection can provide
reachability. Do not forward port 8787 to the public internet: whichcard has no
user accounts/authentication. Shortcuts HTTP requests work without a browser
service worker. Geolocation/installable PWA features require HTTPS on a phone;
see `RUNBOOK.md`. If the computer sleeps or the server is stopped, the automation
cannot fetch a new result. Every `notification_text` is under 120 characters.
