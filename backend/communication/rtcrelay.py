from typing import Dict

from communication.tserver import TeleopServer
from bridge.bot_interface import RobotStateSyncClient
from communication.message import WebRTCSignalingMsg, WebRTCOfferMsg, WebRTCIceCandidateMsg
from teleop_env import env_float, env_int, env_list

class WebRTCRelay:
    def __init__(self, telop_server: TeleopServer, robot_client: RobotStateSyncClient):
        self.telop_server = telop_server
        self.robot_client = robot_client
        self.telop_server.register_callback("webrtc", self.on_vr_webrtc_msgs)
        self.robot_client.register_callback("webrtc", self.on_robot_webrtc_msgs)
        self.stream_ids = env_list("TELEOP_VIDEO_STREAM_IDS", ["camera0", "camera1"])
        self.config = {
            "video_container_cfg": {
                "enabled": True,
                "streamIds": self.stream_ids,
                "width": env_float("TELEOP_VIDEO_WIDTH", 2),
                "height": env_float("TELEOP_VIDEO_HEIGHT", 0.9),
                "distance": env_float("TELEOP_VIDEO_DISTANCE", 2),
                "numSmallVideos": env_int("TELEOP_VIDEO_NUM_SMALL", 1),
            }
        }
        self.telop_server.register_config(self.config)

    async def on_vr_webrtc_msgs(self, msg: WebRTCSignalingMsg):
        if isinstance(msg, WebRTCOfferMsg):
            await self._on_vr_offer_send(msg)
        elif isinstance(msg, WebRTCIceCandidateMsg):
            await self._on_vr_candidate_send(msg)
        else:
            raise NotImplementedError

    async def on_robot_webrtc_msgs(self, msg: Dict):
        if "action" not in msg:
            raise RuntimeError("action not in msg")
        if msg["action"] == "answer":
            await self.on_robot_answer_recv(msg)
        elif msg["action"] == "candidate":
            await self.on_robot_candidate_recv(msg)
        else:
            raise NotImplementedError

    async def _on_vr_offer_send(self, offer_msg: WebRTCOfferMsg):
        if self.robot_client.websocket:
            await self.robot_client.websocket.send(offer_msg.to_json())

    async def _on_vr_candidate_send(self, candidate_msg: WebRTCIceCandidateMsg):
        if self.robot_client.websocket:
            await self.robot_client.websocket.send(candidate_msg.to_json())

    async def on_robot_answer_recv(self, answer_msg: dict):
        for c in self.telop_server.active_connections:
            await self.telop_server.send_to_client(c, answer_msg)
