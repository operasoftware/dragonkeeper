# Copyright (c) 2008, Opera Software ASA
# license see LICENSE.

import socket
import asyncore
"""
accept
bind
close
connect
connect_ex
dup
family
fileno
getpeername
getsockname
getsockopt
gettimeout
listen
makefile
proto
recv
recv_into
recvfrom
recvfrom_into
send
sendall
sendto
setblocking
setsockopt
settimeout
shutdown
type
"""


class SimpleServer(asyncore.dispatcher):

    def __init__(self, host, port, connection_class, context):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bind((host, port))
        self.listen(5)
        self.connection_class = connection_class
        self.context = context

    def handle_accept(self):
        newSocket, address = self.accept()
        self.connection_class(newSocket, address, self.context)
