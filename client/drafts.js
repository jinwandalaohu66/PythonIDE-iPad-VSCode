// Recovery belongs to the project, even when the next launch has a different browser origin.
const keyOf = ref => ref.untitled ? 'untitled:' + ref.untitled : 'file:' + ref.path
const newIdentity = () => crypto.randomUUID().replaceAll('-', '')

export class Drafts {
  constructor(api, project, t) {
    this.api = api
    this.project = project
    this.t = t
    this.documents = new Map() // Current editor URI -> durable recovery reference.
    this.pending = new Map()
    this.chain = Promise.resolve()
    this.suspended = false
    this.warned = false
  }
  debounce() {
    clearTimeout(this.timer)
    if (!this.suspended && this.pending.size) {
      this.timer = setTimeout(() => this.flush().catch(() => {}), 350)
    }
  }
  schedule(ref, data) {
    this.pending.set(keyOf(ref), {ref, data})
    if (data === null) this.flush().catch(() => {})
    else this.debounce()
  }
  flush() {
    clearTimeout(this.timer)
    if (this.suspended) return this.chain.catch(() => {})
    const write = async () => {
      let failure
      for (const [key, entry] of [...this.pending]) {
        if (this.suspended) break
        if (this.pending.get(key) !== entry) continue
        const {ref, data} = entry
        try {
          if (data === null) await this.project.call('draftRemove', ref)
          else await this.project.call('draftSave', {...ref, ...data})
          if (this.pending.get(key) === entry) this.pending.delete(key)
        } catch (error) { failure = error }
      }
      if (failure) {
        if (!this.warned && !this.suspended) this.api.window.showWarningMessage(this.t.recoveryFailed)
        this.warned = true
        throw failure
      }
      this.warned = false
    }
    this.chain = this.chain.catch(() => {}).then(write)
    return this.chain
  }
  async suspend() {
    this.suspended = true
    clearTimeout(this.timer)
    // A previously sent write must finish before the server clears confirmed copies.
    await this.chain.catch(() => {})
  }
  resume() {
    this.suspended = false
    for (const doc of this.api.workspace.textDocuments) {
      if (doc.isDirty) this.changed(doc)
    }
    this.debounce()
  }
  forget(uri) {
    const key = uri.toString()
    const ref = this.documents.get(key)
    if (!ref) return
    this.documents.delete(key)
    this.schedule(ref, null)
  }
  changed(doc) {
    if (!doc.isDirty) { this.forget(doc.uri); return }
    const key = doc.uri.toString()
    let ref = this.documents.get(key)
    if (!ref) {
      if (doc.uri.scheme === 'untitled') ref = {untitled:newIdentity()}
      else if (doc.uri.scheme === 'studio') {
        const path = this.project.relative(doc.uri)
        const revision = this.project.revisions.get(path)
        if (!revision) return
        ref = {path, revision}
      } else return
      this.documents.set(key, ref)
    }
    this.schedule(ref, {text:doc.getText(), language:doc.languageId})
  }
  watch(textFiles) {
    const {api, project} = this
    api.workspace.onDidOpenTextDocument(doc => { if (doc.isDirty) this.changed(doc) })
    api.workspace.onDidChangeTextDocument(({document}) => this.changed(document))
    api.workspace.onDidSaveTextDocument(doc => { if (!doc.isDirty) this.forget(doc.uri) })
    // A language-mode change closes and opens an extension document with the same URI.
    // Saving or reverting the underlying untitled working copy is the actual end of a draft.
    textFiles.untitled.onDidSave(({source}) => this.forget(source))
    textFiles.untitled.onWillDispose(model => { if (!model.isDirty()) this.forget(model.resource) })
    textFiles.files.onDidRevert(model => this.forget(model.resource))
    textFiles.files.onDidRemove(uri => {
      if (uri.scheme === 'studio') project.revisions.delete(project.relative(uri))
    })
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) this.flush().catch(() => {})
    })
  }
  async openUntitled(draft) {
    const {api} = this
    const doc = await api.workspace.openTextDocument({content:draft.text, language:draft.language || undefined})
    await api.window.showTextDocument(doc, {preview:false})
    this.documents.set(doc.uri.toString(), {untitled:draft.untitled})
  }
  async restoreOne(folder, draft) {
    const {api, project} = this
    if (draft.untitled) {
      await this.openUntitled(draft)
      return 'restored'
    }
    const uri = api.Uri.joinPath(folder, draft.path)
    let doc
    try { doc = await api.workspace.openTextDocument(uri) }
    catch (error) {
      if (!(error.code === 'FileNotFound' || /not found|no longer exists|EntryNotFound/i.test(error.message))) throw error
    }
    if (doc && doc.getText() === draft.text) {
      this.schedule({path:draft.path}, null)
      return
    }
    if (doc && project.revisions.get(draft.path) === draft.revision) {
      const edit = new api.WorkspaceEdit()
      edit.replace(uri, new api.Range(doc.positionAt(0), doc.positionAt(doc.getText().length)), draft.text)
      if (!await api.workspace.applyEdit(edit)) throw Error(this.t.recoveryFailed)
      await api.window.showTextDocument(doc, {preview:false})
      this.documents.set(uri.toString(), {path:draft.path, revision:draft.revision})
      return 'restored'
    }
    const copy = await project.call('draftDetach', {path:draft.path, untitled:newIdentity()})
    await this.openUntitled({...copy, language:copy.language || doc?.languageId})
    return 'conflict'
  }
  async restore(folder) {
    const {api, project, t} = this
    const outcomes = new Set(), skipped = []
    let editorFailed = false
    for (const draft of await project.call('draftList')) {
      if (draft.unreadable) { skipped.push(draft.unreadable); continue }
      try { outcomes.add(await this.restoreOne(folder, draft)) }
      catch {
        editorFailed = true
        skipped.push(draft.path || 'untitled-' + draft.untitled + '.json')
      }
    }
    // A dead session is a startup error, not a warning about individual files.
    if (editorFailed) await project.call('status')
    const warnings = []
    // Notifications truncate long text and can interpret linked-text markup.
    // Keep long lists and unusual filenames in the standard plain-text detail.
    const inlineName = skipped.length === 1 && skipped[0].length <= 240 && !/[\[\]\r\n]/.test(skipped[0])
    if (skipped.length) warnings.push(t.unreadableDrafts(inlineName ? skipped[0] : '', skipped.length))
    if (outcomes.has('conflict')) warnings.push(t.conflict)
    if (skipped.length && !inlineName) {
      api.window.showWarningMessage(warnings.join(' '), t.showDrafts).then(choice => {
        if (choice === t.showDrafts) api.window.showInformationMessage(t.skippedDrafts, {modal:true, detail:skipped.join('\n')})
      })
    } else if (warnings.length) api.window.showWarningMessage(warnings.join(' '))
    else if (outcomes.has('restored')) api.window.showInformationMessage(t.recovered)
  }
  references() {
    const refs = new Map()
    for (const {ref} of this.pending.values()) refs.set(keyOf(ref), ref)
    for (const ref of this.documents.values()) refs.set(keyOf(ref), ref)
    return [...refs.values()]
  }
}
