import json
from typing import Dict, Any, Optional, ClassVar, Type, Callable


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

class WebRTCMsg(Msg):
    msg_type: ClassVar[str] = "webrtc"
    action: ClassVar[str] = None

    def __init__(self, **kwargs):
        self.action = kwargs.pop("action", self.__class__.action)
        for key, value in kwargs.items():
            setattr(self, key, value)

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
class WebRTCIceCandidateMsg(WebRTCSignalingMsg):
    action = "ice_candidate"

    def __init__(self, streamId: str, candidate: Dict[str, Any], **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)
        self.streamId = streamId
        self.candidate = candidate

@MessageFactory.register
class WebRTCAnswerMsg(WebRTCSignalingMsg):
    action = "answer"
    def __init__(self, streamId: str, sdp: Dict[str, Any], **kwargs):
        kwargs["action"] = self.action
        super().__init__(**kwargs)
        self.streamId = streamId
        self.sdp = sdp