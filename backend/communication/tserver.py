import json
import asyncio
import logging
import websockets
from concurrent.futures import ThreadPoolExecutor
from websockets.server import WebSocketServerProtocol
from typing import Dict, Any, Optional, List, Callable, Set, Union
from communication.message import Msg, SystemMsg, MessageFactory, ErrorMsg, ConfigResponseMsg, StatusResponseMsg, PongMsg
from teleop_env import env_int, env_str

logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("TeleopServer")

class TeleopServer:
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 ping_interval: int = 20, ping_timeout: int = 20):
        # WebSocket 配置
        self.host = host or env_str("TELEOP_SERVER_HOST", "localhost")
        self.port = port if port is not None else env_int("TELEOP_SERVER_PORT", 5174, aliases=("VITE_TELEOP_WS_PORT",))
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        self.config = {}
        
        # WebSocket 服务器
        self.server = None
        self.active_connections: Set[WebSocketServerProtocol] = set()
        
        self.message_queues: Dict[str, List[asyncio.Queue]] = {}
        self.message_callbacks: Dict[str, List[Callable]] = {}
        self.registered_handlers: Dict[str, List[str]] = {}
        self.thread_pool = ThreadPoolExecutor(max_workers=10)
        
        # 服务器状态
        self.running = False
        self.server_task = None

    async def _websocket_handler(self, websocket: WebSocketServerProtocol):
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}"
        logger.info(f"客户端连接: {client_id}")
        
        # 添加到活动连接集合
        self.active_connections.add(websocket)
        
        try:
            
            async for message_str in websocket:
                try:
                    message = MessageFactory.create_from_json(message_str)
                    message._ws = websocket
                    logger.debug(f"从 {client_id} 接收到消息: {message.to_dict()}")
                    
                    await self.handle_message(message, websocket)
                    
                except json.JSONDecodeError:
                    error_msg = ErrorMsg("无效的JSON格式")
                    await websocket.send(error_msg.to_json())
                    logger.error("无效的JSON格式")
                except ValueError as e:
                    error_msg = ErrorMsg(f"无效的消息格式: {str(e)}")
                    await websocket.send(error_msg.to_json())
                    logger.error(f"无效的消息格式: {str(e)}")
                except Exception as e:
                    logger.error(f"处理来自 {client_id} 的消息时出错: {str(e)}")
                    error_msg = ErrorMsg(f"服务器错误: {str(e)}")
                    await websocket.send(error_msg.to_json())
        
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"客户端 {client_id} 断开连接: {e.code} {e.reason}")
        except Exception as e:
            logger.error(f"与客户端 {client_id} 的连接出错: {str(e)}")
        finally:
            self.active_connections.remove(websocket)
            logger.info(f"客户端 {client_id} 连接已关闭，剩余连接数: {len(self.active_connections)}")

    async def handle_message(self, message: Msg, sender: Optional[WebSocketServerProtocol] = None):
        message_type = message.msg_type
        if message_type == 'system':
            await self._handle_system_message(message, sender)
            return
        
        await self.send_message(message)
        
        if hasattr(message, 'broadcast') and getattr(message, 'broadcast', False) and sender is not None:
            await self.broadcast_message(message, exclude=sender)

    async def _handle_system_message(self, message: SystemMsg, sender: Optional[WebSocketServerProtocol]):
        action = message.action
        
        if action == 'ping':
            # 响应ping请求
            if sender:
                pong_msg = PongMsg(timestamp=getattr(message, 'timestamp', None))
                await sender.send(pong_msg.to_json())
        
        elif action == 'get_status':
            # 发送服务器状态
            if sender:
                status_msg = StatusResponseMsg(
                    registered_types=self.get_registered_types(),
                    active_connections=len(self.active_connections),
                    running=self.running
                )
                await sender.send(status_msg.to_json())
        elif action == 'get_config':
            if sender:
                assert len(self.config) > 0, "No config registered"
                config_msg = ConfigResponseMsg(config=self.config)
                await sender.send(config_msg.to_json())

    def register_config(self, partial_config: Dict[str, Any], **kwargs):
        self.config.update(partial_config, **kwargs)

    def register_queue(self, message_type: str, queue: asyncio.Queue, handler_id: Optional[str] = None) -> str:
        if message_type not in self.message_queues:
            self.message_queues[message_type] = []
        
        self.message_queues[message_type].append(queue)
        
        # 生成或使用处理器ID
        if handler_id is None:
            handler_id = f"queue_{id(queue)}"
        
        # 记录注册信息
        if handler_id not in self.registered_handlers:
            self.registered_handlers[handler_id] = []
        self.registered_handlers[handler_id].append(message_type)
        
        logger.info(f"已注册队列处理器 {handler_id} 用于消息类型 '{message_type}'")
        return handler_id
    
    def register_callback(self, message_type: str, callback: Callable, handler_id: Optional[str] = None) -> str:
        if message_type not in self.message_callbacks:
            self.message_callbacks[message_type] = []
        
        self.message_callbacks[message_type].append(callback)
        if handler_id is None:
            handler_id = f"callback_{id(callback)}"
        
        if handler_id not in self.registered_handlers:
            self.registered_handlers[handler_id] = []
        self.registered_handlers[handler_id].append(message_type)
        
        logger.info(f"已注册回调处理器 {handler_id} 用于消息类型 '{message_type}'")
        return handler_id
    
    def unregister(self, handler_id: str) -> bool:
        if handler_id not in self.registered_handlers:
            logger.warning(f"处理器 {handler_id} 未注册")
            return False
        
        for message_type in self.registered_handlers[handler_id]:
            # 从队列列表中移除
            if message_type in self.message_queues:
                if handler_id.startswith("queue_"):
                    # 找到对应的队列并移除
                    for i, queue in enumerate(self.message_queues[message_type]):
                        if f"queue_{id(queue)}" == handler_id:
                            self.message_queues[message_type].pop(i)
                            break
            
            # 从回调列表中移除
            if message_type in self.message_callbacks:
                if handler_id.startswith("callback_"):
                    # 找到对应的回调并移除
                    for i, callback in enumerate(self.message_callbacks[message_type]):
                        if f"callback_{id(callback)}" == handler_id:
                            self.message_callbacks[message_type].pop(i)
                            break
        
        # 移除注册记录
        del self.registered_handlers[handler_id]
        logger.info(f"已取消注册处理器 {handler_id}")
        return True
    
    async def send_message(self, message: Msg) -> bool:
        message_type = message.msg_type
        dispatch_tasks = []
        
        if message_type in self.message_queues:
            for queue in self.message_queues[message_type]:
                dispatch_tasks.append(queue.put(message))
        
        if message_type in self.message_callbacks:
            for callback in self.message_callbacks[message_type]:
                if asyncio.iscoroutinefunction(callback):
                    dispatch_tasks.append(callback(message))
                else:
                    loop = asyncio.get_running_loop()
                    dispatch_tasks.append(
                        loop.run_in_executor(self.thread_pool, callback, message)
                    )
        
        if dispatch_tasks:
            await asyncio.gather(*dispatch_tasks)
            logger.debug(f"已分发类型为 '{message_type}' 的消息")
            return True
        else:
            logger.debug(f"没有处理器注册用于消息类型 '{message_type}'")
            return False
    
    async def broadcast_message(self, message: Msg, exclude: Optional[WebSocketServerProtocol] = None) -> int:
        if not self.active_connections:
            return 0
        
        message_json = message.to_json()
        send_count = 0
        
        send_tasks = []
        for ws in self.active_connections:
            if exclude is not None and ws == exclude:
                continue
                
            send_tasks.append(ws.send(message_json))
        
        if send_tasks:
            results = await asyncio.gather(*send_tasks, return_exceptions=True)
            send_count = sum(1 for r in results if not isinstance(r, Exception))
            
        return send_count
    
    async def start_server(self):
        if self.server is not None:
            logger.warning("WebSocket服务器已经在运行")
            return
        
        self.running = True
        
        self.server = await websockets.serve(
            self._websocket_handler,
            self.host,
            self.port,
            ping_interval=self.ping_interval,
            ping_timeout=self.ping_timeout
        )
        
        logger.info(f"TeleopServer WebSocket服务器已启动在 {self.host}:{self.port}")
    
    async def stop_server(self):
        if not self.running:
            logger.warning("服务器未运行")
            return
        
        if self.active_connections:
            close_tasks = []
            for ws in self.active_connections:
                close_tasks.append(ws.close(1001, "服务器关闭"))
            
            if close_tasks:
                await asyncio.gather(*close_tasks, return_exceptions=True)
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        
        self.thread_pool.shutdown(wait=False)
        
        self.running = False
        logger.info("TeleopServer WebSocket服务器已停止")
    
    def get_registered_types(self) -> List[str]:
        all_types = set()
        all_types.update(self.message_queues.keys())
        all_types.update(self.message_callbacks.keys())
        return list(all_types)
    
    def get_handlers_for_type(self, message_type: str) -> Dict[str, int]:
        queue_count = len(self.message_queues.get(message_type, []))
        callback_count = len(self.message_callbacks.get(message_type, []))
        return {
            "queues": queue_count,
            "callbacks": callback_count,
            "total": queue_count + callback_count
        }
    
    async def send_to_client(self, client: WebSocketServerProtocol, message: Union [Msg, Dict]) -> bool:
        if client not in self.active_connections:
            logger.warning("客户端不在活动连接列表中")
            return False
        if isinstance(message, Msg):
            data = message.to_json()
        elif isinstance(message, dict):
            data = json.dumps(message)
        else:
            raise RuntimeError("类型不符")
        try:
            await client.send(data)
            return True
        except Exception as e:
            logger.error(f"发送消息给客户端时出错: {str(e)}")
            return False
