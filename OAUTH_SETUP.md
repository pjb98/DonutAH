# DonutDex OAuth Setup

The account system supports Discord, Google, and Microsoft OAuth.

## Required Environment

Set these on `donut-market-dashboard.service`:

```text
DONUTDEX_PUBLIC_BASE_URL=http://147.93.176.190:8095
DONUTDEX_AUTH_SECRET=<long random secret>

DISCORD_CLIENT_ID=<discord client id>
DISCORD_CLIENT_SECRET=<discord client secret>

GOOGLE_CLIENT_ID=<google client id>
GOOGLE_CLIENT_SECRET=<google client secret>

MICROSOFT_CLIENT_ID=<microsoft client id>
MICROSOFT_CLIENT_SECRET=<microsoft client secret>
```

Use `DONUTDEX_COOKIE_SECURE=1` only after the site is served over HTTPS.

## Redirect URLs

Configure these callback URLs in the provider dashboards:

```text
http://147.93.176.190:8095/auth/discord/callback
http://147.93.176.190:8095/auth/google/callback
http://147.93.176.190:8095/auth/microsoft/callback
```

If DonutDex later moves to a domain or HTTPS, update `DONUTDEX_PUBLIC_BASE_URL`
and the provider callback URLs to match exactly.

## Account History

Users can set their account name and Minecraft name on `/account`.

When the Minecraft name matches the seller name in Donut auction sales, the
account page shows that player's recorded sales history. The current Donut data
available to this dashboard exposes seller-side history; buyer history can be
added later if the API exposes buyer names.
