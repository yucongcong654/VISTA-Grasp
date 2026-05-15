import React, { useEffect } from "react";
import { useXR } from "@react-three/xr";

interface XRSessionListenerProps {
  children: (isPresenting: boolean) => React.ReactNode;
}

const XRSessionListener: React.FC<XRSessionListenerProps> = ({ children }) => {
  const { session } = useXR();
  // 根据 session 判断是否进入 XR 模式
  const isPresenting = Boolean(session);

  useEffect(() => {
    if (isPresenting) {
      console.log("XR session started");
    } else {
      console.log("XR session ended");
    }
  }, [isPresenting]);

  return <>{children(isPresenting)}</>;
};

export default XRSessionListener;
