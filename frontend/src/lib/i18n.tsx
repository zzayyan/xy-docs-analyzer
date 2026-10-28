import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

// Explicit shape, so a missing Indonesian string is a build error, not a silent English fallback
export interface Dict {
  appName: string;
  langEnglish: string;
  langIndonesian: string;

  railDocuments: string;
  railCollapse: string;
  railExpand: string;
  railEmpty: string;
  logout: (username: string) => string;
  settingsOpen: string;

  loginUsername: string;
  loginPassword: string;
  loginSubmit: string;
  loginWrong: string;

  settingsTitle: string;
  settingsAccount: string;
  settingsUsers: string;
  roleAdmin: string;
  roleUser: string;
  passwordCurrent: string;
  passwordNew: string;
  passwordChange: string;
  passwordChanged: string;
  userAdd: string;
  userRole: string;
  userYou: string;
  userResetPassword: string;
  userDeleteTitle: string;
  userDeleteBody: (username: string) => string;
  passwordHint: string;
  usersCount: (n: number) => string;
  userCreated: string;
  userActions: string;
  userAddHint: string;
  userResetPasswordTitle: (username: string) => string;
  userResetPasswordHint: string;
  settingsModels: string;
  modelsSourceEnv: string;
  modelsSourceSaved: string;
  modelsChat: string;
  modelsChatHint: string;
  modelsProvider: string;
  modelsProviderOllama: string;
  modelsProviderOpenai: string;
  modelsBaseUrl: string;
  modelsModel: string;
  modelsApiKey: string;
  modelsKeyKeep: (masked: string) => string;
  modelsReasoning: string;
  modelsChoices: string;
  modelsChoicesHint: string;
  modelsTest: string;
  modelsTesting: string;
  modelsTestOk: (ms: number) => string;
  modelsSave: string;
  modelsSaved: string;
  modelsReset: string;
  modelsResetTitle: string;
  modelsResetBody: string;
  embedTitle: string;
  embedStored: (chunks: number, model: string, dim: number) => string;
  embedEmpty: string;
  embedDim: string;
  embedDims: (dim: number) => string;
  embedUseDim: (dim: number) => string;
  embedNeedsReindex: (chunks: number) => string;
  embedSaveReindex: string;
  embedConfirmTitle: string;
  embedConfirmBody: (chunks: number) => string;
  embedProgress: (done: number, total: number) => string;
  embedDone: string;
  embedFailed: (error: string) => string;
  dropActive: string;

  emptyTitle: string;
  emptyBody: string;

  modelLabel: string;

  uploadButton: string;
  uploadUploading: string;
  uploadLimitsCaption: (mb: number, pages: number, formats: string) => string;
  uploadLimitsShort: (mb: number, pages: number) => string;
  uploadFormats: (formats: string) => string;
  uploadLimitsUnavailable: string;

  statusQueued: string;
  statusConverting: string;
  statusEmbedding: string;
  statusBuildingTree: string;
  statusExtractingGraph: string;
  statusDone: string;
  statusError: string;

  modeShort: string;
  modeLong: string;

  deleteAction: string;
  originalLink: string;
  deleteConfirmTitle: string;
  deleteConfirmBody: (name: string) => string;
  deleteConfirmConfirm: string;
  deleteConfirmCancel: string;

  relativeJustNow: string;

  errorGeneric: string;
  errorDetailsShow: string;
  errorDetailsHide: string;

  docElapsedLabel: string;
  docEtaLabel: (eta: string) => string;
  docStepCount: (done: number, total: number) => string;
  unitPages: string;
  unitChunks: string;
  unitSections: string;
  docErrorTitle: string;
  docErrorReupload: string;
  docRetry: string;
  docRetrying: string;
  tabProcess: string;
  ocrPages: (scanned: number, pages: number) => string;
  ocrOff: string;
  stageTokensChunks: (tokens: string, chunks: number) => string;
  stageLanguage: (language: string) => string;
  stageMode: (long: boolean, tokens: string, limit: string) => string;
  stageEmbedded: (chunks: number) => string;
  stageSummarized: (sections: number) => string;
  stageEntities: (entities: number, chunks: number) => string;
  stageGraphSkipped: (chunks: number) => string;
  stageSkipped: string;
  stageQueuedHint: string;
  stageFailed: string;
  stageTotal: (duration: string) => string;

