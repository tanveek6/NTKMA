# Free Deployment: Hugging Face Spaces

Recommended free option: Hugging Face Spaces with Docker.

## 1. Create the Space

1. Go to https://huggingface.co/spaces
2. Click **Create new Space**.
3. Name it something like `ntkma-media-dashboard`.
4. Choose **Docker** as the SDK.
5. Choose the free CPU hardware.
6. Keep it private while testing if you do not want the link public yet.

## 2. Upload or push this project

Upload/push these project files to the Space repository:

- `Dockerfile`
- `.dockerignore`
- `requirements.txt`
- `README.md`
- `app/`
- `scripts/`

Do not upload `.venv/`, `uploads/`, `data/local_db.json`, `.env`, or the Firebase service-account JSON file.

## 3. Add Firebase secrets

In the Space, open **Settings > Variables and secrets** and add:

- `FIREBASE_CREDENTIALS_JSON` = minified content of your Firebase service-account JSON
- `FIREBASE_PROJECT_ID` = `ntkma-media-system`
- `AUTO_SCRAPE_ENABLED` = `true`
- `AUTO_SCRAPE_MINUTES` = `15`
- `SCRAPE_LIMIT` = `50`

Optional, only after Firebase Storage is enabled:

- `FIREBASE_STORAGE_BUCKET` = your bucket name, for example `ntkma-media-system.appspot.com` or `ntkma-media-system.firebasestorage.app`

PowerShell command to create the one-line Firebase secret value:

```powershell
Get-Content "C:\Users\tanvi\Downloads\ntkma-media-system-firebase-adminsdk-fbsvc-1f3895c4ff.json" -Raw | ConvertFrom-Json | ConvertTo-Json -Compress
```

Copy the output and paste it as the `FIREBASE_CREDENTIALS_JSON` secret.

## 4. Public manager URL

After the build finishes, Hugging Face shows a public app link. It usually looks like:

```text
https://YOUR-HF-USERNAME-ntkma-media-dashboard.hf.space
```

You can send that URL to your manager.

## 5. Verify after deploy

Open these URLs:

```text
https://YOUR-HF-USERNAME-ntkma-media-dashboard.hf.space/
https://YOUR-HF-USERNAME-ntkma-media-dashboard.hf.space/api/health
https://YOUR-HF-USERNAME-ntkma-media-dashboard.hf.space/api/brief
```

`/api/health` should show `backend: firebase` and `firestore: true`.
