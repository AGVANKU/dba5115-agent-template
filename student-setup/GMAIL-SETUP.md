# Gmail API Setup Guide

This guide walks you through setting up Gmail API credentials for your own Gmail account. This allows the agent platform to read emails from and send emails through your Gmail account.

> **Note:** This setup is optional. Your instructor may provide shared credentials for the course. Only follow this guide if you want to use your own Gmail account.

---

## Overview

To access Gmail programmatically, you need:

1. **Google Cloud Project** — A container for your API credentials
2. **OAuth 2.0 Credentials** — Client ID and Client Secret
3. **Refresh Token** — A long-lived token that allows the app to access your Gmail

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Google Cloud   │      │  OAuth 2.0      │      │  Your Gmail     │
│  Console        │ ───► │  Credentials    │ ───► │  Account        │
│  (setup once)   │      │  (Client ID/    │      │  (read/send     │
│                 │      │   Secret)       │      │   emails)       │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

---

## Step 1: Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/)

2. Sign in with the Google account you want to use for sending emails

3. Click the project dropdown at the top of the page (next to "Google Cloud")

4. Click **New Project**

5. Enter project details:
   - **Project name:** `DBA5115-Gmail-Agent` (or any name you prefer)
   - **Organization:** Leave as default or select your organization

6. Click **Create**

7. Wait for the project to be created (30 seconds to 1 minute)

8. Make sure your new project is selected in the dropdown

---

## Step 2: Enable the Gmail API