  chatPlaceholder: string;
  chatSend: string;
  chatSending: string;
  chatFollowSources: string;
  chatFoundSources: (n: number) => string;
  chatEmptyTitle: string;
  chatEmpty: string;
  chatSuggestions: string[];
  chatComposerHint: string;
  chatClear: string;
  chatClearConfirmTitle: string;
  chatClearConfirmBody: string;
  chatInterrupted: string;
  chatStatusContextualize: string;
  chatStatusVectorRetrieve: string;
  chatStatusTreeSearch: string;
  chatStatusKgRetrieve: string;

  citationTitle: (n: number) => string;
  citationSource: string;
  citationPages: string;
  citationHeadings: string;
  citationSourceVector: string;
  citationSourceTree: string;
  citationSourceKg: string;
  citationSourceKgFacts: string;
  citationClose: string;
  citationPageOf: (i: number, n: number) => string;
  citationPrevPage: string;
  citationNextPage: string;
  viewerOpen: string;
  viewerZoomIn: string;
  viewerZoomOut: string;
  viewerGoToPage: string;
  viewerCitationOf: (i: number, n: number) => string;
  viewerPrevCitation: string;
  viewerNextCitation: string;
  viewerSlide: (n: number) => string;

  tabChat: string;
  tabOutline: string;
  outlineEmpty: string;
  outlineSelectSection: string;
  outlinePageRange: (start: number, end: number) => string;
  outlineChunkCount: (n: number) => string;
  outlineChunksEmpty: string;

  tabGraph: string;
  graphEmpty: string;
  graphSearch: string;
  graphShowing: (shown: number, total: number) => string;
  graphMentions: (n: number) => string;
  graphRelations: string;
  graphNoRelations: string;
  graphEvidence: string;
  graphHint: string;
  graphFit: string;
  graphTypes: Record<string, string>;

}

