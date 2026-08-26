import { cp, mkdir, rm } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const packageStatic = resolve(frontendRoot, 'node_modules/ezuikit-js/ezuikit_static')
const targetDir = resolve(frontendRoot, 'public/ezuikit_static')

await rm(targetDir, { recursive: true, force: true })
await mkdir(targetDir, { recursive: true })
await cp(packageStatic, targetDir, { recursive: true })
