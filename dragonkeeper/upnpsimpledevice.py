import socket
import asyncore
import time
import random
import common

def get_uuid():
    hex_digit = "0123456789abcdefABCDEF"
    len_ = len(hex_digit) - 1
    ret = []
    for i in [8, 4, 4, 4, 12]:
       ret.append("".join([hex_digit[random.randint(0, len_)] for x in range(i)]))
    return "-".join(ret)

NOTIFY_ALIVE = common.CRLF.join(["NOTIFY * HTTP/1.1",
                                 "HOST: 239.255.255.250:1900",
                                 "CACHE-CONTROL: max-age=1800",
                                 "LOCATION: http://%s:%s/upnp-description",
                                 "SERVER: dragonkeeper",
                                 "NT: upnp:rootdevice",
                                 "NT2: urn:opera-com:device:OperaDragonfly:1",
                                 "NTS: ssdp:alive",
                                 "USN: uuid:%s::urn:opera-com:device:OperaDragonfly:1",
                                 common.CRLF])

NOTIFY_BYBY = common.CRLF.join(["NOTIFY * HTTP/1.1",
                                "HOST: 239.255.255.250:1900",
                                "NT: upnp:rootdevice",
                                "NTS: ssdp:byebye",
                                "USN: uuid:%s::urn:opera-com:device:OperaDragonfly:1",
                                common.CRLF])

SEARCH_RESPONSE = common.CRLF.join(["HTTP/1.1 200 OK",
                                    "CACHE-CONTROL: max-age=1800",
                                    "EXT:",
                                    "LOCATION: http://%s:%s/upnp-description",
                                    "SERVER: dragonkeeper",
                                    "ST: urn:opera-com:device:OperaDragonfly:1",
                                    "USN: uuid:%s::urn:opera-com:device:OperaDragonfly:1",
                                    common.CRLF])

DEVICE_DESCRIPTION = """<?xml version="1.0" encoding="UTF-8"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
    <specVersion>
        <major>1</major>
        <minor>0</minor>
    </specVersion>
    <device>
        <deviceType>urn:opera-com:device:OperaDragonfly:1</deviceType>
        <friendlyName>dragonkeeper</friendlyName>
        <manufacturer>Opera Software ASA</manufacturer>
        <manufacturerURL>http://www.opera.com/</manufacturerURL>
        <payload>http://%s:%s</payload>
        <deviceicon>http://%s:%s/favicon.ico</deviceicon>
    <serviceList/>
    </device>
</root>
"""

class SimpleUPnPDevice(asyncore.dispatcher):
    MCAST_GRP = "239.255.255.250"
    MCAST_PORT = 1900
    UPnP_ADDR = ("239.255.255.250", 1900)
    SEARCH_TARGETS = ["urn:opera-com:device:OperaDragonfly:1"]
                      # "ssdp:all", "upnp:rootdevice",

    def __init__(self, ip="", http_port=0, sniff=False):
        asyncore.dispatcher.__init__(self)
        self.create_socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.bind(("0.0.0.0", self.MCAST_PORT))
        mreq = socket.inet_aton(self.MCAST_GRP) + socket.inet_aton("0.0.0.0")
        self.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        self.ip = ip
        self.http_port = http_port
        self.send_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.uuid = get_uuid()
        self.msg_queue = []
        self.msg_alive = NOTIFY_ALIVE % (self.ip, self.http_port, self.uuid)
        self.msg_byby = NOTIFY_BYBY % self.uuid
        self.search_resp = SEARCH_RESPONSE % (self.ip, self.http_port, self.uuid)
        self.sniff = sniff
        self.is_alive = False

    def notify_alive(self):
        self.is_alive = True
        t = time.time() * 1000
        for i in range(1, 4):
            self.queue_msg(t + i * 100, self.msg_alive, self.UPnP_ADDR)

    def notify_byby(self, cb=None):
        self.is_alive = False
        t = time.time() * 1000
        for i in range(1, 4):
            self.queue_msg(t + i * 100, self.msg_byby, self.UPnP_ADDR)

    def queue_msg(self, delay, msg, addr):
        self.msg_queue.append((delay, msg, addr))
        
    def process_msg_queue(self):
        cur = 0
        t = time.time() * 1000
        TIME = 0
        MSG = 1
        ADDR = 2
        while cur < len(self.msg_queue):
            if t > self.msg_queue[cur][TIME]:
                msg = self.msg_queue.pop(cur)
                self.send_socket.sendto(msg[MSG], msg[ADDR])
            else:
                cur += 1

    def handle_read(self):
        msg, addr = self.recvfrom(common.BUFFERSIZE)
        if self.sniff:
            print addr, '\n', msg
        else:
            parsed_headers = common.parse_headers(msg)
            if parsed_headers:
                raw, first_line, headers, msg = parsed_headers
                method, path, protocol = first_line.split(common.BLANK, 2)
                st = headers.get("ST")
                if self.is_alive and method == "M-SEARCH" and st in self.SEARCH_TARGETS:
                    t = time.time() * 1000
                    mx = int(headers.get("MX", 3)) * 1000
                    self.queue_msg(random.randint(100, mx), self.search_resp, addr)
                else:
                    self.process_msg(method, headers)

    def writable(self):
        if len(self.msg_queue):
            self.process_msg_queue()
        return False

    def get_description(self, headers):
        content = DEVICE_DESCRIPTION % (self.ip, self.http_port, self.ip, self.http_port)
        args = (common.get_timestamp(), "", "text/xml", len(content), content)
        return common.RESPONSE_OK_CONTENT % args

    def handle_close(self):
        self.close()

    def process_msg(self, method, headers):
        pass

if __name__ == "__main__":
    try:
        SimpleUPnPDevice(sniff=True)
        asyncore.loop(timeout=0.1)
    except KeyboardInterrupt:
        for fd, obj in asyncore.socket_map.items():
            obj.close()