const en: Dict = {
  appName: 'Docs Analyzer',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  railDocuments: 'Documents',
  railCollapse: 'Hide sidebar',
  railExpand: 'Show sidebar',
  railEmpty: 'No documents yet. Upload one to start.',
  logout: (username) => `Sign out (${username})`,
  settingsOpen: 'Settings',

  loginUsername: 'Username',
  loginPassword: 'Password',
  loginSubmit: 'Sign in',
  loginWrong: 'Wrong username or password.',

  settingsTitle: 'Settings',
  settingsAccount: 'Your account',
  settingsUsers: 'Users',
  roleAdmin: 'Admin',
  roleUser: 'User',
  passwordCurrent: 'Current password',
  passwordNew: 'New password',
  passwordChange: 'Change password',
  passwordChanged: 'Password changed. Other sessions are signed out.',
  userAdd: 'Add user',
  userRole: 'Role',
  userYou: 'you',
  userResetPassword: 'Reset password',
  userDeleteTitle: 'Delete this user?',
  userDeleteBody: (username) => `${username} is signed out and can no longer sign in. Documents stay.`,
  passwordHint: 'At least 8 characters. Your other sessions are signed out.',
  usersCount: (n) => (n === 1 ? '1 user' : `${n} users`),
  userCreated: 'Added',
  userActions: 'Actions',
  userAddHint: 'Every user sees the same documents. Only admins open Users and model settings.',
  userResetPasswordTitle: (username) => `Reset password for ${username}`,
  userResetPasswordHint: 'At least 8 characters. Every session of this user is signed out.',
  settingsModels: 'Models',
  modelsSourceEnv: 'Using the values from backend/.env. Saving here overrides them.',
  modelsSourceSaved: 'Saved here, overriding backend/.env.',
  modelsChat: 'Chat model',
  modelsChatHint: 'Answers questions and does the ingest work: summaries and the knowledge graph.',
  modelsProvider: 'Provider',
  modelsProviderOllama: 'Ollama (local)',
  modelsProviderOpenai: 'OpenAI-compatible',
  modelsBaseUrl: 'Server URL',
  modelsModel: 'Model',
  modelsApiKey: 'API key',
  modelsKeyKeep: (masked) => `${masked} (leave empty to keep)`,
  modelsReasoning: 'Reasoning effort (optional)',
  modelsChoices: 'More models in the chat picker',
  modelsChoicesHint: 'Comma-separated, served by the same server.',
  modelsTest: 'Test connection',
  modelsTesting: 'Testing…',
  modelsTestOk: (ms) => `Connected in ${ms} ms`,
  modelsSave: 'Save',
  modelsSaved: 'Saved. New calls use these models now.',
  modelsReset: 'Reset to .env',
  modelsResetTitle: 'Reset to .env?',
  modelsResetBody: 'The models saved here are dropped and the values in backend/.env are used again.',
  embedTitle: 'Embedding model',
  embedStored: (chunks, model, dim) => `${chunks} chunks are embedded with ${model} (${dim} dimensions).`,
  embedEmpty: 'No document is embedded yet, so any model can be used.',
  embedDim: 'Dimensions',
  embedDims: (dim) => `${dim} dimensions`,
  embedUseDim: (dim) => `Use ${dim}`,
  embedNeedsReindex: (chunks) =>
    `Another model: all ${chunks} chunks are embedded again before it is used. Search keeps the current model until that is done. Uploads wait meanwhile.`,
  embedSaveReindex: 'Switch and re-index',
  embedConfirmTitle: 'Switch the embedding model?',
  embedConfirmBody: (chunks) =>
    `All ${chunks} chunks are embedded again with the new model. No LLM call and no re-ingest; documents stay as they are. If it fails, nothing changes.`,
  embedProgress: (done, total) => `Re-indexing: ${done} of ${total} documents`,
  embedDone: 'Re-index finished. Search now uses the new model.',
  embedFailed: (error) => `Re-index failed, the previous model is still in use: ${error}`,
  dropActive: 'Drop to upload',

  emptyTitle: 'Analyze a document',
  emptyBody: 'Ask questions as soon as processing finishes; long documents also get a browsable outline.',

  modelLabel: 'Model',

  uploadButton: 'Upload',
  uploadUploading: 'Uploading…',
  uploadLimitsCaption: (mb, pages, formats) => `${formats}. Up to ${mb} MB; PDFs up to ${pages} pages.`,
  uploadLimitsShort: (mb, pages) => `${mb} MB, ${pages} PDF pages max`,
  uploadFormats: (formats) => `Supported formats: ${formats}`,
  uploadLimitsUnavailable: 'API not reachable',

  statusQueued: 'Queued',
  statusConverting: 'Converting',
  statusEmbedding: 'Embedding',
  statusBuildingTree: 'Building outline',
  statusExtractingGraph: 'Extracting graph',
  statusDone: 'Ready',
  statusError: 'Failed',

  modeShort: 'Short',
  modeLong: 'Long',

  deleteAction: 'Delete',
  originalLink: 'Original',
  deleteConfirmTitle: 'Delete this document?',
  deleteConfirmBody: (name) =>
    `"${name}" and everything derived from it (chunks, outline, chat history) will be permanently removed.`,
  deleteConfirmConfirm: 'Delete',
  deleteConfirmCancel: 'Cancel',

  relativeJustNow: 'just now',

  errorGeneric: 'Something went wrong. Please try again.',
  errorDetailsShow: 'Show details',
  errorDetailsHide: 'Hide details',

  docElapsedLabel: 'Elapsed',
  docEtaLabel: (eta) => `About ${eta} remaining`,
  docStepCount: (done, total) => `${done} / ${total}`,
  unitPages: 'pages',
  unitChunks: 'chunks',
  unitSections: 'sections',
  docErrorTitle: 'Processing failed',
  docErrorReupload: 'This document could not be processed. Try again, or delete it and upload the original file again.',
  docRetry: 'Try again',
  docRetrying: 'Starting...',
  tabProcess: 'Process',
  ocrPages: (scanned, pages) => `OCR on: ${scanned} of ${pages} page${pages === 1 ? '' : 's'} have no text layer`,
  ocrOff: 'OCR off: every page has a text layer',
  stageTokensChunks: (tokens, chunks) => `${tokens} tokens split into ${chunks} chunk${chunks === 1 ? '' : 's'}`,
  stageLanguage: (language) => `Language: ${language}`,
  stageMode: (long, tokens, limit) => (long ? `Long mode: ${tokens} > ${limit} tokens` : `Short mode: ${tokens} ≤ ${limit} tokens`),
  stageEmbedded: (chunks) => `${chunks} chunk${chunks === 1 ? '' : 's'} turned into vectors`,
  stageSummarized: (sections) => `${sections} section${sections === 1 ? '' : 's'} summarized`,
  stageEntities: (entities, chunks) => `${entities} entities found in ${chunks} chunk${chunks === 1 ? '' : 's'}`,
  stageGraphSkipped: (chunks) => `${chunks} chunk${chunks === 1 ? '' : 's'} skipped: extraction failed`,
  stageSkipped: 'Skipped: only runs for long documents',
  stageQueuedHint: 'Waiting for another document to finish converting',
  stageFailed: 'Failed at this stage',
  stageTotal: (duration) => `Total ${duration}`,

  chatPlaceholder: 'Ask about this document',
  chatSend: 'Send',
  chatSending: 'Thinking…',
  chatFollowSources: 'Follow sources',
  chatFoundSources: (n) => (n === 1 ? 'Found 1 source' : `Found ${n} sources`),
  chatEmptyTitle: 'Ask anything about this document',
  chatEmpty: 'Answers cite the passages they come from.',
  chatSuggestions: ['Summarize this document', 'What are the key findings?', 'List the main sections and what each covers'],
  chatComposerHint: 'Enter to send, Shift + Enter for a new line',
  chatClear: 'Clear chat',
  chatClearConfirmTitle: 'Clear chat history?',
  chatClearConfirmBody: 'All questions and answers for this document will be permanently removed.',
  chatInterrupted: 'Interrupted before finishing',
  chatStatusContextualize: 'Understanding the question…',
  chatStatusVectorRetrieve: 'Searching the document…',
  chatStatusTreeSearch: 'Reading the outline…',
  chatStatusKgRetrieve: 'Reading the knowledge graph…',

  citationTitle: (n) => `Source ${n}`,
  citationSource: 'Found by',
  citationPages: 'Pages',
  citationHeadings: 'Section',
  citationSourceVector: 'Vector search',
  citationSourceTree: 'Document outline',
  citationSourceKg: 'Knowledge graph evidence',
  citationSourceKgFacts: 'Knowledge graph facts',
  citationClose: 'Close',
  citationPageOf: (i, n) => `Page ${i} of ${n}`,
  citationPrevPage: 'Previous page',
  citationNextPage: 'Next page',
  viewerOpen: 'View document',
  viewerZoomIn: 'Zoom in',
  viewerZoomOut: 'Zoom out',
  viewerGoToPage: 'Go to page',
  viewerCitationOf: (i, n) => `Citation ${i} of ${n}`,
  viewerPrevCitation: 'Previous citation',
  viewerNextCitation: 'Next citation',
  viewerSlide: (n) => `Slide ${n}`,

  tabChat: 'Chat',
  tabOutline: 'Outline',
  outlineEmpty: 'No outline available for this document.',
  outlineSelectSection: 'Select a section to read it.',
  outlinePageRange: (start, end) => (start === end ? `p. ${start}` : `p. ${start}-${end}`),
  outlineChunkCount: (n) => `${n} chunk${n === 1 ? '' : 's'}`,
  outlineChunksEmpty: 'This section has no text of its own. Its subsections hold the content.',

  tabGraph: 'Graph',
  graphEmpty: 'No knowledge graph for this document.',
  graphSearch: 'Find an entity...',
  graphShowing: (shown, total) => `Showing ${shown} of ${total} entities`,
  graphMentions: (n) => (n === 1 ? 'Mentioned in 1 passage' : `Mentioned in ${n} passages`),
  graphRelations: 'Relations',
  graphNoRelations: 'No relations to other entities.',
  graphEvidence: 'Where it is mentioned',
  graphHint: 'Drag to move, scroll to zoom, click an entity to explore it.',
  graphFit: 'Fit to view',
  graphTypes: {
    Person: 'Person', Organization: 'Organization', Location: 'Location', Concept: 'Concept',
    Event: 'Event', Product: 'Product', Regulation: 'Regulation', Date: 'Date / value',
  },

};

