import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Badge, Button, Pill, Textarea } from '../design-system';
import { ConfirmDialog } from './ConfirmDialog';
import { Drawer } from './Drawer';
import { MessageBody } from './MessageBody';
import { Toast } from './Toast';
import { api, ApiError, type Citation, type Turn } from '../lib/api';
import { useLang } from '../lib/i18n';

const SOURCE_LABEL_KEY = {
  vector: 'citationSourceVector',
  tree: 'citationSourceTree',
  kg: 'citationSourceKg',
  kg_facts: 'citationSourceKgFacts',
} as const;

export function ChatPanel({ docId }: { docId: string }) {
  const { t } = useLang();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState('');
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [confirmClear, setConfirmClear] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const turnsQuery = useQuery({ queryKey: ['turns', docId], queryFn: () => api.listTurns(docId) });

  const sendMutation = useMutation({
    mutationFn: (question: string) => api.chat(docId, question),
    onSuccess: () => {
      setDraft('');
      queryClient.invalidateQueries({ queryKey: ['turns', docId] });
    },
    onError: (error: unknown) => setToast(error instanceof ApiError ? error.detail : t.errorGeneric),
  });

  const clearMutation = useMutation({
    mutationFn: () => api.clearTurns(docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['turns', docId] });
      setConfirmClear(false);
    },
    onError: (error: unknown) => {
      setToast(error instanceof ApiError ? error.detail : t.errorGeneric);
      setConfirmClear(false);
    },
  });

  const send = () => {
    const question = draft.trim();
    if (question && !sendMutation.isPending) sendMutation.mutate(question);
  };

  const turns = turnsQuery.data ?? [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)', height: '100%' }}>
      {turns.length > 0 && (
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button variant="ghost" size="sm" onClick={() => setConfirmClear(true)}>
            {t.chatClear}
          </Button>
        </div>
      )}

      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        {turns.length === 0 && !turnsQuery.isPending ? (
          <p style={{ margin: 'var(--space-8) 0', textAlign: 'center', color: 'var(--text-muted)', fontSize: 'var(--fs-ui-sm)' }}>
            {t.chatEmpty}
          </p>
        ) : (
          turns.map((turn) => <TurnBubbles key={turn.id} turn={turn} onCitationClick={setSelectedCitation} />)
        )}
      </div>

      <div style={{ flex: '0 0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <Textarea
          placeholder={t.chatPlaceholder}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={2}
          disabled={sendMutation.isPending}
        />
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Button onClick={send} disabled={sendMutation.isPending || !draft.trim()}>
            {sendMutation.isPending ? t.chatSending : t.chatSend}
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={confirmClear}
        title={t.chatClearConfirmTitle}
        body={t.chatClearConfirmBody}
        danger
        onConfirm={() => clearMutation.mutate()}
        onCancel={() => setConfirmClear(false)}
      />

      <Drawer open={selectedCitation !== null} onClose={() => setSelectedCitation(null)} title={selectedCitation ? t.citationTitle(selectedCitation.n) : ''}>
        {selectedCitation && <CitationDetail citation={selectedCitation} />}
      </Drawer>

      {toast && <Toast message={toast} onDismiss={() => setToast(null)} />}
    </div>
  );
}

function TurnBubbles({ turn, onCitationClick }: { turn: Turn; onCitationClick: (c: Citation) => void }) {
  const { t } = useLang();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div
        style={{
          alignSelf: 'flex-end',
          maxWidth: '78%',
          background: 'var(--xy-red-700)',
          color: '#fff',
          borderRadius: 'var(--radius-md)',
          padding: '14px 18px',
          fontSize: 'var(--fs-ui-md)',
          whiteSpace: 'pre-wrap',
        }}
      >
        {turn.question}
      </div>
      <div
        style={{
          alignSelf: 'flex-start',
          maxWidth: '90%',
          background: 'var(--surface-card)',
          border: 'var(--stroke-hairline) solid var(--border-subtle)',
          borderRadius: 'var(--radius-md)',
          padding: '14px 18px',
          fontSize: 'var(--fs-ui-md)',
          lineHeight: 'var(--lh-body)',
          color: 'var(--text-body)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
        }}
      >
        {!turn.complete && <Badge tone="brand">{t.chatInterrupted}</Badge>}
        <MessageBody text={turn.answer} citations={turn.citations} onCitationClick={onCitationClick} />
        {turn.citations.length > 0 && (
          <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap', marginTop: 'var(--space-2)' }}>
            {turn.citations.map((c) => (
              <Pill key={c.n} size="sm" tone="soft" style={{ cursor: 'pointer' }}>
                <span onClick={() => onCitationClick(c)}>[{c.n}]</span>
              </Pill>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function CitationDetail({ citation }: { citation: Citation }) {
  const { t } = useLang();
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <Badge tone="neutral">{t[SOURCE_LABEL_KEY[citation.source]]}</Badge>
      <div>
        <div style={{ fontSize: 'var(--fs-ui-xs)', letterSpacing: 'var(--ls-caps)', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>
          {t.citationPages}
        </div>
        <div style={{ fontSize: 'var(--fs-ui-sm)', color: 'var(--text-body)' }}>
          {citation.pages.length > 0 ? citation.pages.join(', ') : t.citationNone}
        </div>
      </div>
      {citation.headings.length > 0 && (
        <div>
          <div style={{ fontSize: 'var(--fs-ui-xs)', letterSpacing: 'var(--ls-caps)', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: 4 }}>
            {t.citationHeadings}
          </div>
          <div style={{ fontSize: 'var(--fs-ui-sm)', color: 'var(--text-body)' }}>{citation.headings.join(' › ')}</div>
        </div>
      )}
      <div
        style={{
          fontSize: 'var(--fs-ui-sm)',
          lineHeight: 'var(--lh-body)',
          color: 'var(--text-body)',
          whiteSpace: 'pre-wrap',
          background: 'var(--surface-subtle)',
          border: 'var(--stroke-hairline) solid var(--border-subtle)',
          borderRadius: 'var(--radius-sm)',
          padding: 'var(--space-4)',
        }}
      >
        {citation.text}
      </div>
    </div>
  );
}
