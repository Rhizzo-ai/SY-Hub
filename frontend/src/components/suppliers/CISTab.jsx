/**
 * <CISTab/> — Chat 40 §R3 #12 / §R4.4.
 *
 * Three stacked sections:
 *   1. Current-status banner — useCurrentVerification(supplierId)
 *   2. History table         — useVerifications(supplierId)
 *   3. Record-verification form (iff cis.verify)
 *
 * Append-only: no edit/delete affordances on history rows.
 * Backend orders verifications newest-first.
 */
import React, { useState } from 'react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';

import { useAuth } from '@/context/AuthContext';
import {
  useCurrentVerification, useVerifications, useRecordVerification,
} from '@/hooks/cis';
import {
  canViewSensitiveCIS, canVerifyCIS,
} from '@/lib/poCapability';
import SensitiveValue from '@/components/po/SensitiveValue';
import CISStatusBadge from '@/components/suppliers/CISStatusBadge';
import { formatDate, MATCH_STATUS_LABEL } from '@/lib/cisFormat';

const MATCH_STATUS_OPTIONS = ['Gross', 'Net', 'Unmatched']; // §R1: never Unverified

function emptyForm() {
  return {
    match_status: 'Gross',
    tax_rate_pct: '',
    verified_on: new Date().toISOString().slice(0, 10),
    expires_on: '',
    verification_number: '',
    notes: '',
  };
}

export default function CISTab({ supplierId }) {
  const { me } = useAuth();
  const canVerify = canVerifyCIS(me);
  const canSensitive = canViewSensitiveCIS(me);

  const current = useCurrentVerification(supplierId);
  const history = useVerifications(supplierId);
  const record = useRecordVerification(supplierId);

  const [form, setForm] = useState(emptyForm());
  const [submitting, setSubmitting] = useState(false);
  const onChange = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const onSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const payload = {
        match_status: form.match_status,
        verified_on: form.verified_on, // required
      };
      if (form.tax_rate_pct !== '') payload.tax_rate_pct = String(form.tax_rate_pct);
      if (form.expires_on) payload.expires_on = form.expires_on;
      if (form.verification_number) payload.verification_number = form.verification_number;
      if (form.notes) payload.notes = form.notes;
      await record.mutateAsync(payload);
      toast.success('Verification recorded');
      setForm(emptyForm());
    } catch (err) {
      // §R4.4 — 409 (non-subcontractor) is a defensive edge; tab only
      // renders for subcontractors. Surface the detail either way.
      const detail = err?.response?.data?.detail ?? err?.message ?? 'Save failed';
      toast.error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    } finally {
      setSubmitting(false);
    }
  };

  const currentRow = current.data;
  const rows = history.data?.items ?? [];

  return (
    <div className="space-y-6" data-testid="cis-tab">
      {/* Current-status banner */}
      <section
        className="p-3 border rounded flex items-center gap-3"
        data-testid="cis-current-banner"
      >
        <CISStatusBadge
          status={currentRow?.match_status ?? null}
          testid="cis-current-badge"
        />
        <div className="text-sm">
          {currentRow
            ? <>Verified <strong>{formatDate(currentRow.verified_on)}</strong></>
            : <span className="text-sy-grey-600">No verification on record</span>}
        </div>
      </section>

      {/* History */}
      <section data-testid="cis-history-section">
        <h3 className="text-sm font-semibold mb-2">Verification history</h3>
        {history.isLoading && <div className="text-sm" data-testid="cis-history-loading">Loading…</div>}
        {history.isError && <div className="text-sm text-red-600">Failed to load verifications.</div>}
        {!history.isLoading && !history.isError && (
          <Table data-testid="cis-history-table">
            <TableHeader>
              <TableRow>
                <TableHead>Verified on</TableHead>
                <TableHead>Match status</TableHead>
                <TableHead>Tax rate %</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Verification #</TableHead>
                <TableHead>Notes</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-sy-grey-500" data-testid="cis-history-empty">
                    No verifications recorded.
                  </TableCell>
                </TableRow>
              )}
              {rows.map((v) => (
                <TableRow key={v.id} data-testid={`cis-history-row-${v.id}`}>
                  <TableCell>{formatDate(v.verified_on)}</TableCell>
                  <TableCell>
                    <Badge variant={
                      v.match_status === 'Gross' ? 'default'
                      : v.match_status === 'Net' ? 'secondary'
                      : 'destructive'
                    }>
                      {MATCH_STATUS_LABEL[v.match_status] ?? v.match_status}
                    </Badge>
                  </TableCell>
                  <TableCell className="tabular-nums">{v.tax_rate_pct ?? '—'}</TableCell>
                  <TableCell>{formatDate(v.expires_on)}</TableCell>
                  <TableCell>
                    <SensitiveValue
                      value={v.verification_number}
                      hidden={!canSensitive}
                      testid={`cis-history-vnum-${v.id}`}
                    />
                  </TableCell>
                  <TableCell className="max-w-xs truncate">{v.notes ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>

      {/* Record-verification form */}
      {canVerify && (
        <section data-testid="cis-record-section">
          <h3 className="text-sm font-semibold mb-2">Record verification</h3>
          <form onSubmit={onSubmit} className="space-y-3 max-w-xl" data-testid="cis-record-form">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="cis-form-match">Match status *</Label>
                <select
                  id="cis-form-match"
                  className="w-full px-2 py-1.5 border rounded text-sm"
                  value={form.match_status} onChange={onChange('match_status')}
                  data-testid="cis-record-match"
                  required
                >
                  {MATCH_STATUS_OPTIONS.map((s) => (
                    <option key={s} value={s}>{MATCH_STATUS_LABEL[s]}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="cis-form-tax">Tax rate %</Label>
                <Input
                  id="cis-form-tax" type="number" min="0" max="100" step="0.01"
                  value={form.tax_rate_pct} onChange={onChange('tax_rate_pct')}
                  data-testid="cis-record-tax"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="cis-form-verified">Verified on *</Label>
                <Input
                  id="cis-form-verified" type="date" required
                  value={form.verified_on} onChange={onChange('verified_on')}
                  data-testid="cis-record-verified-on"
                />
              </div>
              <div>
                <Label htmlFor="cis-form-expires">Expires on</Label>
                <Input
                  id="cis-form-expires" type="date"
                  value={form.expires_on} onChange={onChange('expires_on')}
                  data-testid="cis-record-expires-on"
                />
              </div>
            </div>
            <div>
              <Label htmlFor="cis-form-vnum">Verification number</Label>
              <Input
                id="cis-form-vnum" type="text"
                value={form.verification_number} onChange={onChange('verification_number')}
                data-testid="cis-record-vnum"
              />
            </div>
            <div>
              <Label htmlFor="cis-form-notes">Notes</Label>
              <Textarea
                id="cis-form-notes" rows={2}
                value={form.notes} onChange={onChange('notes')}
                data-testid="cis-record-notes"
              />
            </div>
            <Button
              type="submit" disabled={submitting}
              data-testid="cis-record-submit"
            >
              {submitting ? 'Saving…' : 'Record verification'}
            </Button>
          </form>
        </section>
      )}
    </div>
  );
}
