import json
from datetime import datetime
from typing import Dict, Any, Optional, ClassVar, Type, List, Callable


class Msg:
    msg_type: ClassVar[str]
    
    def to_dict(self) -> Dict[str, Any]:
        result = {"type": self.msg_type}
        for key, value in self.__dict__.items():
            if not key.startswith('_'):
                result[key] = value
        if hasattr(self, "action"):
            result["action"] = getattr(self, "action")
        return result
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Msg':
        msg_data = {k: v for k, v in data.items() if k != 'type'}
        return cls(**msg_data)

class ClientMsg(Msg):
    def __init__(self, data: Optional[Dict[str, Any]], timestamp: Optional[float] = None, **kwargs):
        self.data = data
        self.timestamp = datetime.now().timestamp() if timestamp is None else timestamp
        for key, value in kwargs.items():
            setattr(self, key, value)

class ServerMsg(Msg):
    def __init__(self, data: Optional[Dict[str, Any]], timestamp: Optional[float] = None, **kwargs):
        self.data = data
        self.timestamp = datetime.now().timestamp() if timestamp is None else timestamp
        for key, value in kwargs.items():
            setattr(self, key, value)

class SystemMsg(Msg):
    msg_type: ClassVar[str] = "system"
    action: ClassVar[str] = None

    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)

class WebRTCMsg(Msg):
    msg_type: ClassVar[str] = "webrtc"
    action: ClassVar[str] = None

    def __init__(self, **kwargs):
        self.action = kwargs.pop("action", self.__class__.action)
        for key, value in kwargs.items():
            setattr(self, key, value)

class MessageFactory:
    _msg_classes: Dict[str, Dict[Optional[str], Type[Msg]]] = {}

    @classmethod
    def register(cls, msg_class: Type[Msg] = None) -> Callable:
        def _register(msg_class: Type[Msg]) -> Type[Msg]:
            msg_type = msg_class.msg_type

            if msg_type not in cls._msg_classes:
                cls._msg_classes[msg_type] = {}

            action = getattr(msg_class, "action", None)
            cls._msg_classes[msg_type][action] = msg_class

            return msg_class

        if msg_class is not None:
            return _register(msg_class)
        return _register

    @classmethod
    def create_from_dict(cls, data: Dict[str, Any]) -> Msg:
        if 'type' not in data:
            raise ValueError("消息必须包含'type'字段")

        msg_type = data['type']

        if msg_type not in cls._msg_classes:
            raise ValueError(f"未知的消息类型: {msg_type}")

        if 'action' in data:
            action = data['action']
            if action in cls._msg_classes[msg_type]:
                return cls._msg_classes[msg_type][action].from_dict(data)
            elif None in cls._msg_classes[msg_type]:
                return cls._msg_classes[msg_type][None].from_dict(data)

        if None in cls._msg_classes[msg_type]:
            return cls._msg_classes[msg_type][None].from_dict(data)

        raise ValueError(f"无法创建消息类型: {msg_type}")

    @classmethod
    def create_from_json(cls, json_str: str) -> Msg:
        """从JSON字符串创建消息对象"""
        data = json.loads(json_str)
        return cls.create_from_dict(data)

@MessageFactory.register
class PingMsg(SystemMsg):
    action = "ping"

    def __init__(self, timestamp: Optional[float] = None):
        self.timestamp = timestamp or datetime.now().timestamp()

@MessageFactory.register
class PongMsg(SystemMsg):
    action = "pong"
    def __init__(self, timestamp: float):
        super().__init__(action="pong")
        self.timestamp = timestamp
    @classmethod
    def from_ping_msg(cls, ping_msg: PingMsg):
        return cls(ping_msg.timestamp)

@MessageFactory.register
class WebRTCSignalingMsg(WebRTCMsg):
    action = "webrtc"
    def __init__(self, **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)

@MessageFactory.register
class WebRTCOfferMsg(WebRTCSignalingMsg):
    action = "offer"
    def __init__(self, streamId: str, sdp: Dict[str, Any], **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)
        self.streamId = streamId
        self.sdp = sdp

