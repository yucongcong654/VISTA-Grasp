import { useRef, useMemo } from 'react';
import { useThree, useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useWebRTCVideoTexture } from '../utils/useWebRTCVideoPlayer';
import { getWebSocketUrl } from "../utils/url";
import { useConfigStore } from '../utils/configStore';

interface VideosContainersProps {
  width?: number;
  height?: number;
  distance?: number;
  position?: [number, number, number];
  rotation?: [number, number, number];
  fixedToCamera?: boolean;
  numSmallVideos?: number,
}

export default function VideosContainers({
  width: widthProp,
  height: heightProp,
  distance: distanceProp,
  position: positionProp,
  rotation: rotationProp,
  numSmallVideos: numSmallVideosProp,
  fixedToCamera = true
}: VideosContainersProps) {
  const groupRef = useRef<THREE.Group>(null);
  const { camera } = useThree();

  // Config
  const configRemote = useConfigStore((state) => state.configRemote);
  const containerConfig = configRemote?.video_container_cfg;
  const width = widthProp || containerConfig?.width || 2;
  const height = heightProp || containerConfig?.height || 0.9;
  const distance = distanceProp || containerConfig?.distance || 2;
  const numSmallVideos = numSmallVideosProp || containerConfig?.numSmallVideos || 3;
  const websocketPort = useConfigStore((state) => state.configLocal.websocketPort);
  const websocketUrl = useMemo(() => getWebSocketUrl('', websocketPort), [websocketPort]);
  const streamIds = containerConfig?.streamIds || [containerConfig?.streamId || "camera0", "camera1"];
  const mainStreamId = streamIds[0] || "camera0";
  const smallStreamIds = streamIds.slice(1, numSmallVideos + 1);

  // 默认纹理
  const mainTexture = useMemo(() => makeTextTexture("少女祈祷中...", 256, 64), []);
  const { videoTexture, isReady, latencyMs } = useWebRTCVideoTexture(
    mainStreamId,
    websocketUrl
  );
  // 延迟贴图
  const latencyTexture = useMemo(() => {
    if (latencyMs == null) return null;
    // 可根据需要调整画布大小
    return makeTextTexture(`${latencyMs.toFixed(1)} ms`, 256, 64);
  }, [latencyMs]);

  const smallVideoHeight = 0.2;
  const spacing = 0.02;
  

  useFrame(() => {
    if (groupRef.current && fixedToCamera) {
      if (positionProp && rotationProp) {
        groupRef.current.position.set(...positionProp);
        groupRef.current.rotation.set(...rotationProp);
      } else {
        const direction = new THREE.Vector3(0, 0, -1).applyQuaternion(camera.quaternion);
        const targetPos = new THREE.Vector3()
          .copy(camera.position)
          .add(direction.multiplyScalar(distance));
        groupRef.current.position.copy(targetPos);
        groupRef.current.quaternion.copy(camera.quaternion);
      }
    }
  });

  return (
    <group ref={groupRef}>
      {/* 整体背景容器 */}
      <mesh position={[0, 0, 0]}>
        <planeGeometry args={[width, height]} />
        <meshBasicMaterial color="white" transparent opacity={0.05} />
      </mesh>

      {/* 主视频区 */}
      <mesh position={[-0.2, 0, 0]}>
        <planeGeometry args={[1.6, height]} />
        <meshBasicMaterial
          map={isReady && videoTexture ? videoTexture : mainTexture}
          transparent
        />
      </mesh>

      {/* 网络延迟文字平面 */}
      {latencyTexture && (
        <mesh position={[0.875, 0.5, 0]}>
          <planeGeometry args={[0.25, 0.0625]} />
          <meshBasicMaterial map={latencyTexture} transparent />
        </mesh>
      )}

      {/* 小视频区 */}
      <group position={[0.8, 0, 0]}>
        <mesh position={[0, 0, 0]}>
          <planeGeometry args={[0.4, height]} />
          <meshBasicMaterial color="white" transparent opacity={0.1} />
        </mesh>
        <group>
          {smallStreamIds.map((streamId, i) => {
            const totalVideoHeight = numSmallVideos * smallVideoHeight + (numSmallVideos - 1) * spacing;
            const baseOffset = totalVideoHeight / 2;
            return (
              <SmallVideoPlane
                key={streamId}
                streamId={streamId}
                websocketUrl={websocketUrl}
                fallbackTexture={mainTexture}
                position={[0, baseOffset - i * (smallVideoHeight + spacing) - smallVideoHeight / 2, 0]}
                height={smallVideoHeight}
              />
            );
          })}
        </group>
      </group>
    </group>
  );
}

function SmallVideoPlane({
  streamId,
  websocketUrl,
  fallbackTexture,
  position,
  height,
}: {
  streamId: string;
  websocketUrl: string;
  fallbackTexture: THREE.Texture;
  position: [number, number, number];
  height: number;
}) {
  const { videoTexture, isReady } = useWebRTCVideoTexture(streamId, websocketUrl);

  return (
    <mesh position={position}>
      <planeGeometry args={[0.36, height]} />
      <meshBasicMaterial
        map={isReady && videoTexture ? videoTexture : fallbackTexture}
        transparent
      />
    </mesh>
  );
}

// 创建文字贴图函数
function makeTextTexture(text: string, width = 512, height = 256): THREE.Texture {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;
  // 背景
  ctx.fillStyle = 'rgba(0,0,0,0.6)';
  ctx.fillRect(0, 0, width, height);
  // 文字
  ctx.fillStyle = 'white';
  ctx.font = `${height * 0.6}px sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, width / 2, height / 2);
  const tex = new THREE.CanvasTexture(canvas);
  tex.minFilter = THREE.LinearFilter;
  tex.magFilter = THREE.LinearFilter;
  return tex;
}
