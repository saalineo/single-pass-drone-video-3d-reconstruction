import { ImageryLayer } from 'resium';
import { UrlTemplateImageryProvider, SingleTileImageryProvider } from 'cesium';

export function CoverageRasterLayer({
  url,
  format,
  visible,
}: {
  url: string;
  format: 'png-tiles' | 'cog-preview';
  visible: boolean;
}) {
  const provider =
    format === 'png-tiles'
      ? new UrlTemplateImageryProvider({ url: `${url}/{z}/{x}/{y}.png` })
      : new SingleTileImageryProvider({ url });
  return <ImageryLayer imageryProvider={provider} alpha={visible ? 0.6 : 0} />;
}
