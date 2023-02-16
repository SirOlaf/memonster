

if __name__ == "__main__":
    import os
    import ctypes
    from memonster import WindowsBackend, BaseAllocator, py_to_pointer, MemoryView, MemType, MemInt64, MemPointer, MemCString

    def _main():
        class TestType(MemType):
            cool_cstring = MemCString(0)
            cool_int = MemInt64(20)

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

        ttv = allocator.alloc0(24)
        tt = ttv.into(TestType)
        tt.cool_cstring.write("test")
        tt.cool_int.write(999)
        print(tt.cool_cstring.read())
        print(tt.cool_int.read())


        ctypes.windll.kernel32.CloseHandle(handle)

    _main()