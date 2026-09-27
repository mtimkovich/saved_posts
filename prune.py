"""Deletes cached users (and their posts) that haven't been refreshed in
over a year. Safe to run repeatedly; run on a schedule (e.g. a systemd
timer) to keep the database from growing unbounded with stale caches
from one-time visitors.
"""
from app import app
import models

if __name__ == '__main__':
    with app.app_context():
        removed = models.prune_stale(days=365)
        print('Removed {} stale cached user(s)'.format(removed))
