import { createContext, useContext, useMemo, useState, type ReactNode } from 'react';

// Explicit shape (not inferred from `en` with `as const`) so `id`'s values can differ from
// `en`'s while TypeScript still requires every key to be present: a missing Indonesian
// string is a build error, not a silent fallback to English.
export interface Dict {
  appName: string;
  langEnglish: string;
  langIndonesian: string;

  railDocuments: string;
  railCollapse: string;
  railExpand: string;
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
  citationSourceTable: string;
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

  tabTable: string;
  tableIntro: string;
  tablePlaceholder: string;
  tableProposeAction: string;
  tableSuggestAction: string;
  tableSuggesting: string;
  tableSuggestionsTitle: string;
  tableSuggestionsEmpty: string;
  tableProposing: string;
  tableColumnsTitle: string;
  tableColumnName: string;
  tableColumnDescription: string;
  tableColumnAdd: string;
  tableColumnRemove: string;
  tableRunAction: string;
  tableRunningTitle: string;
  tableRunningHint: string;
  tableProgress: (percent: number) => string;
  tableRowCount: (n: number) => string;
  tableCitationsLabel: string;
  tableNothingFound: string;
  tableErrorTitle: string;
  tableRetry: string;
  tableHistoryTitle: string;
  tableNewAction: string;
  tableStatusQueued: string;
  tableStatusRunning: string;
  tableStatusDone: string;
  tableStatusError: string;
  tableStatusCancelled: string;
  tableCancelAction: string;
  tableCancelledNotice: string;
  tableReadScope: (parts: number, chunks: number, total: number) => string;
  tableReadAll: string;
  tableExportAction: string;
  tableDeleteAction: string;
  tableDeleteConfirmTitle: string;
  tableDeleteConfirmBody: (request: string) => string;
  tableRowDelete: string;
}

const en: Dict = {
  appName: 'Docs Analyzer',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  railDocuments: 'Documents',
  railCollapse: 'Hide sidebar',
  railExpand: 'Show sidebar',
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
  citationSourceTable: 'Table extraction',
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

  tabTable: 'Table',
  tableIntro: 'Describe what to pull out of this document, and the columns are proposed for you to edit.',
  tablePlaceholder: 'e.g. every obligation, its due date and amount',
  tableProposeAction: 'Propose columns',
  tableSuggestAction: 'Suggest tables from this document',
  tableSuggesting: 'Reading the document...',
  tableSuggestionsTitle: 'Tables worth pulling out of this document',
  tableSuggestionsEmpty: 'No table suggested itself from this document. Describe one yourself above.',
  tableProposing: 'Proposing columns...',
  tableColumnsTitle: 'Columns',
  tableColumnName: 'Name',
  tableColumnDescription: 'What belongs in this column',
  tableColumnAdd: 'Add column',
  tableColumnRemove: 'Remove',
  tableRunAction: 'Run table extraction',
  tableRunningTitle: 'Reading every chunk of the document',
  tableRunningHint: 'This takes a while. You can leave this tab; the run keeps going.',
  tableProgress: (percent) => `${percent}% read`,
  tableRowCount: (n) => `${n} row${n === 1 ? '' : 's'}`,
  tableCitationsLabel: 'Citations',
  tableNothingFound: 'Nothing in this document matched these columns.',
  tableErrorTitle: 'The table extraction failed',
  tableRetry: 'Run again',
  tableHistoryTitle: 'Earlier table extractions',
  tableNewAction: 'New table',
  tableStatusQueued: 'Queued',
  tableStatusRunning: 'Running',
  tableStatusDone: 'Done',
  tableStatusError: 'Failed',
  tableStatusCancelled: 'Stopped',
  tableCancelAction: 'Stop',
  tableCancelledNotice: 'You stopped this run, so it has no rows. Its columns are kept.',
  tableReadScope: (parts, chunks, total) =>
    `Read only the ${parts === 1 ? 'part' : `${parts} parts`} that answer the request (${chunks} of ${total} passages):`,
  tableReadAll: 'Read the whole document instead',
  tableExportAction: 'Export XLSX',
  tableDeleteAction: 'Delete table',
  tableDeleteConfirmTitle: 'Delete this table extraction?',
  tableDeleteConfirmBody: (request) => `"${request}" and all of its rows will be deleted. This cannot be undone.`,
  tableRowDelete: 'Delete row',
};

const id: Dict = {
  appName: 'Docs Analyzer',
  langEnglish: 'EN',
  langIndonesian: 'ID',

  railDocuments: 'Dokumen',
  railCollapse: 'Sembunyikan panel',
  railExpand: 'Tampilkan panel',
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
  citationSourceTable: 'Ekstraksi tabel',
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

  tabTable: 'Tabel',
  tableIntro: 'Jelaskan apa yang ingin diambil dari dokumen ini, lalu kolomnya diusulkan untuk Anda sunting.',
  tablePlaceholder: 'mis. setiap kewajiban, tenggat, dan nilainya',
  tableProposeAction: 'Usulkan kolom',
  tableSuggestAction: 'Sarankan tabel dari dokumen ini',
  tableSuggesting: 'Membaca dokumen...',
  tableSuggestionsTitle: 'Tabel yang layak diambil dari dokumen ini',
  tableSuggestionsEmpty: 'Tidak ada tabel yang tersarankan dari dokumen ini. Jelaskan sendiri di atas.',
  tableProposing: 'Menyusun kolom...',
  tableColumnsTitle: 'Kolom',
  tableColumnName: 'Nama',
  tableColumnDescription: 'Isi kolom ini',
  tableColumnAdd: 'Tambah kolom',
  tableColumnRemove: 'Hapus',
  tableRunAction: 'Jalankan ekstraksi tabel',
  tableRunningTitle: 'Membaca seluruh bagian dokumen',
  tableRunningHint: 'Proses ini lama. Anda boleh meninggalkan tab ini; ekstraksi tetap berjalan.',
  tableProgress: (percent) => `${percent}% terbaca`,
  tableRowCount: (n) => `${n} baris`,
  tableCitationsLabel: 'Kutipan',
  tableNothingFound: 'Tidak ada isi dokumen yang cocok dengan kolom ini.',
  tableErrorTitle: 'Ekstraksi tabel gagal',
  tableRetry: 'Jalankan lagi',
  tableHistoryTitle: 'Ekstraksi tabel sebelumnya',
  tableNewAction: 'Tabel baru',
  tableStatusQueued: 'Antre',
  tableStatusRunning: 'Berjalan',
  tableStatusDone: 'Selesai',
  tableStatusError: 'Gagal',
  tableStatusCancelled: 'Dihentikan',
  tableCancelAction: 'Hentikan',
  tableCancelledNotice: 'Run ini Anda hentikan, jadi tidak ada baris. Kolomnya tetap disimpan.',
  tableReadScope: (parts, chunks, total) =>
    `Hanya membaca ${parts} bagian yang menjawab permintaan (${chunks} dari ${total} potongan):`,
  tableReadAll: 'Baca seluruh dokumen',
  tableExportAction: 'Ekspor XLSX',
  tableDeleteAction: 'Hapus tabel',
  tableDeleteConfirmTitle: 'Hapus ekstraksi tabel ini?',
  tableDeleteConfirmBody: (request) => `"${request}" beserta semua barisnya akan dihapus. Tindakan ini tidak bisa dibatalkan.`,
  tableRowDelete: 'Hapus baris',
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
