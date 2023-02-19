import copy

from typing import Type, TypeVar, Generic


class MemMetaClass(type):
    def __new__(cls, clsname, bases, attrs):
        temp = dict(attrs)
        # TODO: Maybe filter all builtin things?
        temp.pop("__module__", None)
        temp.pop("__qualname__", None)
        temp.pop("__classcell__", None)
        temp.pop("__orig_bases__", None)
        temp = {k: v for k, v in temp.items() if not callable(v) and not isinstance(v, property)}

        #print("UNTRANSFORMED")
        #print(attrs)

        orig_init = attrs.pop("__init__", None)
        def new_init(self, *uargs, **kwargs):
            if orig_init == None and len(bases) > 0:
                for base in bases:
                    # Avoid stuff like Generics
                    if issubclass(base, MemType):
                        # TODO: Rethink this
                        base.__init__(self, *uargs, **kwargs)

            # "Trivial" fields
            for key, val in temp.items():
                # TODO: Copy might not be good enough. May need to inspect ast to transform this accurately
                type(self).__setattr__(self, key, copy.copy(val))

            if orig_init != None:
                orig_init(self, *uargs, **kwargs)
        attrs["__init__"] = new_init

        # Cleanup
        for attr in temp:
            attrs.pop(attr, None)
        #print(f"Fully transformed: {attrs}\n")
        return super().__new__(cls, clsname, bases, attrs)

T = TypeVar("T")
# Used to let MemType resolve types lazily for stuff like recursive types
class LazyType(Generic[T]):
    def __init__(self, ttype: Type[T]) -> None:
        self.ttype = ttype
        self.args = None
        self.kwds = None

    def __call__(self, *args, **kwds) -> T:
        self.args = args
        self.kwds = kwds
        return self

MT = TypeVar("MT", bound="MemType")
class MemType(metaclass=MemMetaClass):
    _memview = None

    def __init__(self, offset: int) -> None:
        self.offset = offset

    # TODO: Add back a way to restrict the view size

    def __getattribute__(self, __name: str):
        attr = super().__getattribute__(__name)
        if isinstance(attr, MemType):
            attr._memview = self._memview
            return attr
        elif isinstance(attr, LazyType):
            inner = attr(*attr.args, **attr.kwds)
            # It is resolved from here on, so replace the one we store
            super().__setattr__(__name, inner)
            return self.__getattribute__(__name)
        else:
            return attr
    # TODO: Is a corresponding __setattr__ needed?

    def read(self) -> T:
        raise NotImplementedError()

    def write(self, data: T):
        raise NotImplementedError()

    def cast(self, memtype: Type[MT] | MT) -> MT:
        return self._memview.into(memtype, self.offset)

    def cast_offset(self, memtype: Type[MT] | MT, offset) -> MT:
        return self._memview.into(memtype, self.offset + offset)

    def read_bytes(self, count: int) -> bytes:
        return self._memview.read_bytes(count, self.offset)

    def write_bytes(self, data: bytes):
        self._memview.write_bytes(data, self.offset)
