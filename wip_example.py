

if __name__ == "__main__":
    import os
    import ctypes
    from memonster import WindowsBackend, BaseAllocator, py_to_pointer, MemoryView, MemType, MemInt64, MemPointer

    def _main():
        class TestType(MemType):
            a = MemPointer(0, MemPointer(0, MemPointer(0, MemInt64(0))))

        pid = os.getpid()
        # PROCESS_ALL_ACCESS
        handle = ctypes.windll.kernel32.OpenProcess(0xF0000 | 0x100000 | 0xFFFF, 0, pid)

        membackend = WindowsBackend(handle)
        allocator = BaseAllocator(membackend)

        x = ctypes.c_uint64(0xBE1211)
        xt = MemoryView(py_to_pointer(x), 8, membackend).into(MemInt64)
        print(hex(xt.read()))
        xt.write(50)
        print(xt.read())

        ttv = allocator.alloc0(8)
        tt = ttv.into(TestType)
        print(tt.a.cast(MemInt64).read())
        tt.a.cast(MemInt64).write(55)
        print(tt.a.cast(MemInt64).read())

        ttv2 = allocator.alloc0(8)
        tt2 = ttv2.into(TestType(0))
        print(tt2.a.cast(MemInt64).read())

        ctypes.windll.kernel32.CloseHandle(handle)

    _main()