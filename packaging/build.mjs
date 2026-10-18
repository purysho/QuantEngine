import { build } from 'esbuild';
import { mkdir, stat } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
await mkdir(path.join(root, 'dist'), { recursive: true });
await Promise.all([
  build({ entryPoints: [path.join(root, 'desktop/main.ts')], outfile: path.join(root, 'dist/main.cjs'),
    bundle: true, platform: 'node', format: 'cjs', target: 'node22', external: ['electron'], sourcemap: false }),
  build({ entryPoints: [path.join(root, 'desktop/preload.ts')], outfile: path.join(root, 'dist/preload.cjs'),
    bundle: true, platform: 'node', format: 'cjs', target: 'node22', external: ['electron'], sourcemap: false }),
  build({ entryPoints: [path.join(root, 'app/ui-source.js')], outfile: path.join(root, 'app/ui.js'),
    bundle: true, platform: 'browser', format: 'iife', target: 'chrome140', sourcemap: false }),
  // The terminal (with TradingView Lightweight Charts) is a separate script exposing window.QuantTerminal.
  build({ entryPoints: [path.join(root, 'app/terminal.js')], outfile: path.join(root, 'app/terminal.bundle.js'),
    bundle: true, platform: 'browser', format: 'iife', globalName: 'QuantTerminal', target: 'chrome140', sourcemap: false, minify: true,
    legalComments: 'eof' }),
]);
for (const relative of ['dist/main.cjs', 'dist/preload.cjs', 'app/ui.js', 'app/terminal.bundle.js', 'workers/quant_worker.py']) {
  console.log(relative + ': ' + (await stat(path.join(root, relative))).size + ' bytes');
}
