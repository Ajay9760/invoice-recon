import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Api, UploadResult, ReconcileResult } from '../api';

@Component({
  selector: 'app-upload',
  imports: [RouterLink],
  templateUrl: './upload.html',
})
export class Upload {
  private api = inject(Api);
  invoices = signal<File | null>(null);
  payments = signal<File | null>(null);
  busy = signal(false);
  error = signal('');
  uploaded = signal<UploadResult | null>(null);
  reconciled = signal<ReconcileResult | null>(null);

  pick(kind: 'invoices' | 'payments', input: HTMLInputElement) {
    const file = input.files?.[0] ?? null;
    (kind === 'invoices' ? this.invoices : this.payments).set(file);
  }

  submit() {
    const inv = this.invoices();
    const pay = this.payments();
    if (!inv || !pay) return;
    this.busy.set(true);
    this.error.set('');
    this.uploaded.set(null);
    this.reconciled.set(null);
    this.api.upload(inv, pay).subscribe({
      next: (u) => {
        this.uploaded.set(u);
        this.api.reconcile().subscribe({
          next: (r) => { this.reconciled.set(r); this.busy.set(false); },
          error: (e) => this.fail(e),
        });
      },
      error: (e) => this.fail(e),
    });
  }

  private fail(e: any) {
    this.error.set(String(e?.error?.detail ?? 'Request failed'));
    this.busy.set(false);
  }
}