@MessageFactory.register
class WebRTCAnswerMsg(WebRTCSignalingMsg):
    action = "answer"
    def __init__(self, streamId: str, sdp: Dict[str, Any], **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)
        self.streamId = streamId
        self.sdp = sdp

@MessageFactory.register
class WebRTCIceCandidateMsg(WebRTCSignalingMsg):
    action = "ice_candidate"

    def __init__(self, streamId: str, candidate: Dict[str, Any], **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)
        self.streamId = streamId
        self.candidate = candidate

@MessageFactory.register
class WebRTCRequestStreamMsg(WebRTCSignalingMsg):
    action = "request_stream"
    def __init__(self, streamId: str, **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)
        self.streamId = streamId

@MessageFactory.register
class WebRTCErrorMsg(WebRTCSignalingMsg):
    action = "error"
    def __init__(self, error: str, streamId: Optional[str] = None, **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)
        self.error = error
        if streamId:
            self.streamId = streamId

@MessageFactory.register
class StatusRequestMsg(SystemMsg):
    action = "get_status"

    def __init__(self): ...

@MessageFactory.register
class StatusResponseMsg(SystemMsg):
    action = "status"

    def __init__(
        self, registered_types: List[str], active_connections: int, running: bool
    ):
        self.registered_types = registered_types
        self.active_connections = active_connections
        self.running = running

@MessageFactory.register
class ConfigGetMsg(SystemMsg):
    action = "get_config"

@MessageFactory.register
class ConfigResponseMsg(SystemMsg):
    action = "config"

    def __init__(self, config: Dict[str, Any]):
        self.data = {"config": config}

@MessageFactory.register
class WelcomeMsg(SystemMsg):
    action = "welcome"

    def __init__(self, message: str = "已连接到 TeleopServer"):
        self.message = message

@MessageFactory.register
class ErrorMsg(ServerMsg):
    msg_type: ClassVar[str] = "error"
    
    def __init__(self, message: str):
        self.message = message

class HandMsg(ClientMsg):
    ...
    def __init__(self, timestamp: Optional[float] = None, data: Optional[Dict[str, Any]] = None, **kwargs):
        self.timestamp = timestamp
        self.data = data

@MessageFactory.register
class RequestStreamMsg(ClientMsg):
    msg_type: ClassVar[str] = "request_stream"
    def __init__(self, streamId: str, timestamp: Optional[float] = None, **kwargs):
        self.streamId = streamId
        self.timestamp = timestamp or datetime.now().timestamp()

@MessageFactory.register
class LeftHandMsg(HandMsg):
    msg_type: ClassVar[str] = "left_hand"
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@MessageFactory.register
class RightHandMsg(HandMsg):
    msg_type: ClassVar[str] = "right_hand"

class ControllerMsg(ClientMsg): 
    ...
    def __init__(self, timestamp: Optional[float] = None, data: Optional[Dict[str, Any]] = None, **kwargs):
        self.timestamp = timestamp
        self.data = data

@MessageFactory.register
class LeftControllerMsg(ControllerMsg):
    msg_type: ClassVar[str] = "left_controller"
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@MessageFactory.register
class RightControllerMsg(ControllerMsg):
    msg_type: ClassVar[str] = "right_controller"
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

@MessageFactory.register
class HeadMsg(ClientMsg):
    msg_type: ClassVar[str] = "head_move"
    def __init__(self,**kwargs):
        super().__init__(**kwargs)

@MessageFactory.register
class RobotControlMsg(ClientMsg):
    msg_type: ClassVar[str] = "robot_control"
    
    def __init__(self, command: str, params: Optional[Dict[str, Any]] = None):
        self.command = command
        self.params = params or {}
        self.timestamp = datetime.now().timestamp()

@MessageFactory.register
class SensorDataMsg(ServerMsg):
    msg_type: ClassVar[str] = "sensor_data"
    
    def __init__(self, sensor_id: str, values: Dict[str, float], timestamp: Optional[float] = None):
        self.sensor_id = sensor_id
        self.values = values
        self.timestamp = timestamp or datetime.now().timestamp()
