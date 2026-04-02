# Storyboard Visual Engine v7 — Cloud Edition

Use from your phone, anywhere. Same 7-layer consistency engine.

## Deploy to Railway.app (Recommended — $5/mo)

1. Go to [railway.app](https://railway.app) → Sign up with GitHub
2. Click "New Project" → "Deploy from GitHub repo"
3. Upload this folder to a GitHub repo first:
   ```
   git init
   git add .
   git commit -m "storyboard engine v7"
   git remote add origin https://github.com/YOUR_USERNAME/storyboard-engine.git
   git push -u origin main
   ```
4. Railway auto-detects Python → deploys automatically
5. Railway gives you a URL like `https://storyboard-engine-xxxxx.up.railway.app`
6. Open that URL on your phone → done!

## Deploy to Render.com (Free tier available)

1. Go to [render.com](https://render.com) → Sign up
2. New → Web Service → Connect GitHub repo
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 600`
5. Deploy → get URL → open on phone

## Run Locally (free, same wifi)

```bash
pip install -r requirements.txt
python app.py
```

Open on phone: `http://YOUR_PC_IP:5000`
(Find your IP: run `ipconfig` on Windows)

## Files

```
storyboard-cloud/
├── app.py              ← Web server (Flask)
├── engine.py           ← Generation engine (7 layers)
├── templates/
│   └── index.html      ← Mobile-first UI
├── requirements.txt    ← Python packages
├── Procfile            ← Railway/Render config
├── railway.json        ← Railway config
└── README.md           ← You're reading this
```

## Usage

1. Open URL in phone browser
2. Paste Gemini API key (saves automatically)
3. Pick style preset + resolution + aspect ratio
4. Upload storyboard .jsx file
5. Tap buttons: Characters → Envs → Masters → Scenes → Grade → Export
6. Watch real-time progress
7. Export → opens visual production bible in browser
