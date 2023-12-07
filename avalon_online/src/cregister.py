#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

from flask_socketio import Namespace, emit
from flask.views import MethodView
from flask import render_template, url_for, redirect, session
from flask_wtf import FlaskForm
from wtforms.fields import StringField, SubmitField, BooleanField, PasswordField
from wtforms.validators import DataRequired, Regexp, Length

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Regexp('^\w+$', message="Names can only contain alphanumeric characters"), Length(min=3, max=16)])
    password = PasswordField('Password', validators=[DataRequired()])
    consent = BooleanField('By checking this box, you agree that the above terms and agree to participate in this research study.', validators=[DataRequired()])
    submit = SubmitField('Register')

class VRegister(MethodView):
    def __init__(self, config, manager):
        self._manager = manager
        self._cofnig = config
        self._form = RegisterForm()

    def get(self):
        self._form.username.data = session.get("username", "")
        return render_template("register.html", form=self._form, err="")
    
    def post(self):
        error = ""
        if self._form.validate_on_submit():
            success, error = self._manager.registerUser(
                self._form.username.data,
                self._form.password.data,
                self._form.consent.data,
            )
            if success:
                return redirect(url_for("login"))            
        return render_template("register.html", form=self._form, err=error)
