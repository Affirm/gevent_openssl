"""gevent_openssl.SSL - gevent compatibility with OpenSSL.SSL.
"""

import sys
from OpenSSL.SSL import *
from OpenSSL.SSL import WantReadError
from OpenSSL.SSL import WantWriteError
from OpenSSL.SSL import WantX509LookupError
from OpenSSL.SSL import ZeroReturnError
from OpenSSL.SSL import SysCallError
from OpenSSL.SSL import Connection as __Connection__
try:
    from gevent.socket import wait_read
    from gevent.socket import wait_write
    from gevent.socket import wait_readwrite
except ImportError:
    import select
    def wait_read(fd, timeout):
        return select.select([fd], [], [fd], timeout)
    def wait_write(fd, timeout):
        return select.select([fd], [fd], [fd], timeout)
    def wait_readwrite(fd, timeout):
        return select.select([fd], [fd], [fd], timeout)


class Connection(object):

    def __init__(self, context, sock):
        self._context = context
        self._sock = sock
        self._connection = OpenSSL.SSL.Connection(context, sock)
        self._makefile_refs = 0

    def __getattr__(self, attr):
        if attr not in ('_context', '_sock', '_connection', '_makefile_refs'):
            return getattr(self._connection, attr)

    def __wait_sock_io(self, sock, io_func, *args, **kwargs):
        timeout = self._sock.gettimeout() or 0.1
        fd = self._sock.fileno()
        while True:
            try:
                return io_func(*args, **kwargs)
            except (OpenSSL.SSL.WantReadError, OpenSSL.SSL.WantX509LookupError):
                sys.exc_clear()
                _, _, errors = select.select([fd], [], [fd], timeout)
                if errors:
                    break
            except OpenSSL.SSL.WantWriteError:
                sys.exc_clear()
                _, _, errors = select.select([], [fd], [fd], timeout)
                if errors:
                    break

    def accept(self):
        sock, addr = self._sock.accept()
        client = OpenSSL.SSL.Connection(sock._context, sock)
        return client, addr

    def do_handshake(self):
        return self.__wait_sock_io(self._sock, self._connection.do_handshake)

    def connect(self, *args, **kwargs):
        return self.__wait_sock_io(self._sock, self._connection.connect, *args, **kwargs)

    def send(self, data, flags=0):
        try:
            return self.__wait_sock_io(self._sock, self._connection.send, data, flags)
        except OpenSSL.SSL.SysCallError as e:
            if e[0] == -1 and not data:
                # errors when writing empty strings are expected and can be ignored
                return 0
            raise

    def recv(self, bufsiz, flags=0):
        pending = self._connection.pending()
        if pending:
            return self._connection.recv(min(pending, bufsiz))
        try:
            return self.__wait_sock_io(self._sock, self._connection.recv, bufsiz, flags)
        except OpenSSL.SSL.ZeroReturnError:
            return ''

    def read(self, bufsiz, flags=0):
        return self.recv(bufsiz, flags)

    def write(self, buf, flags=0):
        return self.sendall(buf, flags)

    def close(self):
        if self._makefile_refs < 1:
            self._connection = None
            if self._sock:
                socket.socket.close(self._sock)
        else:
            self._makefile_refs -= 1

    def makefile(self, mode='r', bufsize=-1):
        self._makefile_refs += 1
        return socket._fileobject(self, mode, bufsize, close=True)
