import sys
import inspect
import copy

from typing import TypeVar, Type

import ctypes

if sys.platform == "win32":
    from ctypes import wintypes
    _kernel32 = ctypes.windll.kernel32

    _ReadProcessMemory = _kernel32.ReadProcessMemory
    _ReadProcessMemory.argtypes = (
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.LPVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t)
    )
    _ReadProcessMemory.restype = wintypes.BOOL

    _WriteProcessMemory = _kernel32.WriteProcessMemory
    _WriteProcessMemory.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.LPCVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t)
    )
    _WriteProcessMemory.restype = wintypes.BOOL

    _VirtualAllocEx = _kernel32.VirtualAllocEx
    _VirtualAllocEx.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.DWORD,
        wintypes.DWORD
    )
    _VirtualAllocEx.restype = wintypes.LPVOID

    _VirtualFreeEx = _kernel32.VirtualFreeEx
    _VirtualFreeEx.argtypes = (
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.DWORD,
    )
    _VirtualFreeEx.restype = wintypes.BOOL
#else:
#    raise RuntimeError("Memonster is currently unsupported on this platform!")


class MemoryBackend:
    def read_bytes(self, count: int, address: int) -> bytes: 
        raise NotImplementedError()

    def write_bytes(self, data: bytes, address: int):
        raise NotImplementedError()

    def alloc(self, size: int) -> "MemoryView":
        raise NotImplementedError()

    def alloc0(self, size: int) -> "MemoryView":
        result = self.alloc(size)
        result.write_bytes("\x00" * size)
        return result

    def free(self, ptr: "MemoryView"):
        raise NotImplementedError()

class WindowsBackend(MemoryBackend):
    def __init__(self, handle: wintypes.HANDLE) -> None:
        super().__init__()
        self._handle = handle

    def read_bytes(self, count: int, address: int) -> bytes:
        buff = ctypes.create_string_buffer(count)
        if 0 ==_ReadProcessMemory(self._handle, address, buff, count, ctypes.c_size_t(0)):
            raise AllocatorError(f"Failed to read bytes from address {address}")
        return buff.raw

    def write_bytes(self, data: bytes, address: int) -> None:
        if 0 == _WriteProcessMemory(self._handle, address, data, len(data), ctypes.c_size_t(0)):
            raise AllocatorError(f"Failed to write bytes to address {address}")

    def alloc(self, size: int) -> "MemoryView":
        # could use large pages for big allocs
        if lpvoid := _VirtualAllocEx(
            self._handle,
            wintypes.LPVOID(0),
            size,
            0x1000 | 0x2000, # MEM_COMMIT and MEM_RESERVE
            0x40, # PAGE_EXECUTE_READWRITE
            ):
            ptr = MemoryView(
                int(lpvoid),
                self
            )
            return ptr
        else:
            raise AllocatorError("VirtualAllocEx failed")

    def free(self, ptr: "MemoryView"):
        assert isinstance(ptr.backend, MemoryView)
        _VirtualFreeEx(
            self.handle,
            ptr.address,
            0,
            0x8000 # MEM_RELEASE
        )


MMT = TypeVar("MMT")
class MemoryView:
    __slots__ = "address", "backend"
    def __init__(self, address: int, backend: MemoryBackend) -> None:
        self.address = address
        self.backend = backend

    def read_bytes(self, count: int, offset: int = 0) -> bytes:
        return self.backend.read_bytes(count, self.address + offset)

    def write_bytes(self, data: bytes, offset: int = 0) -> None:
        self.backend.write_bytes(data, self.address + offset)

    # Why the hell is X | Y evaluated backwards in my extension
    def into(self, memtype: MMT | Type[MMT], offset: int = 0) -> MMT:
        if inspect.isclass(memtype):
            res = memtype(offset)
        else:
            res = copy.copy(memtype)
        res._memview = self
        res.offset = offset
        return res


class AllocatorError(RuntimeError):
    pass

class BaseAllocator:
    def __init__(self, backend: MemoryBackend) -> None:
        ## Not thread safe!
        # _owned_pointers remains sorted so it's reasonable efficient
        # Most likely want to use a tree structure instead though, this may be too slow
        self._owned_pointers: list[MemoryView] = []
        self.backend = backend

    def _addptr(self, ptr: MemoryView) -> None:
        assert isinstance(ptr, MemoryView)
        if len(self._owned_pointers) == 0:
            self._owned_pointers = [ptr]
            return
        i = 0
        addr = ptr.address
        while i < len(self._owned_pointers):
            cur = self._owned_pointers[i]
            if addr < cur.address:
                # insert here
                self._owned_pointers.insert(i, ptr)
                break
            elif addr > cur.address:
                if i + 1 >= len(self._owned_pointers):
                    # insert at end
                    self._owned_pointers.append(ptr)
                    break
                # continue on
                i += 1
            else:
                # should not happen, but if it does we will escape quickly
                break

    def _removeptr(self, ptr: MemoryView) -> None:
        assert isinstance(ptr.backend, MemoryView)
        i = 0
        addr = ptr.address
        while i < len(self._owned_pointers):
            if addr == self._owned_pointers[i].address:
                self._owned_pointers.pop(i)
                break

    def alloc(self, size: int) -> MemoryView:
        return self.backend.alloc(size)

    def alloc0(self, size: int) -> MemoryView:
        return self.backend.alloc0(size)

    def free(self, ptr: MemoryView) -> None:
        self.backend.free(ptr)
