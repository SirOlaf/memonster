import copy
import struct

from typing import TypeVar, Generic, Type

from .metamem import MemType


T = TypeVar("T")
MT = TypeVar("MT") # TODO: Can this be restricted to just MemType?


type_dict = {
    # int types
    "int8": struct.Struct("<b"),
    "uint8": struct.Struct("<B"),
    "int16": struct.Struct("<h"),
    "uint16": struct.Struct("<H"),
    "int32": struct.Struct("<i"),
    "uint32": struct.Struct("<I"),
    "int64": struct.Struct("<q"),
    "uint64": struct.Struct("<Q"),

    # float types
    "float32": struct.Struct("<f"),
    "float64": struct.Struct("<d"),

    # other types
    "bool": struct.Struct("?"),
    "char": struct.Struct("<c"),
}


class MemPrimitive(MemType, Generic[T]):
    typename: str = None
    generic_type = None

    def read(self) -> Type[T]:
        t = type_dict[self.typename]
        vals = t.unpack(self._memview.read_bytes(t.size, self.offset))
        if len(vals) == 1:
            return vals[0]
        else:
            return vals

    def write(self, data: T):
        t = type_dict[self.typename]
        self._memview.write_bytes(t.pack(data), self.offset)


class MemInt8(MemPrimitive[int]):
    typename = "int8"

class MemUInt8(MemPrimitive[int]):
    typename = "uint8"

class MemInt16(MemPrimitive[int]):
    typename = "int16"

class MemUInt16(MemPrimitive[int]):
    typename = "uint16"

class MemInt32(MemPrimitive[int]):
    typename = "int32"

class MemUInt32(MemPrimitive[int]):
    typename = "uint32"

class MemInt64(MemPrimitive[int]):
    typename = "int64"

class MemUInt64(MemPrimitive[int]):
    typename = "uint64"

class MemFloat32(MemPrimitive[float]):
    typename = "float32"

class MemFloat64(MemPrimitive[float]):
    typename = "float64"

class MemBool(MemPrimitive[bool]):
    typename = "bool"

class MemChar(MemPrimitive[str]):
    typename = "char"

class MemPointer(MemType, Generic[MT]):
    def __init__(self, offset: int, dummy: MT) -> None:
        super().__init__(offset)
        self._dummy = dummy
    
    @property
    def typesize(self) -> int:
        return 8

    def read(self) -> MT:
        res = copy.copy(self._dummy)
        res._memview = copy.copy(self._memview)
        res._memview.size = res.typesize
        # TODO: Generic pointer primitive so it works on multiple process bit-types
        res._memview.address = self.cast(MemUInt64).read()
        return res

    def swap(self, ptr: "MemPointer[MT]"):
        addr = self.cast(MemUInt64)
        res = addr.read()
        addr.write(ptr._memview.address)
        return res
