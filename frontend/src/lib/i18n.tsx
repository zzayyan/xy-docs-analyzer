import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

// Explicit shape (not inferred from `en` with `as const`) so `id`'s values can differ from
// `en`'s while TypeScript still requires every key to be present — a missing Indonesian
// string is a build error, not a silent fallback to English.
export interface Dict {
  appName: string;
  navDocuments: string;
  langEnglish: string;
  langIndonesian: string;

  uploadTitle: string;
  uploadButton: string;
  uploadUploading: string;
  uploadLimitsCaption: (mb: number, pages: number) => string;
  uploadLimitsUnavailable: string;

  tableName: string;
  tableStatus: string;
  tableMode: string;
  tableProgress: string;
  tableUploaded: string;
  tableActions: string;
  tableEmpty: string;

  statusQueued: string;
  statusConverting: string;
  statusEmbedding: string;
  statusBuildingTree: string;
  statusExtractingGraph: string;
  statusDone: string;
  statusError: string;

  modeShort: string;
  modeLong: string;
  modeUnknown: string;

  deleteAction: string;
  deleteConfirmTitle: string;
  deleteConfirmBody: (name: string) => string;
  deleteConfirmConfirm: string;
  deleteConfirmCancel: string;

  relativeJustNow: string;

  errorGeneric: string;
  errorDetailsShow: string;
  errorDetailsHide: string;

  docsCount: (n: number) => string;
  docsFailedSummary: (n: number) => string;
  uploadDropHint: string;

  docBackToList: string;
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
  chatEmpty: string;
  chatTurnCount: (n: number) => string;
  chatClear: string;
  chatClearConfirmTitle: string;
  chatClearConfirmBody: string;
  chatInterrupted: string;
  chatStatusVectorRetrieve: string;
  chatStatusTreeSearch: string;
  chatStatusKgRetrieve: string;

  citationTitle: (n: number) => string;
  citationPages: string;
  citationHeadings: string;
  citationSourceVector: string;
  citationSourceTree: string;
  citationSourceKg: string;
  citationSourceKgFacts: string;
  citationClose: string;
  citationNone: string;

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
  navDocuments: 'Documents',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  uploadTitle: 'Upload a document',
  uploadButton: 'Upload',
  uploadUploading: 'Uploading…',
  uploadLimitsCaption: (mb: number, pages: number) =>
    `Limit ${mb} MB, and ${pages} pages for PDF. Other formats are not page-limited.`,
  uploadLimitsUnavailable: 'API not reachable',

  tableName: 'Document',
  tableStatus: 'Status',
  tableMode: 'Mode',
  tableProgress: 'Progress',
  tableUploaded: 'Uploaded',
  tableActions: 'Actions',
  tableEmpty: 'No documents yet. Upload one to get started.',

  statusQueued: 'Queued',
  statusConverting: 'Converting',
  statusEmbedding: 'Embedding',
  statusBuildingTree: 'Building outline',
  statusExtractingGraph: 'Extracting graph',
  statusDone: 'Done',
  statusError: 'Error',

  modeShort: 'Short',
  modeLong: 'Long',
  modeUnknown: '—',

  deleteAction: 'Delete',
  deleteConfirmTitle: 'Delete this document?',
  deleteConfirmBody: (name: string) =>
    `"${name}" and everything derived from it — chunks, outline, chat history — will be permanently removed. This cannot be undone.`,
  deleteConfirmConfirm: 'Delete',
  deleteConfirmCancel: 'Cancel',

  relativeJustNow: 'just now',

  errorGeneric: 'Something went wrong. Please try again.',
  errorDetailsShow: 'Show details',
  errorDetailsHide: 'Hide details',

  docsCount: (n) => (n === 1 ? '1 document' : `${n} documents`),
  docsFailedSummary: (n) => (n === 1 ? '1 document failed to process.' : `${n} documents failed to process.`),
  uploadDropHint: 'Drag a file here, or',

  docBackToList: '← Back to documents',
  docElapsedLabel: 'Elapsed',
  docEtaLabel: (eta) => `~${eta} remaining`,
  docStepCount: (done, total) => `${done} / ${total}`,
  unitPages: 'pages',
  unitChunks: 'chunks',
  unitSections: 'sections',
  docErrorTitle: 'Ingest failed',
  docErrorReupload: 'This document could not be processed. Delete it and upload the original file again.',

  chatPlaceholder: 'Ask about this document…',
  chatSend: 'Send',
  chatSending: 'Thinking…',
  chatEmpty: 'No questions yet. Ask something about this document.',
  chatTurnCount: (n) => (n === 1 ? '1 question asked' : `${n} questions asked`),
  chatClear: 'Clear chat',
  chatClearConfirmTitle: 'Clear chat history?',
  chatClearConfirmBody: 'All questions and answers for this document will be permanently removed.',
  chatInterrupted: 'Interrupted',
  chatStatusVectorRetrieve: 'Searching the document…',
  chatStatusTreeSearch: 'Reading the outline…',
  chatStatusKgRetrieve: 'Reading the knowledge graph…',

  citationTitle: (n) => `Source [${n}]`,
  citationPages: 'Pages',
  citationHeadings: 'Section',
  citationSourceVector: 'Vector search',
  citationSourceTree: 'Document outline',
  citationSourceKg: 'Knowledge graph evidence',
  citationSourceKgFacts: 'Knowledge graph facts',
  citationClose: 'Close',
  citationNone: '—',

