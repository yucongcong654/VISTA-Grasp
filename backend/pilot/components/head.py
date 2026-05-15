import asyncio
import logging
from typing import Optional, List, Callable
from dataclasses import dataclass
from communication.message import HeadMsg
from communication.tserver import TeleopServer
from teleop_env import env_float, env_int

# Configure logging
logger = logging.getLogger("HeadReceiver")


@dataclass
class Vector3:
    x: float
    y: float
    z: float


@dataclass
class Quaternion:
    x: float
    y: float
    z: float
    w: float


@dataclass
class HeadData:
    position: Optional[Vector3] = None
    rotation: Optional[Quaternion] = None
    timestamp: Optional[float] = None


class HeadReceiver:
    """
    Head component for receiving and processing VR headset data
    """

    def __init__(self, server: TeleopServer):
        """
        Initialize the head component

        Args:
            server: TeleopServer instance
        """
        self.server = server
        self.config = {
            "head_track_cfg": {
                "fps": env_int("TELEOP_HEAD_TRACK_FPS", 30),
                "positionThreshold": env_float("TELEOP_HEAD_POSITION_THRESHOLD", 0.0001),
                "rotationThreshold": env_float("TELEOP_HEAD_ROTATION_THRESHOLD", 0.0001),
            }
        }
        self.server.register_config(self.config)
        self.head_data: Optional[HeadData] = None

        self.handler_ids = []
        self._register_handlers()

        self.callbacks: List[Callable] = []

        logger.info("Head component initialized")

    def _register_handlers(self):
        """Register message handlers"""
        head_id = self.server.register_callback(
            "head_move", self._handle_head, "head_receiver"
        )
        self.handler_ids.append(head_id)
        logger.info("Registered head message handler")

    def register_callback(self, callback: Callable) -> str:
        callback_id = f"head_callback_{id(callback)}"
        self.callbacks.append(callback)
        logger.debug(f"Registered head callback {callback_id}")
        return callback_id

    def unregister_callback(self, callback: Callable) -> bool:
        if callback in self.callbacks:
            self.callbacks.remove(callback)
            logger.debug(f"Unregistered head callback")
            return True
        return False

    def _parse_head_data(self, message: HeadMsg) -> HeadData:
        data = message.data
        timestamp = message.timestamp

        # Parse position
        position = None
        if "position" in data:
            pos = data["position"]
            position = Vector3(
                x=float(pos.get("x", 0)),
                y=float(pos.get("y", 0)),
                z=float(pos.get("z", 0)),
            )

        # Parse rotation
        rotation = None
        if "rotation" in data:
            rot = data["rotation"]
            rotation = Quaternion(
                x=float(rot.get("x", 0)),
                y=float(rot.get("y", 0)),
                z=float(rot.get("z", 0)),
                w=float(rot.get("w", 1)),
            )

        return HeadData(position=position, rotation=rotation, timestamp=timestamp)

    def _notify_callbacks(self, head_data: HeadData):
        for callback in self.callbacks:
            try:
                callback(head_data)
            except Exception as e:
                logger.error(f"Error executing head callback: {str(e)}")

    async def _handle_head(self, message: HeadMsg):
        try:
            head_data = self._parse_head_data(message)
            self.head_data = head_data

            # Notify callbacks
            self._notify_callbacks(head_data)

            logger.debug("Processed head message")
        except Exception as e:
            logger.error(f"Error processing head message: {str(e)}")

    def get_head_data(self) -> Optional[HeadData]:
        return self.head_data

    def cleanup(self):
        for handler_id in self.handler_ids:
            self.server.unregister(handler_id)

        logger.info("头部组件清理完成")
