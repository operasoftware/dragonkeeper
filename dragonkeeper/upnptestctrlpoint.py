import asyncore
import re
from upnpsimpledevice import SimpleUPnPDevice
from upnpsearch import UPnPSearch

re_usn = re.compile(r"uuid:(?P<uuid>[a-zA-Z0-9\-]*)(?:::)?(?P<type_>.*)")
NOTIFY = "NOTIFY"
SEARCH_RESPONSE = "HTTP/1.1"
ALIVE = "alive"
BYEBYE = "byebye"
TARGET = "urn:opera-com:device:OperaDragonfly:1"

class Device(object):
    def __init__(self, uuid, status, type_, headers):
        self.uuid = uuid
        self.status = status
        self.type = type_
        self.location = headers.get("LOCATION") or headers.get("Location")

    def __repr__(self):
        return "".join(["Dragonfly:", "\n",
                        "  uuid: ", self.uuid, "\n",
                        "  description: ", self.location, "\n",
                        "  status: ", self.status, "\n"])

    

class TestControlPoint(SimpleUPnPDevice):
    def __init__(self, ip="", http_port=0, sniff=False):
        SimpleUPnPDevice.__init__(self)
        self.search = UPnPSearch(self.process_msg)
        self.devices = {}

    def process_msg(self, method, headers):
        if method == NOTIFY or method == SEARCH_RESPONSE:
            null, status = headers.get("NTS", ":").split(":", 1)
            match = re_usn.match(headers.get("USN", ""))
            uuid = match and match.group("uuid")
            type_ = match and match.group("type_") or headers.get("ST")
            if status and uuid and type_:
                if status == ALIVE:
                    if type_ == TARGET  and not uuid in self.devices:
                        self.devices[uuid] = Device(uuid, status, type_, headers)
                        print self.devices[uuid]
                elif status == BYEBYE:
                    if uuid in self.devices:
                        device = self.devices.pop(uuid)
                        device.status = BYEBYE
                        print str(device)

if __name__ == "__main__":
    try:
        TestControlPoint()
        asyncore.loop(timeout=0.1)
    except KeyboardInterrupt:
        for fd, obj in asyncore.socket_map.items():
            obj.close()
