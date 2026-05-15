import React, { useMemo, useState, useEffect } from "react";
import { XRStore } from "@react-three/xr";
import { getWebSocketUrl } from "../../utils/url";
import {
  useConfigStore,
  TeleopLocalConfig,
  TeleopRemoteConfig,
} from "../../utils/configStore";
import "./ConfigStatusDisplay.css";
// 导入背景图片
import defaultBackground from "../../assets/configpic.png";
import useWebSocket, {
  ReadyState as WebSocketReadyState,
} from "react-use-websocket";

// Props for the ConfigStatusDisplay component
interface ConfigStatusDisplayProps {
  xrStore?: XRStore;
  backgroundImage?: string;
  // 添加位置控制属性
  position?: {
    x: "left" | "center" | "right";
    y: "top" | "center" | "bottom";
  };
  width?: number;
  height?: number;
}

// 状态行组件
const StatusRow = ({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) => (
  <div className="status-row">
    <div className="status-label">{label}</div>
    <div className="status-value">{value}</div>
  </div>
);

// WebSocket端口编辑组件
const WebSocketPortEditor = ({
  port,
  isEditing,
  setIsEditing,
  onSave,
}: {
  port: number;
  isEditing: boolean;
  setIsEditing: (value: boolean) => void;
  onSave: (port: number) => void;
}) => {
  const [newPort, setNewPort] = useState<string>(port.toString());

  const handlePortChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setNewPort(e.target.value);
  };

  const handleSubmit = () => {
    const portValue = parseInt(newPort, 10);
    if (!isNaN(portValue) && portValue > 0 && portValue < 65536) {
      onSave(portValue);
      setIsEditing(false);
    } else {
      alert("请输入有效的端口号 (1-65535)");
    }
  };

  if (isEditing) {
    return (
      <div className="status-value edit-mode">
        <input
          type="number"
          value={newPort}
          onChange={handlePortChange}
          min="1"
          max="65535"
          className="port-input"
        />
        <button onClick={handleSubmit} className="port-save-button">
          保存
        </button>
        <button
          onClick={() => {
            setIsEditing(false);
            setNewPort(port.toString());
          }}
          className="port-cancel-button"
        >
          取消
        </button>
      </div>
    );
  }

  return (
    <div className="status-value">
      {port}
      <button onClick={() => setIsEditing(true)} className="port-edit-button">
        修改
      </button>
    </div>
  );
};

// 配置信息区块组件
const ServerConfigSection = ({
  configRemote, 
  // updateRemoteConfig, // 这是SetMode组件 暂时用不到
}: {
  configRemote: TeleopRemoteConfig | undefined;
  // updateRemoteConfig: (mode: string) => void;  // 这是SetMode组件 暂时用不到
}) => {
  // 这是SetMode组件 暂时用不到
  // const handleModeChange = () => {
  //   const newMode = configRemote?.mode === "controller_mode" ? "hand_mode" : "controller_mode";
  //   updateRemoteConfig(newMode); // 发送 WebSocket 请求切换模式
  // };  
  return (
    <div className="config-section">
      <h4 className="section-title">服务器配置</h4>
      {/* 这是模式显示 */}
      <StatusRow label="当前模式:" value={configRemote?.mode || "未设置"} />
      {/* 这是SetMode组件 暂时用不到 */}
      {/* <div className="status-row">
        <div className="status-label">当前模式:</div>
        <div
          className="status-value"
          onClick={handleModeChange}
          style={{ cursor: "pointer", color: "#007bff" }}
        >
          {configRemote?.mode || "未设置"}
        </div>
      </div> */}
      <StatusRow
        label="头部追踪FPS:"
        value={configRemote?.head_track_cfg?.fps || "未设置"}
      />
      <StatusRow
        label="手部追踪FPS:"
        value={configRemote?.hand_track_cfg?.fps || "未设置"}
      />
      <StatusRow
        label="控制器追踪FPS:"
        value={configRemote?.controller_track_cfg?.fps || "未设置"}
      />
    </div>
  );
};

// 本地配置区块组件
const LocalConfigSection = ({
  configLocal,
  webSocketReadyState,
  updateLocalConfig,
}: {
  configLocal: TeleopLocalConfig;
  webSocketReadyState: WebSocketReadyState;
  updateLocalConfig: (partialConfig: Partial<TeleopLocalConfig>) => void;
}) => {
  const [isEditing, setIsEditing] = useState<boolean>(false);
  return (
    <div className="config-section">
      <h4 className="section-title">本地配置</h4>
      <StatusRow
        label="WebSocket 状态"
        value={
          webSocketReadyState === WebSocketReadyState.OPEN ? "已连接" : "未连接"
        }
      />
      <div className="status-row websocket-row">
        <div className="status-label">WebSocket 端口:</div>
        <WebSocketPortEditor
          port={configLocal.websocketPort}
          isEditing={isEditing}
          setIsEditing={setIsEditing}
          onSave={(port) => updateLocalConfig({ websocketPort: port })}
        />
      </div>
    </div>
  );
};

