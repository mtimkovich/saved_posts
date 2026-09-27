bind = 'unix:/run/saved_posts/saved_posts.sock'
workers = 2
umask = 0o007
# Fetching a large saved-posts history paginates through reddit's API and
# can take longer than gunicorn's 30s default, which would otherwise kill
# the worker mid-request.
timeout = 120
