

if __name__ == "__main__":
    import os
    import ctypes
    from enum import Enum
    from memonster import WindowsBackend, BaseAllocator, py_to_pointer, MemoryView, MemType, MemInt32, MemInt64, MemPointer, MemCString, MemEnum, LazyType

    def _main():
        class TestEnum(Enum):
            Yes = 0
            No = 1

        class TestType(MemType):
            def __init__(self, offset: int):
                super().__init__(offset)
                self.me = MemPointer(28, LazyType(TestType)(0))

            cool_cstring = MemCString(0)
            cool_int = MemInt32(20)
            cool_enum = MemEnum(24, TestEnum)

        pid = os.getpid()
        # PROCESS_ALL_ACCESS
        handle = ctypes.windll.kernel32.OpenProcess(0xF0000 | 0x100000 | 0xFFFF, 0, pid)

        membackend = WindowsBackend(handle)
        allocator = BaseAllocator(membackend)

        x = ctypes.c_uint64(0xBE1211)
        xt = MemoryView(py_to_pointer(x), membackend).into(MemInt64)
        print(hex(xt.read()))
        xt.write(50)
        print(xt.read())

        ttv = allocator.alloc0(36)
        tt = ttv.into(TestType)
        tt.cool_cstring.write("test")
        tt.cool_int.write(999)
        tt.cool_enum.write(TestEnum.No)
        print(tt.cool_cstring.read())
        print(tt.cool_int.read())
        print(tt.cool_enum.read())
        print(tt.cool_int.cast_offset(4, MemEnum(0, TestEnum)).read())

        ctypes.windll.kernel32.CloseHandle(handle)

    _main()