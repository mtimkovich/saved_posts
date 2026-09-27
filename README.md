# Saved Posts for Reddit

Get all your saved reddit posts and organize them by subreddit.

## Setup

Requires Python 3.9+ (tested on 3.14).

```bash
python -m venv venv
venv/Scripts/activate  # or source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Create `praw.ini` in the project root (this file is gitignored, since it
holds live credentials):

```ini
[saved]
client_id=your_reddit_app_client_id
client_secret=your_reddit_app_client_secret
user_agent=web:your.app.name:v1.0 (by /u/your_username)
redirect_uri=http://127.0.0.1:5000/callback
```

`client_id`/`client_secret` come from a "web app" registered at
https://www.reddit.com/prefs/apps. The `redirect_uri` there must exactly
match the one in `praw.ini`, and must point at wherever `/callback` is
actually served (e.g. your production domain once deployed).

Optionally set these environment variables (sane defaults are used
otherwise, fine for local dev):

- `SECRET_KEY` — Flask session signing key
- `DATABASE_URL` — SQLAlchemy database URI (defaults to a local SQLite file)

## Run (development)

Run from the project root (praw looks for `praw.ini` in the current
working directory):

```bash
python app.py
```

Serves at http://127.0.0.1:5000.

## Deploy (nginx + gunicorn + systemd)

Files in `deploy/` are templates — the placeholders (`server_name`, paths,
`User`/`Group`, `SECRET_KEY`) need to match your server.

The app serves all its routes under a `/saved_posts` prefix (see the `sp`
Blueprint in `app.py`), matching the original mount point, so it can sit
behind an existing site's nginx config as a plain passthrough — no path
rewriting needed.

1. On the server: `git clone` this repo to e.g. `/opt/saved_posts`, create
   `praw.ini` there with the production `redirect_uri`
   (`https://your-domain/saved_posts/callback`), and register that same URL
   on the reddit app's settings page.
2. `python -m venv venv && venv/bin/pip install -r requirements-prod.txt`
3. Make sure the app's working directory is writable by whichever user runs
   gunicorn (for the SQLite file), and copy/adapt:
   - `deploy/saved_posts.service` → `/etc/systemd/system/saved_posts.service`
     — `User`/`Group` must match whichever user nginx's worker process runs
     as, or the socket connect will fail with a permission error.
   - `deploy/nginx_saved_posts.conf` is a `location` block to paste into
     your *existing* server block (not a standalone one, since it's a path
     prefix on an existing domain).
4. `systemctl daemon-reload && systemctl enable --now saved_posts`
5. `nginx -t && systemctl reload nginx`
6. Put TLS in front of it (e.g. `certbot --nginx`) — reddit's OAuth callback
   should be `https://`.
