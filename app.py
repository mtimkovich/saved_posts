import os
import random
import string

from flask import Flask, Blueprint, render_template, request, redirect, url_for, abort, session, flash
import praw
from praw.models.reddit.submission import Submission
from praw.models.reddit.comment import Comment
from prawcore.exceptions import PrawcoreException

from models import db, User
import models

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-me')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'saved_posts.db')
)
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() in ('1', 'true', 'yes')
db.init_app(app)

with app.app_context():
    db.create_all()

reddit = praw.Reddit('saved')

sp = Blueprint('sp', __name__, url_prefix='/saved_posts')


def generate_state():
    return ''.join(random.choice(string.ascii_letters + string.digits)
                    for i in range(8))


@sp.route('/callback')
def callback():
    code = request.args.get('code')
    state_get = request.args.get('state', '')
    error = request.args.get('error')

    state = session.get('state')

    if (error is not None or
            code is None or
            state is None or
            state != state_get):
        abort(403)

    try:
        refresh = reddit.auth.authorize(code)
        username = praw.Reddit('saved', refresh_token=refresh).user.me().name
    except PrawcoreException:
        flash('Reddit authorization failed. Please try again.')
        return redirect(url_for('sp.index'))

    session['refresh'] = refresh
    session['username'] = username

    return render_template('callback.html', redirect=url_for('sp.saved'))


def _authed_reddit_user(refresh):
    """Returns the logged-in Redditor, or None if the session's refresh
    token is no longer valid (revoked, expired, or a transient API error)."""
    try:
        user_reddit = praw.Reddit('saved', refresh_token=refresh)
        return user_reddit.user.me()
    except PrawcoreException:
        return None


def _post_to_item(post):
    """Returns (subreddit_name, {'title', 'url'}) for a saved Submission or
    Comment, or None if it's some other/unrecognized type."""
    if type(post) is Submission:
        title = post.title
        url = 'https://reddit.com' + post.permalink

    elif type(post) is Comment:
        body = post.body
        if len(body) > 300:
            body = body[:300 - 4] + '...'

        title = body
        url = 'https://reddit.com' + post.permalink

    else:
        return None

    return post.subreddit.display_name, {'title': title, 'url': url}


@sp.route('/delete', methods=['GET', 'POST'])
def delete():
    username = session.get('username')

    if username is None:
        flash('Please sign in first so we know whose data to delete.')
        return redirect(url_for('sp.index'))

    if request.method == 'GET':
        return render_template('delete_confirm.html')

    u = User.query.filter_by(name=username).first()
    if u is not None:
        db.session.delete(u)
        db.session.commit()

    session.pop('refresh', None)
    session.pop('username', None)

    return "removed user's saved posts from cache"


@sp.route('/logout', methods=['POST'])
def logout():
    session.pop('refresh', None)
    session.pop('username', None)
    return redirect(url_for('sp.index'))


@sp.route('/update', methods=['POST'])
def update():
    refresh = session.get('refresh')
    username = session.get('username')

    if refresh is None or username is None:
        return redirect(url_for('sp.index'))

    if not models.try_start_sync(username):
        flash('A refresh is already in progress for your account. Please wait a moment and try again.')
        return redirect(url_for('sp.saved'))

    try:
        redditor = _authed_reddit_user(refresh)
        if redditor is None:
            session.pop('refresh', None)
            session.pop('username', None)
            flash('Your reddit session expired. Please sign in again.')
            return redirect(url_for('sp.index'))

        user = User.query.filter_by(name=username).first()
        existing_urls = {post.url for post in user.saved} if user is not None else set()

        # Reddit's saved listing is newest-first, so we can stop as soon as
        # we see something we've already cached — everything after it is
        # older and already cached too.
        new_subreddits = {}
        try:
            for post in redditor.saved(limit=None):
                item = _post_to_item(post)
                if item is None:
                    continue
                sub, data = item
                if data['url'] in existing_urls:
                    break
                new_subreddits.setdefault(sub, []).append(data)
        except PrawcoreException:
            flash('Failed to check for new saved posts. Please try again.')
            return redirect(url_for('sp.saved'))

        new_items = sorted(new_subreddits.items(), key=lambda s: s[0].lower())
        models.write_to_db(username, new_items)

        total_new = sum(len(posts) for posts in new_subreddits.values())
        flash('Found {} new saved post(s).'.format(total_new) if total_new else 'No new saved posts found.')

        return redirect(url_for('sp.saved'))
    finally:
        models.finish_sync(username)


@sp.route('/clear_cache', methods=['POST'])
def clear_cache():
    username = session.get('username')

    if username is None:
        return redirect(url_for('sp.index'))

    u = User.query.filter_by(name=username).first()
    if u is not None:
        u.saved = []
        db.session.commit()

    return redirect(url_for('sp.saved'))


@sp.route('/saved')
def saved():
    refresh = session.get('refresh')
    username = session.get('username')

    if refresh is None or username is None:
        return redirect(url_for('sp.index'))

    user = User.query.filter_by(name=username).first()

    if user is not None and user.saved.count():
        saved_items = models.read_from_db(username)
        date = user.cached()
        total = sum(len(posts) for _, posts in saved_items)
        return render_template('index.html', user=username, date=date, saved_items=saved_items, total=total)

    # Cache miss: this is the only path that actually needs to talk to reddit.
    if not models.try_start_sync(username):
        flash('A refresh is already in progress for your account. Please wait a moment and try again.')
        return redirect(url_for('sp.saved'))

    try:
        redditor = _authed_reddit_user(refresh)
        if redditor is None:
            session.pop('refresh', None)
            session.pop('username', None)
            flash('Your reddit session expired. Please sign in again.')
            return redirect(url_for('sp.index'))

        subreddits = {}
        try:
            for post in redditor.saved(limit=None):
                item = _post_to_item(post)
                if item is None:
                    continue
                sub, data = item
                subreddits.setdefault(sub, []).append(data)
        except PrawcoreException:
            flash('Failed to fetch your saved posts from reddit. Please try again.')
            return redirect(url_for('sp.index'))

        saved_items = sorted(subreddits.items(), key=lambda s: s[0].lower())
        user = models.write_to_db(username, saved_items)

        date = user.cached()
        total = sum(len(posts) for _, posts in saved_items)

        return render_template('index.html', user=username, date=date, saved_items=saved_items, total=total)
    finally:
        models.finish_sync(username)


@sp.route('/')
def index():
    if session.get('refresh') and session.get('username'):
        auth_url = url_for('sp.saved')
    else:
        state = generate_state()
        session['state'] = state
        auth_url = reddit.auth.url(scopes=['identity', 'history'], state=state, duration='permanent')
    return render_template('register.html', auth_url=auth_url)


app.register_blueprint(sp)


if __name__ == '__main__':
    app.run(debug=True)
