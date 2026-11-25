import {getService, IEditorService} from '@codingame/monaco-vscode-api'
import {EditorPane, SimpleEditorInput, registerEditorPane} from '@codingame/monaco-vscode-api/service-override/tools/views'
import {SIDE_GROUP} from '@codingame/monaco-vscode-api/vscode/vs/workbench/services/editor/common/editorService'
import {URI} from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri'
import {marked} from 'marked'
import DOMPurify from 'dompurify'

const paneId = 'pythonideWorkbench.preview'
const docStyle = 'html{color-scheme:light dark}body{box-sizing:border-box;max-width:54rem;margin:0 auto;padding:1.1rem clamp(16px,5vw,48px) 3rem;font:16px/1.65 -apple-system,system-ui,sans-serif;overflow-wrap:anywhere}h1,h2{line-height:1.24;border-bottom:1px solid #8885;padding-bottom:.3em}h1{font-size:2em}pre,code{font-family:ui-monospace,monospace;font-size:.9em;background:#8882;border-radius:4px}pre,blockquote{padding:.65em 1em}pre{overflow:auto}pre code{background:transparent}img{max-width:100%}table{border-collapse:collapse}td,th{border:1px solid #8886;padding:.35em .7em}blockquote{border-left:4px solid #8887;margin-inline:0}a{color:LinkText}'

function markdownPage(text, fileURL, base) {
  const fragment = DOMPurify.sanitize(marked.parse(text, {async:false}), {
    RETURN_DOM_FRAGMENT:true,
    ALLOWED_TAGS:'p br hr h1 h2 h3 h4 h5 h6 a img ol ul li blockquote strong em del pre code table thead tbody tr th td details summary kbd'.split(' '),
    ALLOWED_ATTR:['href','src','alt','title','colspan','rowspan','align','start','id']
  })
  for (const image of fragment.querySelectorAll('img[src]')) {
    const src = image.getAttribute('src')
    if (/^data:image\/(png|jpeg|gif|webp);base64,/i.test(src)) continue
    try {
      const url = new URL(src, fileURL)
      if (url.href.startsWith(base)) { image.src = url.href; continue }
    } catch {}
    image.removeAttribute('src')
  }
  for (const link of fragment.querySelectorAll('a[href]')) {
    if (!link.getAttribute('href').startsWith('#')) link.removeAttribute('href')
  }
  const markup = document.createElement('div')
  markup.append(fragment)
  const dark = document.querySelector('.monaco-workbench')?.matches('.vs-dark, .hc-black')
  return '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data: ' + base + '; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'"><style>' + docStyle + 'html{color-scheme:' + (dark ? 'dark' : 'light') + '}</style>' + markup.innerHTML
}

class PreviewInput extends SimpleEditorInput {
  get typeId() { return paneId }
  matches(other) { return other instanceof PreviewInput && other.resource.toString() === this.resource.toString() }
}

export function registerPreviews(api, t, project) {
  class PreviewPane extends EditorPane {
    constructor(group) { super(paneId, group) }
    createEditor(parent) {
      this.host = document.createElement('div')
      this.host.className = 'wb-preview'
      parent.append(this.host)
    }
    layout({width,height}) {
      this.host.style.width = width + 'px'
      this.host.style.height = height + 'px'
    }
    clearInput() { this.clean?.(); super.clearInput() }
    dispose() { this.clean?.(); super.dispose() }
    focus() { this.host.querySelector('iframe')?.focus() }
    async setInput(input, options, context, token) {
      this.clean?.()
      await super.setInput(input, options, context, token)
      if (token.isCancellationRequested) return
      const frame = document.createElement('iframe')
      frame.title = input.getName()
      frame.setAttribute('sandbox', input.markdown ? '' : 'allow-scripts')
      frame.referrerPolicy = 'no-referrer'
      this.host.replaceChildren(frame)
      let timer
      const update = () => {
        if (input.markdown) frame.srcdoc = markdownPage(input.doc.getText(), input.url, input.base)
        else frame.src = input.url
      }
      const later = () => { clearTimeout(timer); timer = setTimeout(update, 220) }
      const changes = api.workspace.onDidChangeTextDocument(({document}) => {
        if (input.markdown && document === input.doc) later()
      })
      const saves = api.workspace.onDidSaveTextDocument(doc => {
        if (!input.markdown && doc.uri.scheme === 'studio') later()
      })
      const theme = api.window.onDidChangeActiveColorTheme(() => { if (input.markdown) later() })
      this.clean = () => { clearTimeout(timer); changes.dispose(); saves.dispose(); theme.dispose(); frame.remove(); this.clean = null }
      update()
    }
  }
  registerEditorPane(paneId, t.previewTitle, PreviewPane, [PreviewInput])
  return async uri => {
    const doc = await api.workspace.openTextDocument(uri)
    const urls = await project.call('preview', {path:project.relative(uri)})
    const input = new PreviewInput(URI.from({scheme:'workbench-preview', path:uri.path}))
    input.doc = doc
    input.url = new URL(urls.url, location.origin).href
    input.base = new URL(urls.base, location.origin).href
    input.markdown = /\.(md|markdown)$/i.test(uri.path)
    input.setName(t.previewTitle + ' · ' + uri.path.split('/').pop())
    await (await getService(IEditorService)).openEditor(input, {pinned:true, preserveFocus:true, revealIfOpened:true}, SIDE_GROUP)
  }
}

export async function runJavaScript(project, path, update) {
  const urls = await project.call('preview', {path})
  const frame = document.createElement('iframe')
  frame.hidden = true
  frame.setAttribute('sandbox', 'allow-scripts')
  frame.referrerPolicy = 'no-referrer'
  const url = new URL(urls.base + '.run.html', location.origin)
  url.searchParams.set('entry', new URL(urls.url, location.origin).href)
  let output = '', closed = false
  function finish(status) {
    if (closed) return
    closed = true
    window.removeEventListener('message', message)
    frame.remove()
    update({status, output})
  }
  function message(event) {
    if (event.source !== frame.contentWindow || event.origin !== 'null' || event.data?.channel !== 'project-javascript') return
    const {kind, text} = event.data
    if (typeof text !== 'string') return
    output = (output + text).slice(-65536)
    if (kind === 'output') update({status:'running', output})
    if (kind === 'failed' || kind === 'finished') finish(kind)
  }
  window.addEventListener('message', message)
  frame.src = url.href
  document.body.append(frame)
  update({status:'running', output})
  return () => finish('stopped')
}
