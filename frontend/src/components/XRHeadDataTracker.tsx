import { useCallback, useState, useMemo ,useEffect, useRef } from 'react';
import { useXR } from '@react-three/xr';
import * as THREE from 'three';
import { useThree } from '@react-three/fiber';
import useWebSocket from "react-use-websocket";
import { getWebSocketUrl } from "../utils/url";
import { useConfigStore } from '../utils/configStore';
import { toast } from 'react-toastify';

interface XRHeadDataTrackerProps {
  fps?: number; // 可选参数，默认值在组件中设置
  positionThreshold?: number; // 位置变化阈值，默认值为0.0001 (1e-4)
  rotationThreshold?: number; // 旋转变化阈值，默认值为0.0001 (1e-4)
  onStatusChange?: (status: boolean) => void; // New prop for status reporting
}

const XRHeadDataTracker = ({ onStatusChange }: XRHeadDataTrackerProps) => {
  // Get configuration from Zustand store
  const configLocal = useConfigStore((state) => state.configLocal);
  const configRemote = useConfigStore((state) => state.configRemote); 
  
  // Use default values if config is not found
  const fallbackConfig = {
    fps: 1,
    positionThreshold: 0.0001,
    rotationThreshold: 0.0001
  };
  
  // Track component status
  const [isReady, setIsReady] = useState(false);
  
  // Show error toast if config is missing
  useEffect(() => {
    if (!configRemote) {
      toast.error('头部追踪配置未找到, 请检查', {
        position: "bottom-left",
        autoClose: 5000,
        hideProgressBar: false,
        closeOnClick: true,
        pauseOnHover: true,
        draggable: true,
      });
    } else {
      setIsReady(true);
    }
  }, [configRemote]);
  
  // Report status changes
  useEffect(() => {
    if (onStatusChange) {
      onStatusChange(isReady);
    }
  }, [isReady, onStatusChange]);
  
  // Use props if provided, otherwise use the ones from config or fallback
  const fps = configRemote?.head_track_cfg?.fps || fallbackConfig.fps;
  const positionThreshold = configRemote?.head_track_cfg?.positionThreshold || fallbackConfig.positionThreshold;
  const rotationThreshold = configRemote?.head_track_cfg?.rotationThreshold || fallbackConfig.rotationThreshold;
  const websocketPort = configLocal.websocketPort;
  
  const session = useXR().session;
  const { camera } = useThree();
  const websocketUrl = useMemo( () => getWebSocketUrl("", websocketPort), [websocketPort]);
  const { sendMessage, readyState } = useWebSocket(websocketUrl, {
    share: true,
    onOpen: () => {
      console.log('WebSocket connection established for head tracker');
      setIsReady(true);
    },
    onError: () => {
      console.error('WebSocket connection error for head tracker');
      setIsReady(false);
      toast.error('头部追踪WebSocket连接失败');
    },
    onClose: () => {
      console.log('WebSocket connection closed for head tracker');
      setIsReady(false);
    },
    shouldReconnect: () => configLocal.shouldReconnect,
    reconnectInterval: configLocal.reconnectInterval,
    reconnectAttempts: configLocal.reconnectAttempts
  });
  
  // 使用 ref 存储上一次发送的头部数据
  const lastSentData = useRef({
    position: new THREE.Vector3(),
    rotation: new THREE.Quaternion()
  });
  
  // 检查数据是否有显著变化
  const hasSignificantChange = useCallback((
    newPosition: THREE.Vector3, 
    newRotation: THREE.Quaternion
  ) => {
    // 检查位置变化
    if (positionThreshold && lastSentData.current.position.distanceTo(newPosition) > positionThreshold) {
      return true;
    }
    
    // 检查旋转变化 - 使用四元数的点积计算角度差异
    const dotProduct = lastSentData.current.rotation.dot(newRotation);
    // 四元数点积接近1表示方向相似，我们检查它是否小于阈值
    if (rotationThreshold && Math.abs(1 - dotProduct) > rotationThreshold) {
      return true;
    }
    
    return false;
  }, [positionThreshold, rotationThreshold]);
  
  // 降低数值精度的函数
  const reducePrecision = useCallback((value: number) => {
    return parseFloat(value.toFixed(4));
  }, []);
  
  // 发送头部数据的函数
  const sendHeadData = useCallback(() => {
    if (readyState === WebSocket.OPEN && session) {
      try {
        const viewerPose = camera.getWorldPosition(new THREE.Vector3());
        const viewerRotation = camera.getWorldQuaternion(new THREE.Quaternion());
        
        // 检查是否有显著变化
        if (hasSignificantChange(viewerPose, viewerRotation)) {
          // 降低精度
          const precisionReducedPosition = {
            x: reducePrecision(viewerPose.x),
            y: reducePrecision(viewerPose.y),
            z: reducePrecision(viewerPose.z)
          };
          
          const precisionReducedRotation = {
            x: reducePrecision(viewerRotation.x),
            y: reducePrecision(viewerRotation.y),
            z: reducePrecision(viewerRotation.z),
            w: reducePrecision(viewerRotation.w)
          };
          
          const headData = {
            position: precisionReducedPosition,
            rotation: precisionReducedRotation
          };
          
          const message = {
            type: 'head_move',
            timestamp: Date.now(),
            data: headData
          };
          
          sendMessage(JSON.stringify(message));
          console.debug('发送头部位姿:', message);
          
          // 更新上一次发送的数据
          lastSentData.current.position.copy(viewerPose);
          lastSentData.current.rotation.copy(viewerRotation);
        } else {
          console.debug('头部位姿变化不大，跳过发送');
        }
      } catch (error) {
        console.error('获取头部位姿失败:', error);
        toast.error('获取头部位姿失败');
        setIsReady(false);
      }
    } else if(readyState !== WebSocket.OPEN) {
      console.error('WebSocket 连接未打开', websocketUrl);
    } else if(!session) {
      console.error('XR 会话未创建');
    }
  }, [readyState, session, camera, sendMessage, websocketUrl, hasSignificantChange, reducePrecision]);

  useEffect(() => {
    // 计算发送间隔时间（毫秒）
    const interval = Math.floor(1000 / fps);
    
    // 设置定时器
    const timer = setInterval(sendHeadData, interval);
    
    // 清理函数
    return () => {
      clearInterval(timer);
    };
  }, [fps, sendHeadData]);

  // 这个组件不渲染任何内容
  return null;
};

export default XRHeadDataTracker;