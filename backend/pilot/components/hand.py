import logging
from dataclasses import dataclass
from typing import Optional, List, Dict, Callable, Union
from communication.message import LeftHandMsg, RightHandMsg
from communication.tserver import TeleopServer
from teleop_env import env_int


logger = logging.getLogger("HandReceiver")

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
class HandState:
    isTracked: bool  # 大概率没用
    isPinched: bool
    pinchStrength: float
    gesture: Optional[str]
    handConfidence: float

@dataclass
class HandData:
    isLeft: bool
    position: Optional[Vector3] = None
    rotation: Optional[Vector3] = None
    state: Optional[HandState] = None
    jointPositions: Optional[List[Vector3]] = None
    jointRotations: Optional[List[Quaternion]] = None
    timestamp: Optional[float] = None

class HandReceiver:
    def __init__(self, server: TeleopServer):
        self.server = server
        self.config = {
            "hand_track_cfg": {
                "fps": env_int("TELEOP_HAND_TRACK_FPS", 50)
            },
            "mode": "hand_mode",
        }
        self.server.register_config(self.config)
        self.left_hand_data: Optional[HandData] = None
        self.right_hand_data: Optional[HandData] = None

        self.handler_ids = []
        self._register_handlers()

        self.callbacks: Dict[str, List[Callable]] = {
            "left_hand": [],
            "right_hand": [], 
            "any_hand": []
        }

        logger.info("手部组件已初始化")
    
    def _register_handlers(self):
        left_id = self.server.register_callback("left_hand", self._handle_left_hand, "hand_left")
        right_id = self.server.register_callback("right_hand", self._handle_right_hand, "hand_right")
        self.handler_ids.extend([left_id, right_id])
        logger.info("已注册手势消息处理器")

    def register_callback(self, callback: Callable, hand_type: str = "any_hand") -> str:
        if hand_type not in self.callbacks:
            raise ValueError(f"无效的手势类型: {hand_type}")

        callback_id = f"hand_callback_{id(callback)}"
        self.callbacks[hand_type].append(callback)
        logger.debug(f"已注册手势回调 {callback_id} 用于 {hand_type}")
        return callback_id

    def unregister_callback(self, callback: Callable, hand_type: str = "any_hand") -> bool:
            if hand_type not in self.callbacks:
                return False

            if callback in self.callbacks[hand_type]:
                self.callbacks[hand_type].remove(callback)
                logger.debug(f"已取消注册手势回调用于 {hand_type}")
                return True

            return False

    def _parse_hand_data(self, message: Union[LeftHandMsg, RightHandMsg]) -> HandData:
        isLeft = isinstance(message, LeftHandMsg)

        data = message.data
        timestamp = message.timestamp

        position = None
        if 'position' in data:
            pos = data['position']
            position = Vector3(
                x=float(pos.get('x', 0)),
                y=float(pos.get('y', 0)),
                z=float(pos.get('z', 0))
            )

        rotation = None
        if 'rotation' in data:
            rot = data['rotation']
            rotation = Quaternion(
                x=rot[0],
                y=rot[1],
                z=rot[2],
                w=rot[3]
            )

        state = None
        if 'state' in data:
            s = data['state']
            state = HandState(
                isTracked=bool(s.get('isTracked', False)),
                isPinched=bool(s.get('isPinched', False)),
                pinchStrength=float(s.get('pinchStrength', 0.0)),
                gesture=s.get('gesture', None),
                handConfidence=float(s.get('handConfidence', 0.0))
            )

        jointPositions = None
        if 'jointPositions' in data:
            jointPositions = [Vector3(x=float(p['x']), y=float(p['y']), z=float(p['z'])) 
                             for p in data['jointPositions']]

        jointRotations = None
        if 'jointRotations' in data:
            jointRotations = [Quaternion(x=r[0], y=r[1], z=r[2], w=r[3]) 
                             for r in data['jointRotations']]

        return HandData(
            isLeft=isLeft,
            position=position,
            rotation=rotation,
            state=state,
            jointPositions=jointPositions,
            jointRotations=jointRotations,
            timestamp=timestamp
        )


    def _notify_callbacks(self, hand_data: HandData, hand_type: str):
        for callback in self.callbacks[hand_type]:
            try:
                callback(hand_data)
            except Exception as e:
                logger.error(f"执行手势回调时出错: {str(e)}")

        for callback in self.callbacks["any_hand"]:
            try:
                callback(hand_data)
            except Exception as e:
                logger.error(f"执行手势回调时出错: {str(e)}")

    async def _handle_left_hand(self, message: LeftHandMsg):
        try:
            hand_data = self._parse_hand_data(message)
            self.left_hand_data = hand_data

            self._notify_callbacks(hand_data, "left_hand")

            logger.debug("已处理左手势消息")
        except Exception as e:
            logger.error(f"处理左手势消息时出错: {str(e)}")

    async def _handle_right_hand(self, message: RightHandMsg):
        try:
            hand_data = self._parse_hand_data(message)
            self.right_hand_data = hand_data

            self._notify_callbacks(hand_data, "right_hand")

            logger.debug("已处理右手势消息")
        except Exception as e:
            logger.error(f"处理右手势消息时出错: {str(e)}")

    def get_left_hand_data(self) -> Optional[HandData]:
        """获取最新的左手势数据"""
        return self.left_hand_data

    def get_right_hand_data(self) -> Optional[HandData]:
        """获取最新的右手势数据"""
        return self.right_hand_data

    def cleanup(self):
        """清理资源，取消注册处理器"""
        for handler_id in self.handler_ids:
            self.server.unregister(handler_id)

        logger.info("手势组件已清理")
