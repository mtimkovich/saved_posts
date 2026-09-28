from datetime import datetime, timedelta, timezone

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_
from sqlalchemy.sql import func

db = SQLAlchemy()


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), index=True, unique=True)
    created = db.Column(db.DateTime(), default=func.now())
    syncing = db.Column(db.Boolean, default=False, nullable=False)
    syncing_since = db.Column(db.DateTime(), nullable=True)
    saved = db.relationship('Post', cascade="all,delete-orphan", backref='user', lazy='dynamic')

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'User({})'.format(self.name)

    def cached(self):
        return self.created.strftime('%Y-%m-%d %H:%M')


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subreddit = db.Column(db.String(20))
    title = db.Column(db.String(300))
    url = db.Column(db.Text())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), index=True)
    fetched_at = db.Column(db.DateTime(), default=func.now())

    def __init__(self, subreddit, title, url):
        self.subreddit = subreddit
        self.title = title
        self.url = url

    def __repr__(self):
        return 'Post({}, {}, {})'.format(self.subreddit, self.user, self.title)


def write_to_db(user, subreddits):
    u = User.query.filter_by(name=user).first()

    if u is None:
        u = User(user)
        db.session.add(u)

    # All posts from this batch share one timestamp (rather than each row's
    # own default at INSERT time), so a later "update" batch reliably sorts
    # before an older one even if writing many rows spans a couple of
    # seconds. Within a batch, insertion order (id) already matches
    # reddit's newest-first listing order, and serves as the tiebreaker.
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for sub, posts in subreddits:
        for post in posts:
            new_post = Post(sub, post['title'], post['url'])
            new_post.fetched_at = now
            u.saved.append(new_post)

    u.created = func.now()
    db.session.commit()

    return u


SYNC_STALE_SECONDS = 300  # comfortably longer than gunicorn's request timeout,
                          # so a lock is only ever reclaimed as "stale" once
                          # the original request could no longer still be running


def try_start_sync(username, stale_seconds=SYNC_STALE_SECONDS):
    """Atomically claims the per-user sync lock, so two concurrent
    fetches (e.g. a re-fetch and an update racing, or a double-submit)
    can't both write their own copies of the same posts. Returns True if
    the lock was claimed, False if a sync is already in progress.

    A lock held longer than `stale_seconds` is treated as abandoned (e.g.
    the worker handling it was killed mid-fetch, so nothing ever reached
    finish_sync) and can be reclaimed rather than blocking forever."""
    u = User.query.filter_by(name=username).first()
    if u is None:
        return True

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(seconds=stale_seconds)

    rowcount = User.query.filter(
        User.name == username,
        or_(User.syncing.is_(False), User.syncing_since < cutoff),
    ).update({'syncing': True, 'syncing_since': now})
    db.session.commit()

    return rowcount > 0


def finish_sync(username):
    User.query.filter_by(name=username).update({'syncing': False, 'syncing_since': None})
    db.session.commit()


def prune_stale(days=365):
    """Deletes cached users (and their posts, via cascade) whose cache
    hasn't been refreshed in over `days` days. Returns the number removed."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    stale = User.query.filter(User.created < cutoff).all()

    for u in stale:
        db.session.delete(u)
    db.session.commit()

    return len(stale)


def read_from_db(user):
    u = User.query.filter_by(name=user).first()
    saved_items = {}

    posts = u.saved.order_by(Post.fetched_at.desc(), Post.id.asc())
    for post in posts:
        sub = post.subreddit
        if sub not in saved_items:
            saved_items[sub] = []
        saved_items[sub].append({'title': post.title, 'url': post.url})

    return sorted(saved_items.items(), key=lambda s: s[0].lower())
