import asyncio
import websockets
import json
from datetime import datetime
import os

# 创建日志目录
log_dir = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(log_dir, exist_ok=True)

# 日志文件路径
log_file = os.path.join(log_dir, f"websocket_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")

# 存储所有连接的客户端
connected_clients = set()


def load_root_env():
    env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..", ".env"))
    if not os.path.isfile(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[len("export "):].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


def env_str(name, default):
    return os.environ.get(name) or default


def env_int(name, default):
    try:
        return int(env_str(name, str(default)))
    except ValueError:
        return default


def env_float(name, default):
    try:
        return float(env_str(name, str(default)))
    except ValueError:
        return default


load_root_env()

# 客户端配置，匹配 TeleopRemoteConfig 接口
client_config = {
    "head_track_cfg": {
        "fps": env_int("TELEOP_HEAD_TRACK_FPS", 30),
        "positionThreshold": env_float("TELEOP_HEAD_POSITION_THRESHOLD", 0.0001),
        "rotationThreshold": env_float("TELEOP_HEAD_ROTATION_THRESHOLD", 0.0001)
    },
    "controller_track_cfg": {
        "fps": env_int("TELEOP_CONTROLLER_TRACK_FPS", 50)
    },
    "hand_track_cfg": {
        "fps": env_int("TELEOP_HAND_TRACK_FPS", 50)
    },
    "video_container_cfg": {
        "enabled": True,
        "streamIds": [item.strip() for item in env_str("TELEOP_VIDEO_STREAM_IDS", "camera0,camera1").split(",") if item.strip()],
        "width": env_float("TELEOP_VIDEO_WIDTH", 2),
        "height": env_float("TELEOP_VIDEO_HEIGHT", 0.9),
        "distance": env_float("TELEOP_VIDEO_DISTANCE", 2),
        "numSmallVideos": env_int("TELEOP_VIDEO_NUM_SMALL", 1)
    },
    "mode": env_str("TELEOP_MODE", "controller_mode")  # 可以是 'hand_mode' 或 'controller_mode'
}

# 写入日志函数
def write_to_log(entry):
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    
async def handle_client(websocket):
    # 添加新的客户端连接
    client_id = id(websocket)
    connected_clients.add(websocket)
    
    # 记录新连接
    write_to_log({
        "timestamp": datetime.now().isoformat(),
        "event": "client_connected",
        "client_id": client_id,
        "total_clients": len(connected_clients)
    })
    
    try:
        # 向新连接的客户端发送配置信息
        config_message = {
            "type": "teleop_config",
            "data": client_config
        }
        await websocket.send(json.dumps(config_message))
        # 记录发送的配置
        write_to_log({
            "timestamp": datetime.now().isoformat(),
            "event": "config_sent",
            "client_id": client_id,
            "data": config_message
        })
        
        while True:
            try:
                # 等待接收消息
                message = await websocket.recv()
                
                # 尝试解析 JSON
                try:
                    parsed_message = json.loads(message)
                    
                    # 记录接收到的消息
                    write_to_log({
                        "timestamp": datetime.now().isoformat(),
                        "event": "message_received",
                        "client_id": client_id,
                        "data": parsed_message
                    })
                    if parsed_message.get("type") == "offer":
                        # 模拟返回answer
                        answer = {
                            "type": "answer",
                            "streamId": parsed_message.get("streamId", "default"),
                            "sdp": {
                                "type": "answer",
                                "sdp": "v=0\r\no=- 123456789 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\na=group:BUNDLE 0\r\na=msid-semantic: WMS\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\nc=IN IP4 0.0.0.0\r\na=rtcp:9 IN IP4 0.0.0.0\r\na=ice-ufrag:mock\r\na=ice-pwd:mockpassword\r\na=fingerprint:sha-256 00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00:00\r\na=setup:active\r\na=mid:0\r\na=recvonly\r\na=rtcp-mux\r\na=rtpmap:96 H264/90000\r\na=rtcp-fb:96 nack\r\na=rtcp-fb:96 nack pli\r\na=rtcp-fb:96 ccm fir\r\n"
                            }
                        }
                        await websocket.send(json.dumps(answer))
                        # 记录发送的answer
                        write_to_log({
                            "timestamp": datetime.now().isoformat(),
                            "event": "webrtc_signaling_answer_sent",
                            "client_id": client_id,
                            "data": answer
                        })
                        
                except json.JSONDecodeError:
                    # 记录非JSON消息
                    write_to_log({
                        "timestamp": datetime.now().isoformat(),
                        "event": "raw_message_received",
                        "client_id": client_id,
                        "data": message
                    })

            except websockets.ConnectionClosed:
                break
            except Exception as e:
                # 记录错误
                write_to_log({
                    "timestamp": datetime.now().isoformat(),
                    "event": "error",
                    "client_id": client_id,
                    "error": str(e)
                })
                break

    finally:
        # 客户端断开连接时清理
        connected_clients.remove(websocket)
        
        # 记录断开连接
        write_to_log({
            "timestamp": datetime.now().isoformat(),
            "event": "client_disconnected",
            "client_id": client_id,
            "total_clients": len(connected_clients)
        })

async def main():
    # 启动服务器
    port = env_int("TELEOP_SERVER_PORT", env_int("VITE_TELEOP_WS_PORT", 5174))
    host = env_str("TELEOP_SERVER_HOST", "localhost")
    # 主WebSocket服务器
    main_server = await websockets.serve(
        handle_client,
        host,  # 监听地址
        port,        # 端口
        ping_interval=20,  # 20秒发送一次ping以保持连接
        ping_timeout=10    # 10秒内没有收到pong则断开连接
    )
    
    # 记录服务器启动
    write_to_log(
    {
        "timestamp": datetime.now().isoformat(),
        "event": "server_started",
        "main_address": f"ws://{host}:{port}",
        "config": client_config
    })
    
    print(f"[{datetime.now()}] Main WebSocket server started at ws://{host}:{port}")
    print(f"Logging to: {log_file}")
    
    # 保持服务器运行
    await asyncio.Future()  # run forever

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 记录服务器停止
        write_to_log({
            "timestamp": datetime.now().isoformat(),
            "event": "server_stopped",
            "reason": "keyboard_interrupt"
        })
        print(f"\nServer stopped by user. Log file: {log_file}")
