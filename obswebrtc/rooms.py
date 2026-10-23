"""Camera slot signaling: one sender and any number of viewers per cam slot.

The server only routes messages; WebRTC media flows directly between peers.

Client -> server:
  {"type": "join", "role": "sender" | "viewer", "cam": N}
  {"type": "leave"}
  {"type": "offer" | "answer" | "candidate", "to": peer_id, ...}

Server -> client:
  {"type": "joined", "id", "role", "cam", "senderPresent", "bufferMs"}
  {"type": "config", "bufferMs"}                     to viewers when the buffer changes
  {"type": "viewer-joined" | "viewer-left", "id"}    to the sender
  {"type": "sender-left", "from"}                    to viewers
  {"type": "replaced"}                               to a sender bumped by a newer one
  {"type": "offer" | "answer" | "candidate", "from", ...}
  {"type": "error", "error"}
"""

import itertools

from .log import get_logger

log = get_logger("rooms")

ROLES = ("sender", "viewer")
RELAY_TYPES = ("offer", "answer", "candidate")


class Peer:
    def __init__(self, peer_id, ws):
        self.id = peer_id
        self.ws = ws
        self.role = None
        self.cam = None


class Rooms:
    def __init__(self, max_cameras, buffer_ms=0):
        self.max_cameras = max_cameras
        self.buffer_ms = buffer_ms  # viewer jitter buffer target, 0 = browser default
        self.peers = {}    # id -> Peer
        self.senders = {}  # cam -> Peer
        self.viewers = {}  # cam -> set[Peer]
        self._ids = itertools.count(1)

    def connect(self, ws):
        peer = Peer(next(self._ids), ws)
        self.peers[peer.id] = peer
        return peer

    async def disconnect(self, peer):
        self.peers.pop(peer.id, None)
        await self._leave(peer)

    def active_cams(self):
        return sorted(self.senders)

    async def set_buffer_ms(self, buffer_ms):
        self.buffer_ms = buffer_ms
        for peer in list(self.peers.values()):
            if peer.role == "viewer":
                await self._send(peer, {"type": "config", "bufferMs": buffer_ms})

    async def handle(self, peer, msg):
        kind = msg.get("type")
        if kind == "join":
            await self._join(peer, msg.get("role"), msg.get("cam"))
        elif kind == "leave":
            await self._leave(peer)
        elif kind in RELAY_TYPES:
            await self._relay(peer, msg)
        else:
            await self._error(peer, f"unknown message type: {kind!r}")

    async def _join(self, peer, role, cam):
        if role not in ROLES:
            return await self._error(peer, f"invalid role: {role!r}")
        if type(cam) is not int or not 1 <= cam <= self.max_cameras:
            return await self._error(peer, f"cam must be 1-{self.max_cameras}")

        await self._leave(peer)
        peer.role, peer.cam = role, cam
        viewers = self.viewers.setdefault(cam, set())

        if role == "viewer":
            viewers.add(peer)
            sender = self.senders.get(cam)
            log.info("Viewer %d joined cam %d", peer.id, cam)
            await self._send(peer, self._joined(peer, sender is not None))
            if sender is not None:
                await self._send(sender, {"type": "viewer-joined", "id": peer.id})
            return

        # Newest sender wins the slot.
        old = self.senders.get(cam)
        self.senders[cam] = peer
        if old is not None:
            old.role = old.cam = None
            log.info("Sender %d replaced sender %d on cam %d", peer.id, old.id, cam)
            await self._send(old, {"type": "replaced"})
            for v in list(viewers):
                await self._send(v, {"type": "sender-left", "from": old.id})
        else:
            log.info("Sender %d joined cam %d", peer.id, cam)

        await self._send(peer, self._joined(peer, True))
        for v in list(viewers):
            await self._send(peer, {"type": "viewer-joined", "id": v.id})

    async def _leave(self, peer):
        role, cam = peer.role, peer.cam
        if role is None:
            return
        peer.role = peer.cam = None

        if role == "sender":
            if self.senders.get(cam) is peer:
                del self.senders[cam]
            log.info("Sender %d left cam %d", peer.id, cam)
            for v in list(self.viewers.get(cam, ())):
                await self._send(v, {"type": "sender-left", "from": peer.id})
        else:
            self.viewers.get(cam, set()).discard(peer)
            log.info("Viewer %d left cam %d", peer.id, cam)
            sender = self.senders.get(cam)
            if sender is not None:
                await self._send(sender, {"type": "viewer-left", "id": peer.id})

    async def _relay(self, peer, msg):
        target = self.peers.get(msg.get("to"))
        if (peer.role is None or target is None or target.cam != peer.cam
                or target.role in (None, peer.role)):
            # Usually a late ICE candidate for a peer that just left.
            log.debug("Dropped %s from %d to %r", msg.get("type"), peer.id, msg.get("to"))
            return
        out = {k: v for k, v in msg.items() if k != "to"}
        out["from"] = peer.id
        await self._send(target, out)

    def _joined(self, peer, sender_present):
        return {"type": "joined", "id": peer.id, "role": peer.role, "cam": peer.cam,
                "senderPresent": sender_present, "bufferMs": self.buffer_ms}

    async def _error(self, peer, error):
        await self._send(peer, {"type": "error", "error": error})

    @staticmethod
    async def _send(peer, msg):
        if peer.ws.closed:
            return
        try:
            await peer.ws.send_json(msg)
        except (ConnectionError, RuntimeError) as e:
            log.debug("Send to %d failed: %s", peer.id, e)