const id: Dict = {
  appName: 'Docs Analyzer',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  railDocuments: 'Dokumen',
  railCollapse: 'Sembunyikan panel',
  railExpand: 'Tampilkan panel',
  railEmpty: 'Belum ada dokumen. Unggah satu untuk mulai.',
  logout: (username) => `Keluar (${username})`,
  settingsOpen: 'Pengaturan',

  loginUsername: 'Nama pengguna',
  loginPassword: 'Kata sandi',
  loginSubmit: 'Masuk',
  loginWrong: 'Nama pengguna atau kata sandi salah.',

  settingsTitle: 'Pengaturan',
  settingsAccount: 'Akun Anda',
  settingsUsers: 'Pengguna',
  roleAdmin: 'Admin',
  roleUser: 'Pengguna',
  passwordCurrent: 'Kata sandi saat ini',
  passwordNew: 'Kata sandi baru',
  passwordChange: 'Ganti kata sandi',
  passwordChanged: 'Kata sandi diganti. Sesi lain sudah dikeluarkan.',
  userAdd: 'Tambah pengguna',
  userRole: 'Peran',
  userYou: 'Anda',
  userResetPassword: 'Reset kata sandi',
  userDeleteTitle: 'Hapus pengguna ini?',
  userDeleteBody: (username) => `${username} dikeluarkan dan tidak bisa masuk lagi. Dokumen tetap ada.`,
  passwordHint: 'Minimal 8 karakter. Sesi Anda yang lain akan dikeluarkan.',
  usersCount: (n) => `${n} pengguna`,
  userCreated: 'Ditambahkan',
  userActions: 'Aksi',
  userAddHint: 'Semua pengguna melihat dokumen yang sama. Hanya admin yang bisa membuka Pengguna dan pengaturan model.',
  userResetPasswordTitle: (username) => `Reset kata sandi ${username}`,
  userResetPasswordHint: 'Minimal 8 karakter. Semua sesi pengguna ini akan dikeluarkan.',
  settingsModels: 'Model',
  modelsSourceEnv: 'Memakai nilai dari backend/.env. Menyimpan di sini akan menimpanya.',
  modelsSourceSaved: 'Disimpan di sini, menimpa backend/.env.',
  modelsChat: 'Model chat',
  modelsChatHint: 'Menjawab pertanyaan dan mengerjakan ingest: ringkasan dan knowledge graph.',
  modelsProvider: 'Provider',
  modelsProviderOllama: 'Ollama (lokal)',
  modelsProviderOpenai: 'OpenAI-compatible',
  modelsBaseUrl: 'URL server',
  modelsModel: 'Model',
  modelsApiKey: 'API key',
  modelsKeyKeep: (masked) => `${masked} (kosongkan untuk tetap)`,
  modelsReasoning: 'Reasoning effort (opsional)',
  modelsChoices: 'Model tambahan di pilihan chat',
  modelsChoicesHint: 'Pisahkan dengan koma, dari server yang sama.',
  modelsTest: 'Tes koneksi',
  modelsTesting: 'Menguji…',
  modelsTestOk: (ms) => `Terhubung dalam ${ms} ms`,
  modelsSave: 'Simpan',
  modelsSaved: 'Tersimpan. Panggilan baru memakai model ini.',
  modelsReset: 'Kembalikan ke .env',
  modelsResetTitle: 'Kembalikan ke .env?',
  modelsResetBody: 'Model yang disimpan di sini dihapus, lalu nilai di backend/.env dipakai lagi.',
  embedTitle: 'Model embedding',
  embedStored: (chunks, model, dim) => `${chunks} chunk di-embed dengan ${model} (${dim} dimensi).`,
  embedEmpty: 'Belum ada dokumen yang di-embed, jadi model apa pun bisa dipakai.',
  embedDim: 'Dimensi',
  embedDims: (dim) => `${dim} dimensi`,
  embedUseDim: (dim) => `Pakai ${dim}`,
  embedNeedsReindex: (chunks) =>
    `Model lain: semua ${chunks} chunk di-embed ulang sebelum dipakai. Pencarian tetap memakai model sekarang sampai selesai. Upload menunggu selama proses.`,
  embedSaveReindex: 'Ganti & re-index',
  embedConfirmTitle: 'Ganti model embedding?',
  embedConfirmBody: (chunks) =>
    `Semua ${chunks} chunk di-embed ulang dengan model baru. Tanpa panggilan LLM dan tanpa ingest ulang; dokumen tetap seperti sekarang. Kalau gagal, tidak ada yang berubah.`,
  embedProgress: (done, total) => `Re-index: ${done} dari ${total} dokumen`,
  embedDone: 'Re-index selesai. Pencarian sekarang memakai model baru.',
  embedFailed: (error) => `Re-index gagal, model sebelumnya tetap dipakai: ${error}`,
  dropActive: 'Lepas untuk mengunggah',

  emptyTitle: 'Analisis dokumen',
  emptyBody: 'Anda bisa bertanya begitu proses selesai; dokumen panjang juga mendapat daftar isi yang bisa dijelajahi.',

  modelLabel: 'Model',

  uploadButton: 'Unggah',
  uploadUploading: 'Mengunggah…',
  uploadLimitsCaption: (mb, pages, formats) => `${formats}. Maksimal ${mb} MB; PDF maksimal ${pages} halaman.`,
  uploadLimitsShort: (mb, pages) => `Maks. ${mb} MB, ${pages} halaman PDF`,
  uploadFormats: (formats) => `Format yang didukung: ${formats}`,
  uploadLimitsUnavailable: 'API tidak dapat dijangkau',

  statusQueued: 'Menunggu',
  statusConverting: 'Mengonversi',
  statusEmbedding: 'Membuat embedding',
  statusBuildingTree: 'Membangun daftar isi',
  statusExtractingGraph: 'Mengekstrak graf',
  statusDone: 'Siap',
  statusError: 'Gagal',

  modeShort: 'Pendek',
  modeLong: 'Panjang',

  deleteAction: 'Hapus',
  originalLink: 'Asli',
  deleteConfirmTitle: 'Hapus dokumen ini?',
  deleteConfirmBody: (name) =>
    `"${name}" beserta semua turunannya (chunk, daftar isi, riwayat chat) akan dihapus permanen.`,
  deleteConfirmConfirm: 'Hapus',
  deleteConfirmCancel: 'Batal',

  relativeJustNow: 'baru saja',

  errorGeneric: 'Terjadi kesalahan. Silakan coba lagi.',
  errorDetailsShow: 'Tampilkan detail',
  errorDetailsHide: 'Sembunyikan detail',

  docElapsedLabel: 'Berlalu',
  docEtaLabel: (eta) => `Sekitar ${eta} lagi`,
  docStepCount: (done, total) => `${done} / ${total}`,
  unitPages: 'halaman',
  unitChunks: 'chunk',
  unitSections: 'bagian',
  docErrorTitle: 'Proses gagal',
  docErrorReupload: 'Dokumen ini gagal diproses. Coba lagi, atau hapus dan unggah ulang berkas aslinya.',
  docRetry: 'Coba lagi',
  docRetrying: 'Memulai...',
  tabProcess: 'Proses',
  ocrPages: (scanned, pages) => `OCR aktif: ${scanned} dari ${pages} halaman tanpa lapisan teks`,
  ocrOff: 'OCR mati: semua halaman punya lapisan teks',
  stageTokensChunks: (tokens, chunks) => `${tokens} token dipecah menjadi ${chunks} chunk`,
  stageLanguage: (language) => `Bahasa: ${language}`,
  stageMode: (long, tokens, limit) => (long ? `Mode Panjang: ${tokens} > ${limit} token` : `Mode Pendek: ${tokens} ≤ ${limit} token`),
  stageEmbedded: (chunks) => `${chunks} chunk diubah menjadi vektor`,
  stageSummarized: (sections) => `${sections} bagian diringkas`,
  stageEntities: (entities, chunks) => `${entities} entitas ditemukan di ${chunks} chunk`,
  stageGraphSkipped: (chunks) => `${chunks} chunk dilewati: ekstraksi gagal`,
  stageSkipped: 'Dilewati: hanya untuk dokumen panjang',
  stageQueuedHint: 'Menunggu dokumen lain selesai dikonversi',
  stageFailed: 'Gagal di tahap ini',
  stageTotal: (duration) => `Total ${duration}`,

  chatPlaceholder: 'Tanya tentang dokumen ini',
  chatSend: 'Kirim',
  chatSending: 'Memikirkan…',
  chatFollowSources: 'Ikuti sumber',
  chatFoundSources: (n) => `Menemukan ${n} sumber`,
  chatEmptyTitle: 'Tanyakan apa saja tentang dokumen ini',
  chatEmpty: 'Setiap jawaban menyertakan kutipan sumbernya.',
  chatSuggestions: ['Ringkas dokumen ini', 'Apa temuan utamanya?', 'Sebutkan bagian utama dan isi masing-masing'],
  chatComposerHint: 'Enter untuk kirim, Shift + Enter untuk baris baru',
  chatClear: 'Hapus riwayat',
  chatClearConfirmTitle: 'Hapus riwayat chat?',
  chatClearConfirmBody: 'Semua pertanyaan dan jawaban untuk dokumen ini akan dihapus permanen.',
  chatInterrupted: 'Terputus sebelum selesai',
  chatStatusContextualize: 'Memahami pertanyaan…',
  chatStatusVectorRetrieve: 'Mencari di dokumen…',
  chatStatusTreeSearch: 'Membaca daftar isi…',
  chatStatusKgRetrieve: 'Membaca graf pengetahuan…',

  citationTitle: (n) => `Sumber ${n}`,
  citationSource: 'Ditemukan lewat',
  citationPages: 'Halaman',
  citationHeadings: 'Bagian',
  citationSourceVector: 'Pencarian vektor',
  citationSourceTree: 'Daftar isi dokumen',
  citationSourceKg: 'Bukti graf pengetahuan',
  citationSourceKgFacts: 'Fakta graf pengetahuan',
  citationClose: 'Tutup',
  citationPageOf: (i, n) => `Halaman ${i} dari ${n}`,
  citationPrevPage: 'Halaman sebelumnya',
  citationNextPage: 'Halaman berikutnya',
  viewerOpen: 'Lihat dokumen',
  viewerZoomIn: 'Perbesar',
  viewerZoomOut: 'Perkecil',
  viewerGoToPage: 'Ke halaman',
  viewerCitationOf: (i, n) => `Sitasi ${i} dari ${n}`,
  viewerPrevCitation: 'Sitasi sebelumnya',
  viewerNextCitation: 'Sitasi berikutnya',
  viewerSlide: (n) => `Slide ${n}`,

  tabChat: 'Chat',
  tabOutline: 'Daftar Isi',
  outlineEmpty: 'Tidak ada daftar isi untuk dokumen ini.',
  outlineSelectSection: 'Pilih bagian untuk membacanya.',
  outlinePageRange: (start, end) => (start === end ? `hal. ${start}` : `hal. ${start}-${end}`),
  outlineChunkCount: (n) => `${n} chunk`,
  outlineChunksEmpty: 'Bagian ini tidak punya teks sendiri. Isinya ada di sub-bagian.',

  tabGraph: 'Graf',
  graphEmpty: 'Dokumen ini tidak punya graf pengetahuan.',
  graphSearch: 'Cari entitas...',
  graphShowing: (shown, total) => `Menampilkan ${shown} dari ${total} entitas`,
  graphMentions: (n) => `Disebut di ${n} bagian`,
  graphRelations: 'Relasi',
  graphNoRelations: 'Tidak ada relasi ke entitas lain.',
  graphEvidence: 'Disebut di mana',
  graphHint: 'Seret untuk menggeser, gulir untuk zoom, klik entitas untuk menjelajah.',
  graphFit: 'Paskan ke layar',
  graphTypes: {
    Person: 'Orang', Organization: 'Organisasi', Location: 'Lokasi', Concept: 'Konsep',
    Event: 'Peristiwa', Product: 'Produk', Regulation: 'Regulasi', Date: 'Tanggal / nilai',
  },

};

const dictionaries = { en, id } as const;
export type Lang = keyof typeof dictionaries;

const STORAGE_KEY = 'docs-analyzer:lang';

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'id') return stored;
  } catch {
    // localStorage unavailable (private mode, etc.): fall through to default
  }
  return 'en';
}

interface LangContextValue {
  lang: Lang;
  setLang: (lang: Lang) => void;
  t: Dict;
}

const LangContext = createContext<LangContextValue | null>(null);

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);

  const setLang = (next: Lang) => {
    setLangState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
    }
  };

  const value = useMemo(() => ({ lang, setLang, t: dictionaries[lang] }), [lang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang(): LangContextValue {
  const ctx = useContext(LangContext);
  if (!ctx) throw new Error('useLang must be used within LangProvider');
  return ctx;
}
