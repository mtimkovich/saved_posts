from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class User(db.Model):
    __bind_key__ = 'saved'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), index=True, unique=True)
    created = db.Column(db.DateTime(), default=func.now())
    saved = db.relationship('Post', cascade="all,delete-orphan", backref='user', lazy='dynamic')

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'User({})'.format(self.name)

    def cached(self):
        return self.created.strftime('%Y-%m-%d %H:%M')


class Post(db.Model):
    __bind_key__ = 'saved'

    id = db.Column(db.Integer, primary_key=True)
    subreddit = db.Column(db.String(20))
    title = db.Column(db.String(300))
    url = db.Column(db.Text())
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

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

    for sub, posts in subreddits:
        for post in posts:
            u.saved.append(Post(sub, post['title'], post['url']))

    u.created = func.now()
    db.session.commit()

    return u


def read_from_db(user):
    u = User.query.filter_by(name=user).first()
    saved_items = {}

    for post in u.saved:
        sub = post.subreddit
        if sub not in saved_items:
            saved_items[sub] = []
        saved_items[sub].append({'title': post.title, 'url': post.url})

    return sorted(saved_items.items(), key=lambda s: s[0].lower())
