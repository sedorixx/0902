"""
This type stub file was generated by pyright.
"""

import typing
import _jpype
from . import _jcustomizer

__all__ = ['JString']
class JString(_jpype._JObject, internal=True):
    """ Base class for ``java.lang.String`` objects

    When called as a function, this class will produce a ``java.lang.String``
    object.  It can be used to test if an object is a Java string
    using ``isinstance(obj, JString)``.

    """
    def __new__(cls, *args, **kwargs):
        ...
    


@_jcustomizer.JImplementationFor("java.lang.String")
class _JStringProto:
    def __add__(self, other: str) -> str:
        ...
    
    def __len__(self) -> int:
        ...
    
    def __getitem__(self, i: typing.Union[slice, int]): # -> str:
        ...
    
    def __contains__(self, other: str) -> bool:
        ...
    
    def __hash__(self) -> int:
        ...
    
    def __repr__(self): # -> str:
        ...
    


