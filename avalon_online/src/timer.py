#   Copyright 2023 by Simon Stepputtis, Carnegie Mellon University
#   All rights reserved.
#   This file is part of the Avalon-NLU repository,
#   and is released under the "MIT License Agreement". Please see the LICENSE
#   file that should have been included as part of this package.

from threading import Timer
import time

class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer     = None
        self.interval   = interval
        self.function   = function
        self.args       = args
        self.kwargs     = kwargs
        self.is_running = False
        self.started_at = 0

    def _run(self):
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)
    
    def _runOnce(self):
        self.is_running = False
        self.function(*self.args, **self.kwargs)

    def start(self):
        if self.interval <= 0:
            return
        if not self.is_running:
            self._timer = Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True
            self.started_at = time.time()
            

    def startOnce(self):
        if self.interval <= 0:
            return
        if not self.is_running:
            self._timer = Timer(self.interval, self._runOnce)
            self._timer.start()
            self.is_running = True
            self.started_at = time.time()

    def stop(self):
        if self._timer:
            self._timer.cancel()
        self.is_running = False

    def getRemaining(self):
        if not self.is_running:
            return 0
        return self.interval - (time.time() - self.started_at)
