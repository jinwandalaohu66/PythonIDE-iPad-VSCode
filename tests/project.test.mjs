import assert from 'node:assert/strict'
import test from 'node:test'
import {ProjectFiles} from '../client/project.js'

test('deleting a folder forgets descendant revisions and preserves a similarly named folder', async () => {
  const provider = new ProjectFiles({name:'P', key:'project'})
  const uri = path => ({scheme:'studio', path:'/P/' + path})
  const requests = []
  provider.call = async (action, fields) => {
    requests.push({action, ...fields})
    return {revision:'original', bytes:'eA=='}
  }
  await provider.readFile(uri('demo/a.py'))
  await provider.readFile(uri('demo2/b.py'))
  await provider.delete(uri('demo'))
  await provider.mkdir(uri('demo'))
  await provider.writeFile(uri('demo/a.py'), new Uint8Array([42]), {create:true, overwrite:true})
  assert.equal(requests.at(-1).revision, undefined)
  assert.equal(provider.revisions.get('demo2/b.py'), 'original')
})
