import {defineConfig} from 'vite'

export default defineConfig({
  base:'./',
  worker:{format:'es'},
  build:{target:'safari16.4', outDir:'../web', emptyOutDir:true, cssCodeSplit:false,
    assetsInlineLimit:0, reportCompressedSize:false, chunkSizeWarningLimit:16000}
})
