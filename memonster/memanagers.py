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
        assert isinstance(ptr._backend, MemoryView)
        _VirtualFreeEx(
            self.handle,
            ptr.address,
            0,
            0x8000 # MEM_RELEASE
        )


MMT = TypeVar("MMT")
class MemoryView:
    def __init__(self, address: int, backend: MemoryBackend) -> None:
        self._address = address
        self._backend = backend

    @property
    def address(self) -> int:
        return self._address

    def read_bytes(self, count: int, offset: int = 0) -> bytes:
        return self._backend.read_bytes(count, self.address + offset)

    def write_bytes(self, data: bytes, offset: int = 0) -> None:
        self._backend.write_bytes(data, self.address + offset)

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
        # (view, size)
        self._owned_pointers: list[tuple[MemoryView, int]] = []
        self._backend = backend

    def _addptr(self, ptr: MemoryView, size: int) -> None:
        assert isinstance(ptr, MemoryView)
        if len(self._owned_pointers) == 0:
            self._owned_pointers = [(ptr, size)]
            return
        i = 0
        addr = ptr.address
        while i < len(self._owned_pointers):
            cur = self._owned_pointers[i]
            if addr < cur[0].address:
                # insert here
                self._owned_pointers.insert(i, (ptr, size))
                break
            elif addr > cur[0].address:
                if i + 1 >= len(self._owned_pointers):
                    # insert at end
                    self._owned_pointers.append((ptr, size))
                    break
                # continue on
                i += 1
            else:
                # should not happen, but if it does we will escape quickly
                raise AllocatorError("Could not store a pointer in _owned_pointers")

    def _removeptr(self, ptr: MemoryView) -> None:
        assert isinstance(ptr._backend, MemoryView)
        i = 0
        addr = ptr.address
        while i < len(self._owned_pointers):
            if addr == self._owned_pointers[i][0].address:
                self._owned_pointers.pop(i)
                break

    def alloc(self, size: int) -> MemoryView:
        res = self._backend.alloc(size)
        self._addptr(res, size)
        return res

    def alloc0(self, size: int) -> MemoryView:
        return self._backend.alloc0(size)

    def free(self, ptr: MemoryView) -> None:
        self._removeptr(ptr)
        self._backend.free(ptr)

# TODO: Maybe add support for multiple caves
class CaveAllocator(BaseAllocator):
    def __init__(self, backend: MemoryBackend, start_addr: int, size: int) -> None:
        ## Not thread safe and can fragment badly
        super().__init__(backend)
        self._start_addr = start_addr
        self._size = size

    @property
    def _end_addr(self):
        return self._start_addr + self._size

    def _find_space(self, size: int):
        # Returns the smallest region that can fit size bytes to reduce fragmentation somewhat

        assert size <= self._size
        # Don't need any extra checks in this case
        if len(self._owned_pointers) == 0:
            return self._start_addr
        # Simple case, write by hand
        elif len(self._owned_pointers) == 1:
            # [start]++++++[ptr0]----[end]
            region_a = self._owned_pointers[0][0].address - self._start_addr
            b_start = self._owned_pointers[0][0].address + self._owned_pointers[0][1]
            # [start]------[ptr0]++++[end]
            region_b = self._end_addr - (b_start)

            # Otherwise no space
            if region_a >= size or region_b >= size:
                if region_a >= size and region_b < size:
                    return self._start_addr                
                elif region_b >= size and region_a < size:
                    return b_start

                # both are big enough, use smaller one
                # a is smaller
                elif region_a < region_b:
                    return self._start_addr 
                # b must be smaller and still big enough
                else:
                    return b_start
        # Need to scan all pointers and find smallest gap
        else:
            smallest = self._size + 1
            smallest_addr = -1

            # first and last are special, do those by hand
            a = self._owned_pointers[0]
            b = self._owned_pointers[-1]
            s = a[0].address - self._start_addr
            if s >= size and s < smallest:
                smallest = s
                smallest_addr = self._start_addr
            s = self._end_addr - (b[0].address + b[1])
            if s >= size and s < smallest:
                smallest = s
                smallest_addr = b[0].address + b[1]

            # all the other pointers
            # leave space for last because we wanna have i and i+1
            for i in range(len(self._owned_pointers) - 1):
                a = self._owned_pointers[i]
                b = self._owned_pointers[i+1]
                s = b[0].address - (a[0].address + a[1])
                if s >= size and s < smallest:
                    smallest = s
                    smallest_addr = a[0].address + a[1]

            # We didn't find a gap otherwise so fall through
            if smallest <= self._size:
                return smallest_addr
        raise AllocatorError(f"Cave does not have a region big enough for {size} bytes")

    def alloc(self, size: int) -> MemoryView:
        addr = self._find_space(size)
        self._addptr(addr, size)
        return MemoryView(addr, self._backend)

    def free(self, ptr: MemoryView) -> None:
        self._removeptr(ptr)

