import copy

from typing import Type, TypeVar


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

        # Need to resolve these lazily in frame of __init__
        str_annots = {}
        if annots := attrs.pop("__annotations__", None):
            temp.pop("__annotations__")
            for annot, typehint in annots.items():
                if isinstance(typehint, str):
                    if annot in temp:
                        str_annots[annot] = typehint
                    else:
                        temp[annot] = None

                    continue
                
                if annot not in temp:
                    temp[annot] = None
                elif annot in temp and isinstance(temp[annot], tuple):
                    args = temp[annot]
                    if len(args) > 1:
                        temp[annot] = typehint(*args[0], **args[1])
                    else:
                        if isinstance(args[0], dict):
                            temp[annot] = typehint(**args[0])
                        else:
                            temp[annot] = typehint(*args[0])

        orig_init = attrs.pop("__init__", None)
        def new_init(self, *uargs, **kwargs):
            if orig_init == None and len(bases) > 0:
                for base in bases:
                    # Avoid stuff like Generics
                    if issubclass(base, MemType):
                        base.__init__(self, *uargs, **kwargs)

            # "Trivial" fields
            for key, val in temp.items():
                # TODO: Copy might not be good enough. May need to inspect ast to transform this accurately
                type(self).__setattr__(self, key, copy.copy(val))

            # lazy resolution for str type hints; makes forward declarations kinda work
            for name, strannot in str_annots.items():
                args = temp[name]
                typecls = eval(strannot)
                if len(args) > 1:
                    val = typecls(*temp[0], **temp[1])
                elif len(args) == 1:
                    if isinstance(args[0], dict):
                        val = typecls(**args[0])
                    else:
                        val = typecls(*args[0])
                else:
                    val = typecls()
                type(self).__setattr__(self, name, val)

            if orig_init != None:
                orig_init(self, *uargs, **kwargs)
        attrs["__init__"] = new_init

        # Cleanup
        for attr in temp:
            attrs.pop(attr, None)
        #print(f"Fully transformed: {attrs}\n")
        return super().__new__(cls, clsname, bases, attrs)

MT = TypeVar("MT")
T = TypeVar("T")
class MemType(metaclass=MemMetaClass):
    _memview = None

    def __init__(self, offset: int) -> None:
        self.offset = offset

    # TODO: Size inference (if possible, might be quite hard with stuff like arrays)
    @property
    def typesize(self) -> int:
        raise NotImplementedError()

    def __getattribute__(self, __name: str):
        attr = super().__getattribute__(__name)
        if isinstance(attr, MemType):
            attr._memview = self._memview
            return attr
        else:
            return attr

    def read(self) -> T:
        raise NotImplementedError()

    def write(self, data: T):
        raise NotImplementedError()

    def cast(self, memtype: Type[MT] | MT) -> MT:
        return self._memview.into(memtype)
