#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

from flask_socketio import Namespace, emit
from flask.views import MethodView
from flask import render_template, session, redirect, url_for
from flask_wtf import FlaskForm
from wtforms.fields import StringField, SubmitField, BooleanField, PasswordField
from wtforms.validators import DataRequired, Regexp
from flask_login import login_user, current_user
from src.user import User

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Regexp('^\w+$', message="Names can only contain alphanumeric characters")])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class VLogin(MethodView):
    def __init__(self, config, manager):
        self._manager = manager
        self._cofnig = config
        self._form = LoginForm()

    def get(self):
        if current_user.is_authenticated:
            return redirect(url_for("lobby"))
        self._form.username.data = session.get('username', '')
        return render_template("login.html", form=self._form, msg="")
    
    def post(self):
        err = ""
        if self._form.validate_on_submit():
            success, err, uid = self._manager.loginUser(
                self._form.username.data,
                self._form.password.data
            )
            if not success:
                return render_template("login.html", form=self._form, msg=err)
            login_user(self._manager.getUserObject(uid))
            return redirect(url_for("lobby"))
        return render_template("login.html", form=self._form, msg="")        
