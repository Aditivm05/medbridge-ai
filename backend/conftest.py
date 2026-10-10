import os
import typing

os.environ["TESTING"] = "1"
os.environ["GEMINI_API_KEY"] = ""

# Python 3.10.0 ForwardRef compatibility shim for test runner
_orig_fr_init = typing.ForwardRef.__init__

def _compat_fr_init(self, arg, is_argument=True, **kwargs):
    return _orig_fr_init(self, arg, is_argument=is_argument)

typing.ForwardRef.__init__ = _compat_fr_init
