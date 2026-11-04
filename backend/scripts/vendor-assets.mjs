// Copy only the production ESM graph and licenses, never development bundles.
import { copyFile, mkdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { resolve } from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const destination = resolve(root, 'static/vendor');
for (const [packageName, folder, files] of [
  ['maplibre-gl', 'maplibre', [
    'dist/maplibre-gl.mjs', 'dist/maplibre-gl-shared.mjs',
    'dist/maplibre-gl-worker.mjs', 'dist/maplibre-gl.css', 'LICENSE.txt'
  ]],
  ['@maplibre/maplibre-gl-leaflet', 'maplibre-leaflet', [
    'leaflet-maplibre-gl.js', 'LICENSE'
  ]]
]) {
  const target = resolve(destination, folder);
  await mkdir(target, { recursive: true });
  for (const file of files) {
    await copyFile(resolve(root, 'node_modules', packageName, file),
      resolve(target, file.split('/').at(-1)));
  }
}
