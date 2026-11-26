import {CancellationError} from '@codingame/monaco-vscode-api/vscode/vs/base/common/errors'
import {URI} from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri'
import Worker from './search-worker.js?worker'

export class ProjectSearch {
  constructor(project) { this.project = project }
  fileSearch(query, token) { return this.search(query, undefined, token) }
  textSearch(query, progress, token) { return this.search(query, progress, token) }
  clearCache() { return Promise.resolve() }
  async search(query, progress, token) {
    if (token?.isCancellationRequested) throw new CancellationError()
    const worker = new Worker()
    let cancellation
    try {
      return await new Promise((resolve, reject) => {
        const results = []
        cancellation = token?.onCancellationRequested(() => reject(new CancellationError()))
        worker.onerror = event => reject(new Error(event.message))
        worker.onmessage = ({data}) => {
          if (data.error) return reject(new Error(data.error))
          if (data.done) return resolve({results, limitHit:data.limitHit, messages:[]})
          const match = {resource:URI.revive(data.resource), results:data.results}
          results.push(match)
          if (data.results) progress?.(match)
        }
        worker.postMessage({query:JSON.parse(JSON.stringify(query)), project:this.project.project,
          endpoint:new URL('rpc', document.baseURI).href})
      })
    } finally { cancellation?.dispose(); worker.terminate() }
  }
}
