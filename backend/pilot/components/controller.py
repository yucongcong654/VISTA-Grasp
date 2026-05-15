import logging
from typing import Dict, Optional, List, Callable, Union
from dataclasses import dataclass
from communication.message import LeftControllerMsg, RightControllerMsg
from communication.tserver import TeleopServer
from teleop_env import env_int

logger = logging.getLogger("ControllerReceiver")

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
class ControllerState:
    trigger: bool
    squeeze: bool
    touchpad: bool
    thumbstick: bool
    aButton: bool
    bButton: bool
    triggerValue: float
    squeezeValue: float
    touchpadValue: List[float]  # [x, y]
    thumbstickValue: List[float]  # [x, y]
    aButtonValue: bool
    bButtonValue: bool

@dataclass
class ControllerData:
    isLeft: bool
    position: Optional[Vector3] = None
    rotation: Optional[Quaternion] = None
    state: Optional[ControllerState] = None
    timestamp: Optional[float] = None

class ControllerReceiver:
    def __init__(self, server: TeleopServer):
        self.server = server
        self.config = {
            "controller_track_cfg": {
                "fps": env_int("TELEOP_CONTROLLER_TRACK_FPS", 50)
            },
            "mode": "controller_mode",
        }
        self.server.register_config(self.config)
        self.left_controller_data: Optional[ControllerData] = None
        self.right_controller_data: Optional[ControllerData] = None

        # 注册回调函数
        self.handler_ids = []
        self._register_handlers()

        # 回调函数字典，用于存储注册的外部回调
        self.callbacks: Dict[str, List[Callable]] = {
            "left_controller": [],
            "right_controller": [],
            "any_controller": []
        }

        logger.info("控制器组件已初始化")

    def _register_handlers(self):
        """注册消息处理器"""
        left_id = self.server.register_callback("left_controller", self._handle_left_controller, "controller_left")
        right_id = self.server.register_callback("right_controller", self._handle_right_controller, "controller_right")
        self.handler_ids.extend([left_id, right_id])
        logger.info("已注册控制器消息处理器")

    def register_callback(self, callback: Callable, controller_type: str = "any_controller") -> str:

        if controller_type not in self.callbacks:
            raise ValueError(f"无效的控制器类型: {controller_type}")

        callback_id = f"controller_callback_{id(callback)}"
        self.callbacks[controller_type].append(callback)
        logger.debug(f"已注册控制器回调 {callback_id} 用于 {controller_type}")
        return callback_id

    def unregister_callback(self, callback: Callable, controller_type: str = "any_controller") -> bool:
        if controller_type not in self.callbacks:
            return False

        if callback in self.callbacks[controller_type]:
            self.callbacks[controller_type].remove(callback)
            logger.debug(f"已取消注册控制器回调用于 {controller_type}")
            return True

        return False

    def _parse_controller_data(self, message: Union[LeftControllerMsg, RightControllerMsg]) -> ControllerData:

        is_left = isinstance(message, LeftControllerMsg)

        data = message.data
        timestamp = message.timestamp

        # 解析位置
        position = None
        if 'position' in data:
            pos = data['position']
            position = Vector3(
                x=float(pos.get('x', 0)),
                y=float(pos.get('y', 0)),
                z=float(pos.get('z', 0))
            )

        # 解析旋转
        rotation = None
        if 'rotation' in data:
            rot = data['rotation']
            rotation = Quaternion(
                x = rot[0],
                y = rot[1],
                z = rot[2],
                w = rot[3]
            )

        # 解析状态
        state = None
        if 'state' in data:
            s = data['state']
            state = ControllerState(
                trigger=bool(s.get('trigger', False)),
                squeeze=bool(s.get('squeeze', False)),
                touchpad=bool(s.get('touchpad', False)),
                thumbstick=bool(s.get('thumbstick', False)),
                aButton=bool(s.get('aButton', False)),
                bButton=bool(s.get('bButton', False)),
                triggerValue=float(s.get('triggerValue', 0)),
                squeezeValue=float(s.get('squeezeValue', 0)),
                touchpadValue=s.get('touchpadValue', [0, 0]),
                thumbstickValue=s.get('thumbstickValue', [0, 0]),
                aButtonValue=bool(s.get('aButtonValue', False)),
                bButtonValue=bool(s.get('bButtonValue', False))
            )

        return ControllerData(
            isLeft=is_left,
            position=position,
            rotation=rotation,
            state=state,
            timestamp=timestamp
        )

    def _notify_callbacks(self, controller_data: ControllerData, controller_type: str):
        for callback in self.callbacks[controller_type]:
            try:
                callback(controller_data)
            except Exception as e:
                logger.error(f"执行控制器回调时出错: {str(e)}")

        # 调用通用回调
        for callback in self.callbacks["any_controller"]:
            try:
                callback(controller_data)
            except Exception as e:
                logger.error(f"执行控制器回调时出错: {str(e)}")

    async def _handle_left_controller(self, message: LeftControllerMsg):
        try:
            controller_data = self._parse_controller_data(message)
            self.left_controller_data = controller_data

            # 通知回调
            self._notify_callbacks(controller_data, "left_controller")

            logger.debug("已处理左控制器消息")
        except Exception as e:
            logger.error(f"处理左控制器消息时出错: {str(e)}")

    async def _handle_right_controller(self, message: RightControllerMsg):
        try:
            controller_data = self._parse_controller_data(message)
            self.right_controller_data = controller_data

            # 通知回调
            self._notify_callbacks(controller_data, "right_controller")

            logger.debug("已处理右控制器消息")
        except Exception as e:
            logger.error(f"处理右控制器消息时出错: {str(e)}")

    def get_left_controller_data(self) -> Optional[ControllerData]:
        """获取最新的左控制器数据"""
        return self.left_controller_data

    def get_right_controller_data(self) -> Optional[ControllerData]:
        """获取最新的右控制器数据"""
        return self.right_controller_data

    def cleanup(self):
        """清理资源，取消注册处理器"""
        for handler_id in self.handler_ids:
            self.server.unregister(handler_id)

        logger.info("控制器组件已清理")
