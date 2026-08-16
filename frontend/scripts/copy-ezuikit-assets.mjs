import { copyFile, mkdir } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const packageDist = resolve(frontendRoot, 'node_modules/@ezuikit/player-hls/dist')
const targetDir = resolve(frontendRoot, 'public/ezuikit-hls')

await mkdir(targetDir, { recursive: true })
await Promise.all(
  ['decoder.wasm', 'decoder.worker.js'].map((name) =>
    copyFile(resolve(packageDist, name), resolve(targetDir, name)),
  ),
)
