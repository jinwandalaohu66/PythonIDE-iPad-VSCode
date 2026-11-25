// Rebuild distribution notices from the same lockfile used to compile the editor.
import {cp, mkdir, readFile, readdir, writeFile} from 'node:fs/promises'
import path from 'node:path'
import {fileURLToPath} from 'node:url'

const client = path.dirname(fileURLToPath(import.meta.url))
const notices = path.join(client, '../licenses')
const out = path.join(notices, 'npm')
await mkdir(out, {recursive:true})
const lock = JSON.parse(await readFile(path.join(client, 'package-lock.json'), 'utf8'))
const lines = ['Production dependency inventory', 'Built from client/package-lock.json.', '']
for (const [relative, entry] of Object.entries(lock.packages)) {
  if (!relative || entry.dev) continue
  const directory = path.join(client, relative)
  const pkg = JSON.parse(await readFile(path.join(directory, 'package.json'), 'utf8'))
  lines.push([pkg.name, pkg.version, pkg.license, entry.resolved].join('  '))
  const names = await readdir(directory)
  for (const name of names.filter(n => /^(licen[sc]e|notice|copying|contributors)(\.|-|$)/i.test(n))) {
    await cp(path.join(directory, name), path.join(out, pkg.name.replace(/\//g, '_') + '-' + name))
  }
  if (pkg.name === 'jschardet') {
    const source = path.join(out, 'jschardet-source')
    await mkdir(source, {recursive:true})
    for (const name of ['src','index.js','package.json','LICENSE','CONTRIBUTORS']) {
      await cp(path.join(directory,name), path.join(source,name), {recursive:true})
    }
  }
}
await writeFile(path.join(notices,'npm-inventory.txt'), lines.join('\n') + '\n')
