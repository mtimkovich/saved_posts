#!/usr/bin/env python
from models import db, User, Post
from flask import Flask
import os

"""
This file sets up the DB for first time run
"""

app = Flask(__name__)
app.app_context().push()
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///saved.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
db.create_all()
