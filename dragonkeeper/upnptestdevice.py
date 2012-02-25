import sys
import os
import socket
import common
import asyncore
from httpconnection import HTTPConnection
from simpleserver import SimpleServer
from upnpsimpledevice import SimpleUPnPDevice

class Obj(object):
        pass

if __name__ == "__main__":
    options = Obj()
    try:
        ip = socket.gethostbyname(socket.gethostname())
        options.http_get_handlers = {}
        options.host = "0.0.0.0"
        options.server_port = 8000
        options.cgi_enabled = False
        server = SimpleServer(options.host, options.server_port, HTTPConnection, options)
        upnp_device = SimpleUPnPDevice(ip, options.server_port)
        upnp_device.notify_alive()
        options.http_get_handlers["upnp_description"] = upnp_device.get_description
        options.upnp_device = upnp_device
        asyncore.loop(timeout=0.1)
    except KeyboardInterrupt:
        options.upnp_device.notify_byby()
        asyncore.loop(timeout=0.1, count=6)
        for fd, obj in asyncore.socket_map.items():
            obj.close()
        sys.exit()
