// XRControllerDataTracker.jsx
import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import * as THREE from "three";
import { useXR } from "@react-three/xr";
import { useXRInputSourceState } from "@react-three/xr";
import useWebSocket from "react-use-websocket";
import { getWebSocketUrl } from "../utils/url";
import { useFrame } from "@react-three/fiber";
// import { toast } from "react-toastify";
import { useConfigStore } from "../utils/configStore";

export type ControllerData = {
  position?: THREE.Vector3; // Made optional with ?
  rotation?: THREE.Quaternion; // Made optional with ?
  state: ControllerStateType;
};

export type ControllerStateType = {
  trigger: boolean;
  squeeze: boolean;
  touchpad: boolean;
  thumbstick: boolean;
  aButton: boolean;
  bButton: boolean;

  triggerValue: number;
  squeezeValue: number;
  touchpadValue: [number, number]; // X and Y values for the touchpad
  thumbstickValue: [number, number]; // X and Y values for the thumbstick
  aButtonValue: boolean;
  bButtonValue: boolean;
};

interface XRControllerDataTrackerProps {
  handness: "left" | "right";
  fps?: number;
  onStatusChange?: (status: boolean) => void; // New prop for status reporting
}

type StatusChecks = {
  configLoaded: boolean;
  websocketConnected: boolean;
  controllerConnected: boolean;
};

const XRControllerDataTracker = ({
  handness = "left",
  onStatusChange,
}: XRControllerDataTrackerProps) => {
  // Get configuration from Zustand store
  const configFps = useConfigStore(
    (state) => state.configRemote?.controller_track_cfg?.fps
  );
  const configLocal = useConfigStore((state) => state.configLocal);
  const websocketPort = useConfigStore(
    (state) => state.configLocal.websocketPort
  );

  // Use props fps if provided, otherwise use the one from config
  const fps = configFps || 50;

  const session = useXR().session;
  const websocketUrl = useMemo(
    () => getWebSocketUrl("", websocketPort),
    [websocketPort]
  );
  const { sendMessage, readyState } = useWebSocket(websocketUrl, {
    share: true,
    shouldReconnect: () => configLocal.shouldReconnect,
    reconnectInterval: configLocal.reconnectInterval,
    reconnectAttempts: configLocal.reconnectAttempts
  });
  const controllerState = useXRInputSourceState("controller", handness);
  // 上次发送状态的时间戳
  const lastSendTimeRef = useRef(0);

  // 发送间隔 (毫秒)
  const sendInterval = (1 / fps) * 1000;
  // Track individual status checks

  const [, setStatusChecks] = useState<StatusChecks>({
    configLoaded: !!configFps,
    websocketConnected: false,
    controllerConnected: false,
  });

  // Function to validate and update overall status
  const validateStatus = useCallback(() => {
    // Update individual status checks
    const newStatusChecks: StatusChecks = {
      configLoaded: !!configFps,
      websocketConnected: readyState === WebSocket.OPEN,
      controllerConnected: !!controllerState,
    };

    setStatusChecks(newStatusChecks);

    // Calculate overall status
    const isValid = Object.values(newStatusChecks).every(
      (status) => status === true
    );

    // Report status change if callback provided
    if (onStatusChange) {
      onStatusChange(isValid);
    }

    // Log status for debugging
    console.debug(
      `${handness} controller status:`,
      newStatusChecks,
      "Overall:",
      isValid
    );

    return isValid;
  }, [configFps, readyState, controllerState, handness, onStatusChange]);
  // Check status when dependencies change

  useEffect(() => {
    validateStatus();
  }, [configFps, readyState, controllerState, validateStatus]);

  //TODO
  // Periodically check controller connection 出了问题 需要修改 
  // useEffect(() => {
  //   const intervalId = setInterval(() => {
  //     const isValid = validateStatus();

  //     // Show toast notification when controller becomes ready
  //     if (isValid && statusChecks.controllerConnected && controllerState) {
  //       toast.success(`${handness} 控制器已连接`, {
  //         position: "bottom-right",
  //         autoClose: 2000,
  //       });
  //     }

  //     // Show toast notification when controller disconnects
  //     if (!statusChecks.controllerConnected && !controllerState) {
  //       toast.error(`${handness} 控制器已断开连接`, {
  //         position: "bottom-right",
  //         autoClose: 2000,
  //       });
  //     }
  //   }, 1000);

  //   return () => clearInterval(intervalId);
  // }, [validateStatus, statusChecks, controllerState, handness]);

  // 发送控制器数据的函数
  const sendControllerData = useCallback(
    (data: ControllerData) => {
      if (readyState === WebSocket.OPEN && session) {
        try {
          const message = {
            type: `${handness}_controller`,
            timestamp: Date.now(),
            data,
          };
          console.debug("发送控制器数据:", message);
          sendMessage(JSON.stringify(message));
        } catch (error) {
          console.error("获取控制器数据失败:", error);
        }
      }
    },
    [readyState, session, handness, sendMessage]
  );

  useFrame(() => {
    const currTime = performance.now();
    if (currTime - lastSendTimeRef.current < sendInterval) {
      return;
    }

    // Skip if controller not available
    if (!session || !controllerState || !controllerState) {
      return;
    }
    // Initialize with default values - only include state initially
    const controllerData: ControllerData = {
      state: {
        trigger: false,
        squeeze: false,
        touchpad: false,
        thumbstick: false,
        aButton: false,
        bButton: false,

        triggerValue: 0,
        squeezeValue: 0,
        touchpadValue: [0, 0],
        thumbstickValue: [0, 0],
        aButtonValue: false,
        bButtonValue: false,
      },
    };

    // Get position and rotation from controller if available
    if (controllerState.object) {
      const position = controllerState.object.getWorldPosition(
        new THREE.Vector3()
      );
      const rotation = controllerState.object.getWorldQuaternion(
        new THREE.Quaternion()
      );
      // Only add position and rotation if they are valid
      controllerData.position = position;
      controllerData.rotation = rotation;
    }

    // Get button states and axis values if gamepad is available
    if (controllerState?.inputSource?.gamepad) {
      const gamepad = controllerState.inputSource.gamepad;
      const buttons = gamepad.buttons;
      const axes = gamepad.axes;

      // Apply deadzone to thumbstick values
      const deadzone = 0.15;
      const [, , thumbX = 0, thumbY = 0] = axes;
      const actualX = Math.abs(thumbX) > deadzone ? thumbX : 0;
      const actualY = Math.abs(thumbY) > deadzone ? thumbY : 0;

      // Update state values based on gamepad data
      controllerData.state = {
        // Button pressed states
        trigger: buttons[0]?.pressed || false,
        squeeze: buttons[1]?.pressed || false,
        touchpad: buttons[2]?.pressed || false,
        thumbstick: buttons[3]?.pressed || false,
        aButton: buttons[4]?.pressed || false,
        bButton: buttons[5]?.pressed || false,

        // Button values
        triggerValue: buttons[0]?.value || 0,
        squeezeValue: buttons[1]?.value || 0,
        touchpadValue: [axes[0] || 0, axes[1] || 0],
        thumbstickValue: [actualX, actualY],
        aButtonValue: buttons[4]?.pressed || false,
        bButtonValue: buttons[5]?.pressed || false,
      };
    }
    // Send the controller data
    sendControllerData(controllerData);

    lastSendTimeRef.current = currTime;
  });

  // 这个组件不渲染任何内容
  return null;
};

export default XRControllerDataTracker;
