"""Linux-only offline TShark launcher. Fail closed if syscall isolation is unavailable."""
import ctypes
import ctypes.util
import errno
import os
import resource
import platform
import sys

FIELDS = ('frame.number', 'frame.time_epoch', 'frame.len', 'ip.src', 'ipv6.src',
          'ip.dst', 'ipv6.dst', 'tcp.srcport', 'udp.srcport', 'tcp.dstport', 'udp.dstport',
          '_ws.col.Protocol', 'dns.qry.name', 'tls.handshake.extensions_server_name', 'http.host')


def restrict_filesystem(libc, capture):
    # Landlock ABI 3 covers rename/link and truncation, even for non-root workers.
    if platform.machine() not in ('x86_64', 'aarch64'):
        raise RuntimeError('Unsupported PCAP isolation architecture')
    libc.syscall.restype = ctypes.c_long
    if libc.syscall(ctypes.c_long(444), None, ctypes.c_size_t(0), ctypes.c_uint(1)) < 3:
        raise RuntimeError('PCAP filesystem isolation requires Landlock ABI 3 or newer')
    class Ruleset(ctypes.Structure):
        _fields_ = [('handled_access_fs', ctypes.c_uint64)]
    class PathRule(ctypes.Structure):
        _pack_ = 1
        _fields_ = [('allowed_access', ctypes.c_uint64), ('parent_fd', ctypes.c_int)]
    attributes = Ruleset((1 << 15) - 1)
    ruleset = libc.syscall(ctypes.c_long(444), ctypes.byref(attributes), ctypes.sizeof(attributes), 0)
    if ruleset < 0:
        raise RuntimeError('Unable to initialize PCAP filesystem isolation')
    try:
        paths = [(p, 1 | 4 | 8) for p in ('/usr', '/lib', '/lib64') if os.path.exists(p)]
        paths += [(p, 4) for p in (capture, '/etc/ld.so.cache', '/etc/passwd', '/etc/group',
                                  '/etc/localtime', '/dev/null', '/dev/urandom') if os.path.exists(p)]
        if os.path.isdir('/etc/wireshark'):
            paths.append(('/etc/wireshark', 4 | 8))
        for path, access in paths:
            descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = PathRule(access, descriptor)
                if libc.syscall(ctypes.c_long(445), ruleset, 1, ctypes.byref(rule), 0) != 0:
                    raise RuntimeError('Unable to restrict PCAP filesystem paths')
            finally:
                os.close(descriptor)
        if libc.syscall(ctypes.c_long(446), ruleset, 0) != 0:
            raise RuntimeError('Unable to load PCAP filesystem isolation')
    finally:
        os.close(ruleset)


def main():
    if sys.platform != 'linux':
        raise RuntimeError('Offline PCAP isolation requires Linux')
    path = sys.argv[1]
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024**2, 512 * 1024**2))
    resource.setrlimit(resource.RLIMIT_CPU, (60, 60))
    resource.setrlimit(resource.RLIMIT_FSIZE, (16 * 1024**2, 16 * 1024**2))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(38, 1, 0, 0, 0) != 0:  # PR_SET_NO_NEW_PRIVS
        raise RuntimeError('Unable to restrict PCAP process privileges')
    sec = ctypes.CDLL(ctypes.util.find_library('seccomp') or 'libseccomp.so.2', use_errno=True)
    sec.seccomp_init.argtypes = [ctypes.c_uint32]
    sec.seccomp_init.restype = ctypes.c_void_p
    sec.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    sec.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    sec.seccomp_load.argtypes = [ctypes.c_void_p]
    sec.seccomp_release.argtypes = [ctypes.c_void_p]
    ctx = sec.seccomp_init(0x7fff0000)  # SCMP_ACT_ALLOW
    if not ctx:
        raise RuntimeError('Unable to initialize PCAP isolation')
    try:
        for name in ('socket', 'socketpair', 'socketcall', 'connect', 'ptrace', 'process_vm_readv',
                     'process_vm_writev', 'mount', 'umount2', 'bpf', 'keyctl', 'perf_event_open'):
            number = sec.seccomp_syscall_resolve_name(name.encode())
            if number >= 0 and sec.seccomp_rule_add(ctx, 0x00050000 | errno.EPERM, number, 0) != 0:
                raise RuntimeError('Unable to restrict PCAP syscall')
        if sec.seccomp_load(ctx) != 0:
            raise RuntimeError('Unable to load PCAP isolation')
    finally:
        sec.seccomp_release(ctx)
    if os.getuid() == 0:
        os.setgroups([])
        os.setgid(65534)
        os.setuid(65534)
    restrict_filesystem(libc, path)
    argv = ['/usr/bin/tshark', '-n', '-r', path, '-c', '100000', '-T', 'fields',
            '-E', 'separator=/t', '-E', 'occurrence=f', '-E', 'quote=n']
    for field in FIELDS:
        argv += ['-e', field]
    os.execve(argv[0], argv, {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C.UTF-8'})


if __name__ == '__main__':
    main()
