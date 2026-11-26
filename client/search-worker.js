import {URI} from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri'
import {createRegExp} from '@codingame/monaco-vscode-api/vscode/vs/base/common/strings'
import {isFilePatternMatch, QueryGlobTester, SearchRange, TextSearchMatch} from '@codingame/monaco-vscode-api/vscode/vs/workbench/services/search/common/search'
import {PositionOffsetTransformer} from '@codingame/monaco-vscode-api/vscode/vs/editor/common/core/text/positionToOffsetImpl'
import {request} from './project.js'

function textResults(bytes, regexp, query, remaining) {
  const encoding = bytes[0] === 255 && bytes[1] === 254 ? 'utf-16le'
    : bytes[0] === 254 && bytes[1] === 255 ? 'utf-16be' : 'utf-8'
  if (encoding === 'utf-8' && bytes.subarray(0,8192).includes(0)) return []
  const source = new TextDecoder(encoding).decode(bytes).replace(/\r\n?/g, '\n')
  const offsets = new PositionOffsetTransformer(source)
  const lines = source.split('\n'), results = [], matched = new Set(), context = new Set()
  const surrounding = query.surroundingContext ?? 0
  for (const match of source.matchAll(regexp)) {
    const first = offsets.getPosition(match.index), last = offsets.getPosition(match.index + match[0].length)
    const start = first.lineNumber - 1, end = last.lineNumber - 1
    const range = new SearchRange(start, first.column - 1, end, last.column - 1)
    results.push(new TextSearchMatch(lines.slice(start, end + 1).join('\n'), range, query.previewOptions))
    if (surrounding) {
      for (let i = start; i <= end; i++) matched.add(i)
      for (let i = Math.max(0, start - surrounding); i < start; i++) context.add(i)
      for (let i = end + 1; i <= Math.min(lines.length - 1, end + surrounding); i++) context.add(i)
    }
    if (results.length > remaining) break
  }
  for (const line of context) if (!matched.has(line)) results.push({text:lines[line], lineNumber:line + 1})
  return results
}

async function search({project, query, endpoint}) {
  const call = (action, path) => request(action, {path, project:project.key}, endpoint)
  const text = query.contentPattern
  const regexp = text && createRegExp(text.pattern, !!text.isRegExp, {global:true, unicode:true,
    multiline:true, wholeWord:text.isWordMatch, matchCase:text.isCaseSensitive})
  let remaining = query.maxResults ?? 10000
  for (const scope of query.folderQueries) {
    const folder = URI.revive(scope.folder)
    const root = '/' + project.name
    if (folder.scheme !== 'studio' || (folder.path !== root && !folder.path.startsWith(root + '/'))) continue
    const prefix = folder.path.slice(root.length + 1)
    const globs = new QueryGlobTester(query, scope)
    const pending = ['']
    while (pending.length) {
      const directory = pending.pop()
      const entries = await call('list', [prefix,directory].filter(Boolean).join('/')).catch(error => {
        if (error.code === 'EntryNotFound' || error.code === 'NoPermissions') return []
        throw error
      })
      const siblings = new Set(entries.map(([name]) => name))
      for (const [name, type] of entries) {
        const path = directory ? directory + '/' + name : name
        const hasSibling = candidate => siblings.has(candidate)
        if (type === 2) {
          if (!globs.matchesExcludesSync(path, name, hasSibling)) pending.push(path)
          continue
        }
        if (!globs.includedInQuerySync(path, name, hasSibling)) continue
        if (query.filePattern && !isFilePatternMatch({relativePath:path}, query.filePattern.toLowerCase())) continue
        let results
        if (text) {
          let file
          try { file = await call('read', [prefix,path].filter(Boolean).join('/')) }
          catch (error) {
            if (['Unavailable','EntryNotFound','NoPermissions'].includes(error.code)) continue
            throw error
          }
          const bytes = Uint8Array.from(atob(file.bytes), ch => ch.charCodeAt(0))
          results = textResults(bytes, regexp, query, remaining)
          if (!results.length) continue
          results = results.filter(item => !item.rangeLocations || remaining-- > 0)
        } else remaining--
        if (results?.length || (!text && remaining >= 0)) {
          self.postMessage({resource:URI.joinPath(folder, path).toJSON(), results})
        }
        if (remaining < 0 || query.exists) return true
      }
    }
  }
  return false
}
self.onmessage = async ({data}) => {
  try { self.postMessage({done:true, limitHit:await search(data)}) }
  catch (error) { self.postMessage({error:error.message}) }
}
