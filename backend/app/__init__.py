import typing

# Python 3.10.0 compatibility shim for ForwardRef keyword arguments (e.g. is_class) used by modern Pydantic
_orig_fr_init = typing.ForwardRef.__init__

def _compat_fr_init(self, arg, is_argument=True, **kwargs):
    return _orig_fr_init(self, arg, is_argument=is_argument)

typing.ForwardRef.__init__ = _compat_fr_init
