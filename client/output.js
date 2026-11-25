import {getService, IViewsService} from '@codingame/monaco-vscode-api'
import {registerCustomView, ViewContainerLocation} from '@codingame/monaco-vscode-api/service-override/tools/views'

export class RunOutput {
  constructor(t, reply, goTo, recover) {
    this.t = t
    this.recover = recover
    this.state = {status:'idle', output:''}
    this.id = 'pythonideWorkbench.output'
    registerCustomView({
      id:this.id, name:t.output, location:ViewContainerLocation.Panel, canToggleVisibility:true,
      renderBody:container => {
        const body = document.createElement('div')
        body.className = 'wb-output'
        body.innerHTML = '<span class="state" role="status"></span><pre tabindex="0"></pre><div class="frames"></div><form hidden><input autocomplete="off" autocapitalize="off" spellcheck="false"><button type="submit">↵</button></form>'
        const field = body.querySelector('input'), form = body.querySelector('form')
        field.placeholder = t.input
        field.setAttribute('aria-label', t.input)
        form.querySelector('button').setAttribute('aria-label', t.send)
        let composing = false, confirmingComposition = false
        field.addEventListener('compositionstart', () => { composing = true })
        field.addEventListener('compositionend', () => { composing = false })
        field.addEventListener('keydown', event => {
          if (event.key !== 'Enter' || !event.isComposing && !composing && event.keyCode !== 229) return
          confirmingComposition = true
          setTimeout(() => { confirmingComposition = false }, 0)
          event.stopPropagation()
        })
        form.onsubmit = async event => {
          event.preventDefault()
          if (composing || confirmingComposition || this.submitting || this.state.status !== 'input') return
          this.submitting = true
          try { if (await reply(field.value)) field.value = '' }
          finally { this.submitting = false }
        }
        container.append(body)
        this.body = body
        this.goTo = goTo
        this.frames = undefined
        this.render(this.state)
        return {dispose:() => { if (this.body === body) this.body = null }}
      }
    })
  }
  async show() {
    await (await getService(IViewsService)).openView(this.id, false)
  }
  render(state) {
    this.state = state
    const automatic = !!state.id && this.automaticJob === state.id && state.status === 'failed'
    if (automatic) this.automaticJob = null
    if (!this.body) return
    const status = this.body.querySelector('.state'), log = this.body.querySelector('pre')
    const label = this.t[state.status === 'input' ? 'inputState' : state.status] || state.status
    const heading = state.name ? state.name + ' · ' + label : label
    if (status.textContent !== heading) status.textContent = heading
    if (log.textContent !== state.output || log.dataset.errorLength !== String(state.errorLength || 0)) {
      const scroll = this.body.closest('.monaco-scrollable-element')?.firstElementChild
      const atEnd = scroll && scroll.scrollHeight - scroll.scrollTop - scroll.clientHeight < 32
      log.dataset.errorLength = String(state.errorLength || 0)
      if (state.errorLength) {
        const error = document.createElement('span')
        error.className = 'run-error'
        error.textContent = state.output.slice(-state.errorLength)
        log.replaceChildren(document.createTextNode(state.output.slice(0, -state.errorLength)), error)
      } else {
        log.textContent = state.output
      }
      if (atEnd) requestAnimationFrame(() => { scroll.scrollTop = scroll.scrollHeight })
    }
    const frames = state.frames || []
    const key = JSON.stringify([frames, state.id])
    if (this.frames !== key) {
      const links = this.body.querySelector('.frames')
      links.replaceChildren(...frames.map(frame => {
        const link = document.createElement('button')
        link.textContent = frame.path + ':' + frame.line
        link.title = this.t.frames
        link.onclick = () => this.goTo(frame)
        return link
      }))
      this.frames = key
    }
    this.body.querySelector('form').hidden = state.status !== 'input'
    if (automatic && state.blockedLibrary) {
      const error = log.querySelector('.run-error')
      requestAnimationFrame(() => setTimeout(() => {
        if (this.state.id !== state.id || document.hidden || !error?.isConnected) return
        const line = Array.from(error.getClientRects()).filter(rect => rect.width > 0 && rect.height > 0).pop()
        if (!line) return
        const hit = document.elementFromPoint(line.left + Math.min(2, line.width / 2), line.top + line.height / 2)
        if (error.contains(hit)) this.recover(state.id)
      }, 450))
    }
  }
}
