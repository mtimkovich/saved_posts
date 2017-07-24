from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(20), index=True, unique=True)
    created = db.Column(db.DateTime, default=datetime.now())
    saved = db.relationship('Post', cascade="all,delete-orphan", backref='user', lazy='dynamic')

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return 'User({})'.format(self.name)

class Post(db.Model):
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
        return 'Post({}, {})'.format(self.title, self.subreddit)


def write_to_db(user, subreddits):
    u = User(user)

    for sub, posts in subreddits:
        for post in posts:
            u.saved.append(Post(sub, post['title'], post['url']))

    db.session.add(u)
    db.session.commit()


def read_from_db(user):
    u = User.query.filter_by(name=user).first()
    saved_items = {}

    for post in u.saved:
        sub = post.subreddit
        if sub not in saved_items:
            saved_items[sub] = []
        saved_items[sub].append({'title': post.title, 'url': post.url})

    return sorted(saved_items.items())

