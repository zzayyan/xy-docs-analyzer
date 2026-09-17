import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

// Explicit shape (not inferred from `en` with `as const`) so `id`'s values can differ from
// `en`'s while TypeScript still requires every key to be present: a missing Indonesian
// string is a build error, not a silent fallback to English.
export interface Dict {
  appName: string;
  langEnglish: string;
  langIndonesian: string;

  railDocuments: string;
  railEmpty: string;
  dropActive: string;

  emptyTitle: string;
  emptyBody: string;

  modelLabel: string;

  uploadButton: string;
  uploadUploading: string;
  uploadLimitsCaption: (mb: number, pages: number) => string;
  uploadLimitsShort: (mb: number, pages: number) => string;
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

  chatPlaceholder: string;
  chatSend: string;
  chatSending: string;
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

  tabChat: string;
  tabOutline: string;
  outlineEmpty: string;
  outlineSelectSection: string;
  outlinePageRange: (start: number, end: number) => string;
  outlineChunkCount: (n: number) => string;
  outlineChunksEmpty: string;
}

const en: Dict = {
  appName: 'Docs Analyzer',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  railDocuments: 'Documents',
  railEmpty: 'No documents yet. Upload one to start.',
  dropActive: 'Drop to upload',

  emptyTitle: 'Analyze a document',
  emptyBody: 'Ask questions as soon as processing finishes; long documents also get a browsable outline.',

  modelLabel: 'Model',

  uploadButton: 'Upload',
  uploadUploading: 'Uploading…',
  uploadLimitsCaption: (mb, pages) => `Up to ${mb} MB. PDFs up to ${pages} pages.`,
  uploadLimitsShort: (mb, pages) => `${mb} MB, ${pages} PDF pages max`,
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
  docErrorReupload: 'This document could not be processed. Delete it and upload the original file again.',

  chatPlaceholder: 'Ask about this document',
  chatSend: 'Send',
  chatSending: 'Thinking…',
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

  tabChat: 'Chat',
  tabOutline: 'Outline',
  outlineEmpty: 'No outline available for this document.',
  outlineSelectSection: 'Select a section to read it.',
  outlinePageRange: (start, end) => (start === end ? `p. ${start}` : `p. ${start}-${end}`),
  outlineChunkCount: (n) => `${n} chunk${n === 1 ? '' : 's'}`,
  outlineChunksEmpty: 'This section has no text of its own. Its subsections hold the content.',
};

const id: Dict = {
  appName: 'Docs Analyzer',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  railDocuments: 'Dokumen',
  railEmpty: 'Belum ada dokumen. Unggah satu untuk mulai.',
  dropActive: 'Lepas untuk mengunggah',

  emptyTitle: 'Analisis dokumen',
  emptyBody: 'Anda bisa bertanya begitu proses selesai; dokumen panjang juga mendapat daftar isi yang bisa dijelajahi.',

  modelLabel: 'Model',

  uploadButton: 'Unggah',
  uploadUploading: 'Mengunggah…',
  uploadLimitsCaption: (mb, pages) => `Maksimal ${mb} MB. PDF maksimal ${pages} halaman.`,
  uploadLimitsShort: (mb, pages) => `Maks. ${mb} MB, ${pages} halaman PDF`,
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
  docErrorReupload: 'Dokumen ini gagal diproses. Hapus dan unggah ulang berkas aslinya.',

  chatPlaceholder: 'Tanya tentang dokumen ini',
  chatSend: 'Kirim',
  chatSending: 'Memikirkan…',
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

  tabChat: 'Chat',
  tabOutline: 'Daftar Isi',
  outlineEmpty: 'Tidak ada daftar isi untuk dokumen ini.',
  outlineSelectSection: 'Pilih bagian untuk membacanya.',
  outlinePageRange: (start, end) => (start === end ? `hal. ${start}` : `hal. ${start}-${end}`),
  outlineChunkCount: (n) => `${n} chunk`,
  outlineChunksEmpty: 'Bagian ini tidak punya teks sendiri. Isinya ada di sub-bagian.',
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
      // best-effort persistence only
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
