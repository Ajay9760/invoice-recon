import { Component, inject, signal } from '@angular/core';
import { Api, ExceptionPage } from '../api';

@Component({
  selector: 'app-exceptions',
  templateUrl: './exceptions.html',
})
export class Exceptions {
  private api = inject(Api);
  readonly pageSize = 25;
  readonly rules = [
    'MISSING_VENDOR', 'DUPLICATE_INVOICE', 'NON_POSITIVE_AMOUNT', 'TAX_MISMATCH',
    'TOTAL_MISMATCH', 'FUTURE_DATED', 'DUE_BEFORE_ISSUE', 'INVALID_CURRENCY',
    'UNPAID_OVERDUE', 'OVERPAID', 'PARTIALLY_PAID_OVERDUE', 'ORPHAN_PAYMENT',
  ];

  rule = signal('');
  page = signal(0);
  result = signal<ExceptionPage | null>(null);

  constructor() {
    this.load();
  }

  load() {
    this.api
      .getExceptions(this.rule(), this.pageSize, this.page() * this.pageSize)
      .subscribe((r) => this.result.set(r));
  }

  setRule(value: string) {
    this.rule.set(value);
    this.page.set(0);
    this.load();
  }

  next() { this.page.update((p) => p + 1); this.load(); }
  prev() { this.page.update((p) => p - 1); this.load(); }
  isLast(r: ExceptionPage) { return (this.page() + 1) * this.pageSize >= r.total; }
}