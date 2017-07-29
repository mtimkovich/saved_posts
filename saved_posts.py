from flask import Flask, Blueprint, render_template, request, redirect, \
                  url_for, abort, session, flash
import os
import praw
import random
import string

from praw.models.reddit.submission import Submission
from praw.models.reddit.comment import Comment

import saved_posts.models as models
from saved_posts.models import db, User

os.chdir(os.path.dirname(os.path.abspath(__file__)))

saved_posts = Blueprint('sp', __name__, template_folder='templates')

reddit = praw.Reddit('saved')


def generate_state():
    return ''.join(random.choice(string.ascii_letters + string.digits)
                   for i in range(8))

@saved_posts.route('/callback')
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
        # TODO: Show on html
        # flash('Access Denied', 'error')
        # return redirect(url_for('index'))

    session['refresh'] = reddit.auth.authorize(code)
    user = reddit.user.me().name

    return render_template('sp/callback.html', redirect=url_for('sp.saved'))


@saved_posts.route('/delete')
def delete():
    refresh = session.get('refresh')

    if refresh is None:
        return redirect(url_for('sp.index'))

    reddit = praw.Reddit('saved', refresh_token=refresh)
    u = User.query.filter_by(name=reddit.user.me().name).first()
    db.session.delete(u)
    db.session.commit()

    return "removed user's saved posts from cache"


@saved_posts.route('/clear_cache')
def clear_cache():
    refresh = session.get('refresh')

    if refresh is None:
        return redirect(url_for('sp.index'))

    reddit = praw.Reddit('saved', refresh_token=refresh)
    u = User.query.filter_by(name=reddit.user.me().name).first()
    u.saved = []
    db.session.commit()

    return redirect(url_for('sp.saved'))


@saved_posts.route('/saved')
def saved():
    refresh = session.get('refresh')

    if refresh is None:
        return redirect(url_for('sp.index'))

    reddit = praw.Reddit('saved', refresh_token=refresh)

    redditor = reddit.user.me()

    user = User.query.filter_by(name=redditor.name).first()

    if user is not None and user.saved.count():
        saved_items = models.read_from_db(redditor.name)
        date = user.cached()
        return render_template('sp/index.html', user=redditor.name, date=date, saved_items=saved_items)

    subreddits = {}
    for post in redditor.saved(limit=None):
        if type(post) is Submission:
            title = post.title
            url = 'https://reddit.com' + post.permalink

        elif type(post) is Comment:
            body = post.body
            if len(body) > 300:
                body = body[:300-4] + '...'

            title = body
            url = 'https://reddit.com' + post.permalink(fast=True)

        sub = post.subreddit.display_name

        if sub not in subreddits:
            subreddits[sub] = []
        subreddits[sub].append({'title': title, 'url': url})

    saved_items = sorted(subreddits.items(), key=lambda s: s[0].lower())
    user = models.write_to_db(redditor.name, saved_items)

    date = user.cached()

    return render_template('sp/index.html', user=redditor.name, date=date, saved_items=saved_items)


@saved_posts.route('/')
def index():
    state = generate_state()
    session['state'] = state
    auth_url = reddit.auth.url(['identity', 'history'], state, 'permanent')
    return render_template('sp/register.html', auth_url=auth_url)
