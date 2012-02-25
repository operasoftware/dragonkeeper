import common
import socket
import asyncore
import time
from upnpsimpledevice import SimpleUPnPDevice

M_SEARCH = common.CRLF.join(["M-SEARCH * HTTP/1.1",
                             "HOST: 239.255.255.250:1900",
                             "MAN: \"ssdp:discover\"",
                             "MX: 3",
                             "ST: %s", # ssdp:all
                             common.CRLF])


class UPnPSearch(asyncore.dispatcher):
    def __init__(self, process_msg, target="ssdp:all"):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.sendto(M_SEARCH % target, SimpleUPnPDevice.UPnP_ADDR)
        self.process_msg = process_msg
        self.expire = time.time() * 1000 + 5 * 1000

    def handle_read(self):
        msg, addr = self.recvfrom(common.BUFFERSIZE)
        parsed_headers = common.parse_headers(msg)
        if parsed_headers:
            raw, first_line, headers, msg = parsed_headers
            method, path, protocol = first_line.split(common.BLANK, 2)
            self.process_msg(method, headers)

    def writable(self):
        if time.time() * 1000 > self.expire:
            self.del_channel()
        return False