import assert from 'node:assert/strict'
import {test} from 'node:test'
import {Drafts} from '../client/drafts.js'

function makeDrafts(call) {
  return new Drafts({workspace:{textDocuments:[]}, window:{showWarningMessage() {}}}, {call}, {})
}

test('discard waits for the active write, skips queued writes, and can resume on failure', async () => {
  const started = Promise.withResolvers()
  const finish = Promise.withResolvers()
  const writes = []
  const drafts = makeDrafts(async (action, fields) => {
    writes.push([action, fields.text])
    if (writes.length === 1) { started.resolve(); await finish.promise }
  })
  const a = {untitled:'a'.repeat(32)}, b = {untitled:'b'.repeat(32)}
  drafts.schedule(a, {text:'older'})
  drafts.schedule(b, {text:'second'})
  const flushing = drafts.flush()
  await started.promise
  drafts.schedule(a, {text:'newest'})
  let drained = false
  const draining = drafts.suspend().then(() => { drained = true })
  await Promise.resolve()
  assert.equal(drained, false)
  finish.reject(Error('disk full'))
  await assert.rejects(flushing)
  await draining
  await drafts.flush()
  assert.deepEqual(writes, [['draftSave','older']])
  assert.deepEqual(drafts.references(), [a, b])
  drafts.resume()
  await drafts.flush()
  assert.deepEqual(writes.slice(1), [['draftSave','newest'], ['draftSave','second']])
})

test('a rejected draft does not starve another document and discard removes an older copy', async () => {
  const writes = []
  const drafts = makeDrafts(async (action, fields) => {
    writes.push([action, fields.path])
    if (action === 'draftSave' && fields.path === 'large.py') throw Error('too large')
  })
  const large = {path:'large.py'}, small = {path:'small.py'}
  drafts.schedule(large, {text:'over the limit'})
  drafts.schedule(small, {text:'valid'})
  await assert.rejects(drafts.flush())
  assert.deepEqual(writes, [['draftSave','large.py'], ['draftSave','small.py']])
  drafts.schedule(large, null)
  await drafts.flush()
  assert.deepEqual(writes.at(-1), ['draftRemove','large.py'])
  assert.deepEqual(drafts.references(), [])
})

test('a skipped record or editor error does not block the next tab or wait for a notification', async () => {
  const choice = Promise.withResolvers()
  const warnings = [], details = [], opened = [], calls = []
  const api = {
    workspace:{async openTextDocument({content}) {
      if (content === 'cannot open') throw Error('Editor unavailable')
      return {uri:{toString:() => 'untitled:' + content}}
    }},
    window:{
      async showTextDocument(doc) { opened.push(doc.uri.toString()) },
      showWarningMessage(message, action) { warnings.push([message, action]); return choice.promise },
      showInformationMessage(title, options) { details.push([title, options]) }
    }
  }
  const bad = 'b'.repeat(32), good = 'a'.repeat(32)
  const project = {async call(action) {
    calls.push(action)
    if (action === 'draftList') return [{unreadable:'truncated.json'},
      {untitled:bad, text:'cannot open'}, {untitled:good, text:'good'}]
    assert.equal(action, 'status')
  }}
  const t = {unreadableDrafts:(_name, count) => 'Skipped ' + count, showDrafts:'See drafts', skippedDrafts:'Skipped drafts'}
  const drafts = new Drafts(api, project, t)
  await drafts.restore({})
  assert.deepEqual(opened, ['untitled:good'])
  assert.deepEqual(drafts.references(), [{untitled:good}])
  assert.deepEqual(calls, ['draftList', 'status'])
  assert.deepEqual(warnings, [['Skipped 2', 'See drafts']])
  assert.deepEqual(details, [])
  choice.resolve(t.showDrafts)
  await Promise.resolve()
  assert.deepEqual(details, [[t.skippedDrafts, {modal:true, detail:'truncated.json\nuntitled-' + bad + '.json'}]])
})

test('a lost project connection is not reported as a damaged draft', async () => {
  const api = {workspace:{async openTextDocument() { throw Error('Disconnected') }}, window:{}}
  const failed = Error('Session disconnected')
  for (const failAt of ['draftList', 'status']) {
    const drafts = new Drafts(api, {async call(action) {
      if (action === failAt) throw failed
      return [{untitled:'a'.repeat(32), text:'keep'}]
    }}, {})
    await assert.rejects(drafts.restore({}), error => error === failed)
    assert.deepEqual(drafts.references(), [])
  }
})
