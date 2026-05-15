import { useState, useEffect } from "react";
import useWebSocket from "react-use-websocket";
import { getWebSocketUrl } from "../utils/url";
import { useConfigStore } from "../utils/configStore";
import { toast } from "react-toastify";

const WebSocketConfigListener = () => {
  const configLocal = useConfigStore((state) => state.configLocal);
  const updateServerConfig = useConfigStore((state) => state.setRemoteConfig);
  const websocketPort = useConfigStore(
    (state) => state.configLocal.websocketPort
  );
  const [configReceived, setConfigReceived] = useState(false);

  // 使用WebSocket监听配置更新
  const { sendJsonMessage, lastMessage, readyState } = useWebSocket(
    getWebSocketUrl("", websocketPort),
    {
      share: true,
      onOpen: () => {
        console.log("WebSocket连接已打开，准备发送配置请求");
      },
      shouldReconnect: () => configLocal.shouldReconnect,
      reconnectInterval: configLocal.reconnectInterval,
      reconnectAttempts: configLocal.reconnectAttempts,
    }
  );

  // 发送配置请求

  // 当WebSocket连接打开时发送配置请求
  useEffect(() => {
    const sendConfigRequest = () => {
      try {
        sendJsonMessage({
          type: "system",
          action: "get_config",
          timestamp: Date.now(),
        });
        console.log("配置请求已发送");
      } catch (error) {
        console.error("发送配置请求失败:", error);
      }
    };
    if (readyState === WebSocket.OPEN) {
      sendConfigRequest();

      // 如果还没收到配置，设置一个定时器每5秒重新请求一次
      if (!configReceived) {
        const intervalId = setInterval(() => {
          if (!configReceived) {
            console.log("尚未收到配置，重新发送请求");
            sendConfigRequest();
          } else {
            clearInterval(intervalId);
          }
        }, 5000);

        // 清理函数
        return () => {
          clearInterval(intervalId);
        };
      }
    }
  }, [readyState, configReceived, sendJsonMessage]);

  // 处理收到的消息
  useEffect(() => {
    if (lastMessage) {
      try {
        const message = JSON.parse(lastMessage.data);

        // 检查是否是配置消息
        if (message.type === "system" && message.action === "config" && configReceived === false) {
          console.log("收到配置更新:", message.data);
          updateServerConfig(message.data.config);
          setConfigReceived(true);
          toast.success("配置已更新", {
            position: "bottom-right",
            autoClose: 2000,
            hideProgressBar: false,
            closeOnClick: true,
            pauseOnHover: true,
            draggable: true,
          });
        }
      } catch (error) {
        console.error("解析WebSocket消息出错:", error);
      }
    }
  }, [lastMessage, updateServerConfig, configReceived]);

  // 这个组件不渲染任何内容
  return null;
};

export default WebSocketConfigListener;