  tabChat: 'Chat',
  tabOutline: 'Outline',
  outlineEmpty: 'No outline available for this document.',
  outlineSelectSection: 'Select a section to view its content.',
  outlinePageRange: (start, end) => (start === end ? `p. ${start}` : `p. ${start}–${end}`),
  outlineChunkCount: (n) => `${n} chunk${n === 1 ? '' : 's'}`,
  outlineChunksEmpty: 'This section has no text of its own — see its subsections.',
};

const id: Dict = {
  appName: 'Docs Analyzer',
  navDocuments: 'Dokumen',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  uploadTitle: 'Unggah dokumen',
  uploadButton: 'Unggah',
  uploadUploading: 'Mengunggah…',
  uploadLimitsCaption: (mb: number, pages: number) =>
    `Batas ${mb} MB, dan ${pages} halaman untuk PDF. Format lain tidak dibatasi jumlah halaman.`,
  uploadLimitsUnavailable: 'API tidak dapat dijangkau',

  tableName: 'Dokumen',
  tableStatus: 'Status',
  tableMode: 'Mode',
  tableProgress: 'Progres',
  tableUploaded: 'Diunggah',
  tableActions: 'Aksi',
  tableEmpty: 'Belum ada dokumen. Unggah satu untuk memulai.',

  statusQueued: 'Menunggu',
  statusConverting: 'Mengonversi',
  statusEmbedding: 'Membuat embedding',
  statusBuildingTree: 'Membangun outline',
  statusExtractingGraph: 'Mengekstrak graf',
  statusDone: 'Selesai',
  statusError: 'Gagal',

  modeShort: 'Pendek',
  modeLong: 'Panjang',
  modeUnknown: '—',

  deleteAction: 'Hapus',
  deleteConfirmTitle: 'Hapus dokumen ini?',
  deleteConfirmBody: (name: string) =>
    `"${name}" beserta semua turunannya — chunk, outline, riwayat chat — akan dihapus permanen. Tindakan ini tidak dapat dibatalkan.`,
  deleteConfirmConfirm: 'Hapus',
  deleteConfirmCancel: 'Batal',

  relativeJustNow: 'baru saja',

  errorGeneric: 'Terjadi kesalahan. Silakan coba lagi.',
  errorDetailsShow: 'Tampilkan detail',
  errorDetailsHide: 'Sembunyikan detail',

  docsCount: (n) => (n === 1 ? '1 dokumen' : `${n} dokumen`),
  docsFailedSummary: (n) => (n === 1 ? '1 dokumen gagal diproses.' : `${n} dokumen gagal diproses.`),
  uploadDropHint: 'Seret berkas ke sini, atau',

  docBackToList: '← Kembali ke daftar dokumen',
  docElapsedLabel: 'Berlalu',
  docEtaLabel: (eta) => `~${eta} lagi`,
  docStepCount: (done, total) => `${done} / ${total}`,
  unitPages: 'halaman',
  unitChunks: 'chunk',
  unitSections: 'bagian',
  docErrorTitle: 'Proses gagal',
  docErrorReupload: 'Dokumen ini gagal diproses. Hapus dan unggah ulang berkas aslinya.',

  chatPlaceholder: 'Tanya tentang dokumen ini…',
  chatSend: 'Kirim',
  chatSending: 'Memikirkan…',
  chatEmpty: 'Belum ada pertanyaan. Tanyakan sesuatu tentang dokumen ini.',
  chatTurnCount: (n) => (n === 1 ? '1 pertanyaan diajukan' : `${n} pertanyaan diajukan`),
  chatClear: 'Hapus riwayat',
  chatClearConfirmTitle: 'Hapus riwayat chat?',
  chatClearConfirmBody: 'Semua pertanyaan dan jawaban untuk dokumen ini akan dihapus permanen.',
  chatInterrupted: 'Terputus',
  chatStatusVectorRetrieve: 'Mencari di dokumen…',
  chatStatusTreeSearch: 'Membaca outline…',
  chatStatusKgRetrieve: 'Membaca graf pengetahuan…',

  citationTitle: (n) => `Sumber [${n}]`,
  citationPages: 'Halaman',
  citationHeadings: 'Bagian',
  citationSourceVector: 'Pencarian vektor',
  citationSourceTree: 'Outline dokumen',
  citationSourceKg: 'Bukti graf pengetahuan',
  citationSourceKgFacts: 'Fakta graf pengetahuan',
  citationClose: 'Tutup',
  citationNone: '—',

  tabChat: 'Chat',
  tabOutline: 'Daftar Isi',
  outlineEmpty: 'Tidak ada outline untuk dokumen ini.',
  outlineSelectSection: 'Pilih bagian untuk melihat isinya.',
  outlinePageRange: (start, end) => (start === end ? `hal. ${start}` : `hal. ${start}–${end}`),
  outlineChunkCount: (n) => `${n} chunk`,
  outlineChunksEmpty: 'Bagian ini tidak punya teks sendiri — lihat sub-bagiannya.',
};

const dictionaries = { en, id } as const;
export type Lang = keyof typeof dictionaries;

const STORAGE_KEY = 'docs-analyzer:lang';

function initialLang(): Lang {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === 'en' || stored === 'id') return stored;
  } catch {
    // localStorage unavailable (private mode, etc.) — fall through to default
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
