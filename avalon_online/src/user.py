#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

from flask_login import UserMixin

class User(UserMixin):
    def __init__(self, values):
        self._parse(values)
    
    def _parse(self, values):
        self.name = values[1]
        self.id = values[0]
        self.active = values[3]
        self.gamesplayed = values[4]
        self.victories_good = values[5]
        self.victories_evil = values[6]
        self.game = values[7]
        self.session_token = values[8]

    @property
    def is_active(self):
        return self.active
    
    def get_id(self):
        return str(self.session_token)
