import sys
import asyncio
from typing import Dict, Callable
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCIceCandidate

from cam.bot_message import WebRTCOfferMsg, WebRTCIceCandidateMsg, WebRTCAnswerMsg

import os
parent_dirpath = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(parent_dirpath)

class RTCManager:
    def __init__(self, send_to_client: Callable[[WebRTCAnswerMsg], None]):
        self.peer_connections: Dict[str, RTCPeerConnection] = {}
        self.send_to_client = send_to_client

    async def handle_offer(self, message: WebRTCOfferMsg, create_track: Callable[[str], object]):
        stream_id = message.streamId
        pc = RTCPeerConnection()
        self.peer_connections[stream_id] = pc

        @pc.on("connectionstatechange")
        async def on_state_change():
            if pc.connectionState in ["failed", "closed"]:
                await self.cleanup(stream_id)

        # add video track
        track = create_track(stream_id)
        pc.addTrack(track)

        # set remote and local descriptions
        await pc.setRemoteDescription(
            RTCSessionDescription(**message.sdp["sdp"])
        )
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        answer_msg = WebRTCAnswerMsg(
            streamId=stream_id,
            sdp={"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
        )
        # send answer back to client 此时的Answer已经包含了本地的SDP信息和ICE候选者的信息
        await self.send_to_client(answer_msg)

    async def handle_ice_candidate(self, message: WebRTCIceCandidateMsg):
        stream_id = message.streamId
        pc = self.peer_connections.get(stream_id)
        if not pc:
            return
        candidate = RTCIceCandidate(**message.candidate)
        await pc.addIceCandidate(candidate)

    async def cleanup(self, stream_id: str):
        pc = self.peer_connections.pop(stream_id, None)
        if pc:
            await pc.close()

    async def stop_all(self):
        coros = [pc.close() for pc in self.peer_connections.values()]
        await asyncio.gather(*coros)
        self.peer_connections.clear()