1. In the Google Cloud Console, go to **APIs & Services** → **Library**
   - Or use this direct link: [API Library](https://console.cloud.google.com/apis/library)

2. Search for **"Gmail API"**

3. Click on **Gmail API** in the results

4. Click **Enable**

5. Wait for the API to be enabled

---

## Step 3: Configure OAuth Consent Screen

Before creating credentials, you must configure the OAuth consent screen. This defines what users see when authorizing your app.

1. Go to **APIs & Services** → **OAuth consent screen**
   - Or use: [OAuth Consent Screen](https://console.cloud.google.com/apis/credentials/consent)

2. Select **User Type**:
   - Choose **External** (unless you have a Google Workspace organization)
   - Click **Create**

3. Fill in the **App information**:
   - **App name:** `DBA5115 Gmail Agent`
   - **User support email:** Select your email
   - **App logo:** Skip (optional)

4. Skip the **App domain** section (leave blank)

5. Fill in **Developer contact information**:
   - Enter your email address

6. Click **Save and Continue**

7. **Scopes** page:
   - Click **Add or Remove Scopes**
   - In the filter box, search for `gmail`
   - Select these scopes:
     - `https://www.googleapis.com/auth/gmail.readonly` (Read emails)
     - `https://www.googleapis.com/auth/gmail.send` (Send emails)
     - `https://www.googleapis.com/auth/gmail.modify` (Mark as read)
   - Click **Update**
   - Click **Save and Continue**

8. **Test users** page:
   - Click **Add Users**
   - Enter your Gmail address (the one you'll use with the agent)
   - Click **Add**
   - Click **Save and Continue**

9. Review the summary and click **Back to Dashboard**

---

## Step 4: Create OAuth 2.0 Credentials

1. Go to **APIs & Services** → **Credentials**
   - Or use: [Credentials](https://console.cloud.google.com/apis/credentials)

2. Click **Create Credentials** → **OAuth client ID**

3. Select **Application type:** `Web application`

   > **Important:** You must select **Web application** (not "Desktop app"). We need this type because we will use Google's OAuth Playground to generate a refresh token, and the Playground requires a web application client with its redirect URI whitelisted. Selecting "Desktop app" will cause a `redirect_uri_mismatch` error in the next step.

4. Enter **Name:** `DBA5115 Web Client`

5. Under **Authorized redirect URIs**, click **Add URI** and enter:
   ```
   https://developers.google.com/oauthplayground
   ```
   This allows the OAuth Playground to receive the authorization response.

6. Click **Create**

7. A dialog appears with your credentials:
   - **Client ID:** `xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com`
   - **Client Secret:** `GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx`

8. Click **Download JSON** to save the credentials file
   - Keep this file safe — you'll need it in the next step

9. Click **OK** to close the dialog

---

## Step 5: Generate a Refresh Token

The refresh token allows the application to access your Gmail without requiring you to log in each time. We'll use Google's OAuth 2.0 Playground to generate it.

### 5a: Configure OAuth Playground

1. Go to [OAuth 2.0 Playground](https://developers.google.com/oauthplayground/)

2. Click the **gear icon** (⚙️) in the top right corner

3. Check **"Use your own OAuth credentials"**

4. Enter your credentials from Step 4:
   - **OAuth Client ID:** Paste your Client ID
   - **OAuth Client Secret:** Paste your Client Secret

5. Click **Close**

### 5b: Authorize Gmail Scopes

1. In the left panel, find **"Gmail API v1"** and expand it

2. Select these scopes (check the boxes):
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/gmail.modify`

3. Click **Authorize APIs**

4. A Google sign-in page opens:
   - Sign in with the Gmail account you want to use
   - You may see a warning "Google hasn't verified this app"
   - Click **Advanced** → **Go to DBA5115 Gmail Agent (unsafe)**
   - Click **Continue**

5. Review the permissions and click **Allow**

6. You'll be redirected back to OAuth Playground

### 5c: Exchange for Refresh Token

1. You should now be on **"Step 2: Exchange authorization code for tokens"**

2. Click **Exchange authorization code for tokens**

3. The response panel shows your tokens:
   ```json
   {
     "access_token": "ya29.xxxxx...",
     "refresh_token": "1//xxxxx...",
     "scope": "https://www.googleapis.com/auth/gmail...",
     "token_type": "Bearer",
     "expires_in": 3599
   }
   ```

4. **Copy the `refresh_token` value** — this is what you need!
   - It starts with `1//` followed by a long string
   - This token does not expire (unless you revoke it)

---

## Step 6: Configure Your Environment

Add these values to your `local.settings.json` or `.env` file:

```json
{
  "Values": {
    "GMAIL_CLIENT_ID": "xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com",
    "GMAIL_CLIENT_SECRET": "GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx",
    "GMAIL_REFRESH_TOKEN": "1//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "GMAIL_FROM_NAME": "My Agent",
    "GMAIL_FROM_EMAIL": "your-email@gmail.com"
  }
}
```

Or for `.env`:
```
GMAIL_CLIENT_ID=xxxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx.apps.googleusercontent.com
GMAIL_CLIENT_SECRET=GOCSPX-xxxxxxxxxxxxxxxxxxxxxxxx
GMAIL_REFRESH_TOKEN=1//xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GMAIL_FROM_NAME=My Agent
GMAIL_FROM_EMAIL=your-email@gmail.com
```

---

## Verification

To verify your setup works:

1. Start the function app locally:
   ```bash
   func start
   ```

2. Trigger a Gmail pull:
   ```bash
   curl -X POST http://localhost:7071/api/hooks/gmail_pull
   ```

3. Check the logs for:
   - `Gmail API: Fetching unread messages...` — API connection works
   - `Found X unread email(s)` — Successfully reading inbox

---

## Troubleshooting

### "Token has been expired or revoked"

Your refresh token may have been invalidated. This can happen if:
- You changed your Google password
- You revoked access in your Google Account settings
- The OAuth consent screen is still in "Testing" mode and 7 days passed

**Solution:** Repeat Step 5 to generate a new refresh token.

### "Error 400: redirect_uri_mismatch"

The OAuth client type is set to "Desktop app" instead of "Web application", or the redirect URI is missing.

**Solution:**
1. Go to **APIs & Services** → **Credentials**
2. Delete the existing OAuth client (or edit it)
3. Create a new OAuth client with type **Web application**
4. Add `https://developers.google.com/oauthplayground` under **Authorized redirect URIs**
5. Use the new Client ID and Client Secret in the OAuth Playground

### "Access blocked: This app's request is invalid"

The OAuth consent screen configuration may be incomplete.

**Solution:** Go back to Step 3 and ensure all required fields are filled in.

### "Error 403: access_denied"

You're trying to access a Gmail account that isn't in the test users list.

**Solution:** Add the Gmail address to the test users in the OAuth consent screen (Step 3.8).

### "invalid_grant" error

The authorization code expired before you could exchange it for tokens.

**Solution:** Repeat Step 5 — the authorization code is only valid for a few minutes.

### Emails not being sent / "Insufficient Permission"

The send scope may not be authorized.

**Solution:** Ensure `https://www.googleapis.com/auth/gmail.send` is selected in Step 5b.

---

## Publishing Your App (Optional)

If your app is in "Testing" mode, refresh tokens expire after 7 days. To make them permanent:

1. Go to **OAuth consent screen**
2. Click **Publish App**
3. Confirm the warning

> **Note:** Published apps may require Google verification if used by many users. For personal/course use, this is usually not necessary.

---

## Security Best Practices

1. **Never commit credentials to git** — Add `local.settings.json` and `.env` to `.gitignore`

2. **Use a dedicated Gmail account** — Don't use your primary personal email

3. **Limit scopes** — Only request the permissions you actually need

4. **Rotate credentials** — If you suspect they've been compromised, revoke and regenerate

5. **Monitor access** — Check [Google Account Security](https://myaccount.google.com/security) periodically

---

## Revoking Access

To revoke the app's access to your Gmail:

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Scroll to **"Third-party apps with account access"**
3. Click **Manage third-party access**
4. Find **DBA5115 Gmail Agent** and click **Remove Access**

This immediately invalidates all tokens. You'll need to repeat the setup if you want to use the app again.

---

## Quick Reference

| Item | Where to Find It |
|------|------------------|
| Client ID | Google Cloud Console → Credentials |
| Client Secret | Google Cloud Console → Credentials |
| Refresh Token | OAuth Playground → Step 2 response |
| Project Dashboard | [console.cloud.google.com](https://console.cloud.google.com) |
| OAuth Playground | [developers.google.com/oauthplayground](https://developers.google.com/oauthplayground/) |
| Revoke Access | [myaccount.google.com/security](https://myaccount.google.com/security) |