// 进入AR按钮组件
const EnterARButton = ({
  xrStore,
  disabled,
}: {
  xrStore?: XRStore;
  disabled: boolean;
}) => {
  // 添加计时器状态
  const [waitTime, setWaitTime] = useState<number>(0);

  // 如果按钮被禁用，启动计时器
  useEffect(() => {
    let timerId: number | undefined;

    if (disabled) {
      // 重置计时器
      setWaitTime(0);

      // 每秒更新一次计时器
      timerId = window.setInterval(() => {
        setWaitTime((prevTime) => prevTime + 1);
      }, 1000);
    } else {
      // 如果不再禁用，清除计时器
      setWaitTime(0);
    }

    // 清理函数
    return () => {
      if (timerId !== undefined) {
        clearInterval(timerId);
      }
    };
  }, [disabled]);

  return (
    <div className="config-section enter-ar-section">
      <button
        onClick={() => xrStore && xrStore.enterAR()}
        className={`enter-ar-button ${disabled ? "disabled" : ""}`}
        disabled={disabled}
      >
        {disabled ? `等待配置加载... ${waitTime}s` : "进入AR"}
      </button>
    </div>
  );
};


// 这是SetMode组件 暂时用不到
// // 更新模式的函数
// const updateRemoteConfig = (sendJsonMessage: any, newMode: string) => {
//   const message = {
//     type: "set_mode",  // WebSocket 命令类型
//     mode: newMode,     // 需要切换的模式
//     timestamp: Date.now()
//   };

//   // 发送 WebSocket 消息
//   sendJsonMessage(message);
// };


const ConfigStatusDisplay = ({
  xrStore,
  backgroundImage = defaultBackground,
  position = { x: "right", y: "center" },
  width = 800,
  height = 450,
}: ConfigStatusDisplayProps) => {
  const configLocal = useConfigStore((state) => state.configLocal);
  const configRemote = useConfigStore((state) => state.configRemote);
  const websocketPort = useConfigStore(
    (state) => state.configLocal.websocketPort
  );
  const websocketUrl = useMemo(
    () => getWebSocketUrl("", websocketPort),
    [websocketPort]
  );
  // sendJsonMessage是SetMode组件 暂时用不到
  // const { readyState, sendJsonMessage } = useWebSocket(websocketUrl, {
  const { readyState } = useWebSocket(websocketUrl, {
    share: true,
    shouldReconnect: () => configLocal.shouldReconnect,
    reconnectInterval: configLocal.reconnectInterval,
    reconnectAttempts: configLocal.reconnectAttempts,
  });
  // 这是SetMode组件 暂时用不到
  // const handleUpdateRemoteConfig = (newMode: string) => {
  //   updateRemoteConfig(sendJsonMessage, newMode);
  // };

  const updateLocalConfig = useConfigStore((state) => state.updateLocalConfig);

  // 判断按钮是否禁用
  const isButtonDisabled = !configRemote || !configRemote.mode;

  // 创建外层容器样式 - 这个容器将包含完整的背景图
  const containerStyle = {
    position: "relative" as const,
    width: `${width}px`,
    height: `${height}px`,
    overflow: "hidden",
  };

  // 创建背景图层样式
  const backgroundStyle = {
    position: "absolute" as const,
    width: "100%",
    height: "100%",
    backgroundImage: `url(${backgroundImage})`,
    backgroundSize: "contain",
    backgroundPosition: "center",
    backgroundRepeat: "no-repeat",
    zIndex: 1,
  };

  // 创建内容层样式 - 这个层将包含实际组件内容
  const contentStyle = {
    position: "absolute" as const,
    zIndex: 2,
    // 水平位置
    ...(position.x === "left"
      ? { left: "20px" }
      : position.x === "right"
      ? { right: "20px" }
      : { left: "50%", transform: "translateX(-50%)" }),
    // 垂直位置
    ...(position.y === "top"
      ? { top: "20px" }
      : position.y === "bottom"
      ? { bottom: "20px" }
      : {
          top: "50%",
          transform: `${
            position.x === "center"
              ? "translate(-50%, -50%)"
              : "translateY(-50%)"
          }`,
        }),
    maxWidth: "400px",
    width: "400px",
  };

  return (
    <div className="config-status-outer-container" style={containerStyle}>
      <div className="config-status-background" style={backgroundStyle}></div>

      <div className="config-status-content" style={contentStyle}>
        <div className="config-status-container">
          <div className="overlay">
            <h4 className="config-title">系统状态</h4>

            <ServerConfigSection configRemote={configRemote} />
            {/* 这是SetMode组件 暂时用不到 */}
            {/* <ServerConfigSection 
              configRemote={configRemote}
              updateRemoteConfig={handleUpdateRemoteConfig}
            /> */}
            <LocalConfigSection
              configLocal={configLocal}
              updateLocalConfig={updateLocalConfig}
              webSocketReadyState={readyState}
            />

            <EnterARButton xrStore={xrStore} disabled={isButtonDisabled} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConfigStatusDisplay;
