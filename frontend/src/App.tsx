import { Canvas } from "@react-three/fiber";
import { XR, createXRStore } from "@react-three/xr";
import XRHeadDataTracker from "./components/XRHeadDataTracker";
import XRControllerDataTracker from "./components/XRControllerDataTracker";
import WebSocketConfigListener from "./components/WebSocketConfigListener";
import ConfigStatusDisplay from "./components/plainUI/ConfigStatusDisplay";
import { useConfigStore } from "./utils/configStore";
import { ToastContainer } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import "./App.css";
import XRSessionListener from "./components/XRSessionListener";
import VideosContainers from "./components/VideosContainers";

// 创建 XR 的 store
const store = createXRStore();

function App() {
  const configRemote = useConfigStore((state) => state.configRemote);

  return (
    <>
      <ToastContainer />
      <WebSocketConfigListener />
      <>
        <ConfigStatusDisplay xrStore={store} />
        {configRemote && (
          <Canvas>
            <XR store={store}>
              <XRHeadDataTracker />
              <XRControllerDataTracker handness="left" />
              <XRControllerDataTracker handness="right" />
              <XRSessionListener>
                {(isPresenting) =>
                  isPresenting ? (
                    <VideosContainers />
                  ) : null
                }
              </XRSessionListener>
            </XR>
          </Canvas>
        )}
      </>
    </>
  );
}

export default App;
