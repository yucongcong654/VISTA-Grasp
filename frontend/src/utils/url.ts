const parsePort = (value: string | undefined, fallback: number): number => {
  const port = Number(value);
  return Number.isInteger(port) && port > 0 && port < 65536 ? port : fallback;
};

const normalizeProtocol = (protocol: string | undefined, fallback: string): string => {
  if (!protocol) {
    return fallback;
  }
  return protocol.endsWith(':') ? protocol : `${protocol}:`;
};

const DEFAULT_WEBSOCKET_PORT = parsePort(import.meta.env.VITE_TELEOP_WS_PORT, 5174);

export const getWebSocketUrl = (customPath?: string, port?: number): string => {
  const location = window.location;
  const protocol = normalizeProtocol(
    import.meta.env.VITE_TELEOP_WS_PROTOCOL,
    location.protocol === 'https:' ? 'wss:' : 'ws:'
  );
  const hostname = import.meta.env.VITE_TELEOP_WS_HOST || location.hostname;
  const finalPort = port !== undefined ? port : DEFAULT_WEBSOCKET_PORT;
  const hostWithPort = finalPort ? `${hostname}:${finalPort}` : hostname;

  const path = customPath ? 
    (customPath.startsWith('/') ? customPath : `/${customPath}`) : 
    '';

  return `${protocol}//${hostWithPort}${path}`;
};

export const getCurrentWebPort = (): number => DEFAULT_WEBSOCKET_PORT;
