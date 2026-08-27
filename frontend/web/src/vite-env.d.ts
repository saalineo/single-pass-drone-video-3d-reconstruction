/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_WS_BASE_URL?: string;
  readonly VITE_CESIUM_ION_TOKEN?: string;
  readonly VITE_GLTF_DRACO_DECODER_PATH?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
