import {Emitter, Event} from '@codingame/monaco-vscode-api/vscode/vs/base/common/event'
import {CancellationError} from '@codingame/monaco-vscode-api/vscode/vs/base/common/errors'
import {URI} from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri'
import {FileChangeType, FileSystemProviderCapabilities, FileSystemProviderErrorCode as Code, createFileSystemProviderError} from '@codingame/monaco-vscode-api/vscode/vs/platform/files/common/files'

const errors = {NotFound:Code.FileNotFound, Exists:Code.FileExists, Denied:Code.NoPermissions, Conflict:Code.FileWriteLocked, Unavailable:Code.Unavailable}
export async function request(action, fields = {}, endpoint = new URL('rpc', document.baseURI), signal) {
  const response = await fetch(endpoint, {
    method:'POST', headers:{'Content-Type':'application/json', 'X-Studio-Request':'1'},
    body:JSON.stringify({action, ...fields}), signal
  })
  const result = await response.json()
  if (!response.ok) throw createFileSystemProviderError(result.error, errors[result.kind] || Code.Unknown)
  return result.result
}

function encode(data) {
  const parts = []
  for (let offset=0; offset<data.length; offset+=8192) {
    parts.push(String.fromCharCode(...data.subarray(offset, offset+8192)))
  }
  return btoa(parts.join(''))
}

export class ProjectFiles {
  constructor(project) {
    this.project = project
    this.root = '/' + project.name
    this.events = new Emitter()
    this.onDidChangeFile = this.events.event
    this.onDidChangeCapabilities = Event.None
    this.capabilities = FileSystemProviderCapabilities.FileReadWrite | FileSystemProviderCapabilities.Trash
    this.revisions = new Map()
    this.requests = new Set()
    this.leaving = false
    this.directories = new Map()
    this.rootWatches = 0
  }
  watch() {
    this.rootWatches++
    this.scheduleWatch()
    return {dispose:() => { this.rootWatches--; this.scheduleWatch() }}
  }
  scheduleWatch() {
    clearTimeout(this.watchTimer)
    if (this.rootWatches && !this.leaving && !document.hidden && !this.polling) {
      this.watchTimer = setTimeout(() => this.refreshFolders(), 1600)
    }
  }
  async refreshFolders() {
    if (this.leaving || this.polling || document.hidden) return
    this.polling = true
    try {
      const folders = [...this.directories]
      for (let offset = 0; offset < folders.length && !this.leaving; offset += 64) {
        const batch = folders.slice(offset, offset + 64)
        const stamps = Object.fromEntries(batch.map(([path, folder]) => [path, folder.stamp]))
        const changes = await this.call('folderChanges', {folders:stamps})
        for (const [path, previous] of batch) {
          const next = Object.hasOwn(changes, path) && changes[path]
          if (!next || this.directories.get(path) !== previous) continue
          if (next.stamp === null) this.directories.delete(path)
          else this.directories.set(path, next)
          const before = new Map(previous.entries), after = new Map(next.entries)
          const events = []
          for (const name of new Set([...before.keys(), ...after.keys()])) {
            if (before.get(name) === after.get(name)) continue
            const type = !after.has(name) ? FileChangeType.DELETED : !before.has(name) ? FileChangeType.ADDED : FileChangeType.UPDATED
            events.push({type, resource:URI.from({scheme:'studio', path:[this.root, path, name].filter(Boolean).join('/')})})
          }
          if (events.length) this.events.fire(events)
        }
      }
    } catch { /* Retry a transient local connection failure on the next visible poll. */ }
    finally { this.polling = false; this.scheduleWatch() }
  }
  relative(uri) {
    if (uri.scheme === 'studio' && uri.path === this.root) return ''
    if (uri.scheme === 'studio' && uri.path.startsWith(this.root + '/')) {
      const path = uri.path.slice(this.root.length + 1)
      if (path.split('/').some(segment => segment.startsWith('.'))) {
        throw createFileSystemProviderError('Hidden project file', Code.FileNotFound)
      }
      return path
    }
    throw createFileSystemProviderError('Outside the selected project', Code.FileNotFound)
  }
  async call(action, fields={}) {
    if (this.leaving) throw new CancellationError()
    const pending = request(action, {project:this.project.key, ...fields})
    this.requests.add(pending)
    try { return await pending }
    finally { this.requests.delete(pending) }
  }
  async leave(action, fields) {
    this.leaving = true
    try {
      await Promise.allSettled([...this.requests])
      return await request(action, {project:this.project.key, ...fields})
    } catch (error) { this.leaving = false; throw error }
  }
  stat(uri) { return this.call('stat', {path:this.relative(uri)}) }
  async readdir(uri) {
    const path = this.relative(uri)
    const listing = await this.call('list', {path, withStamp:true})
    this.directories.set(path, listing)
    return listing.entries
  }
  async readFile(uri) {
    const path = this.relative(uri)
    const result = await this.call('read', {path})
    // A background read must not rebase an editor's unsaved buffer.
    if (!this.revisions.has(path)) this.revisions.set(path, result.revision)
    return Uint8Array.from(atob(result.bytes), ch => ch.charCodeAt(0))
  }
  async writeFile(uri, data, opts) {
    const path = this.relative(uri)
    const revision = opts.create && !opts.overwrite ? undefined : this.revisions.get(path)
    const result = await this.call('write', {path, bytes:encode(data), revision, create:opts.create, overwrite:opts.overwrite})
    this.revisions.set(path, result.revision)
    this.events.fire([{type:revision ? FileChangeType.UPDATED : FileChangeType.ADDED, resource:uri}])
  }
  async mkdir(uri) {
    await this.call('mkdir', {path:this.relative(uri)})
    this.events.fire([{type:FileChangeType.ADDED, resource:uri}])
  }
  async rename(from, to) {
    const oldPath = this.relative(from), newPath = this.relative(to)
    await this.call('rename', {path:oldPath, to:newPath})
    for (const [path, revision] of [...this.revisions]) {
      if (path === oldPath || path.startsWith(oldPath + '/')) {
        this.revisions.delete(path)
        this.revisions.set(newPath + path.slice(oldPath.length), revision)
      }
    }
    this.events.fire([{type:FileChangeType.DELETED, resource:from}, {type:FileChangeType.ADDED, resource:to}])
  }
  async delete(uri) {
    const removed = this.relative(uri)
    await this.call('trash', {path:removed})
    for (const map of [this.revisions, this.directories]) {
      for (const path of map.keys()) {
        if (path === removed || path.startsWith(removed + '/')) map.delete(path)
      }
    }
    this.events.fire([{type:FileChangeType.DELETED, resource:uri}])
  }
}
