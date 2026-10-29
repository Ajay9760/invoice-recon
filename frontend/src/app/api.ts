import { Injectable, inject } from '@angular/core';
import { HttpClient,HttpParams } from '@angular/common/http';

export interface RuleCount {
  rule_code: string;
  severity: string;
  count: number;
}

export interface SummaryResponse {
  invoices: number;
  payments: number;
  exceptions: number;
  by_severity: Record<string, number>;
  by_rule: RuleCount[];
}

export interface ExceptionItem {
  id: number;
  rule_code: string;
  severity: string;
  invoice_id: number | null;
  payment_id: number | null;
  detail: string;
  run_at: string;
}

export interface ExceptionPage {
  total: number;
  limit: number;
  offset: number;
  items: ExceptionItem[];
}

export interface UploadResult {
  invoices_loaded: number;
  payments_loaded: number;
  invoices_rejected: number;
  payments_rejected: number;
}

export interface ReconcileResult {
  as_of: string;
  exceptions: number;
}

@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  private base = 'http://127.0.0.1:8000';

    upload(invoices: File, payments: File) {
    const form = new FormData();
    form.append('invoices', invoices);
    form.append('payments', payments);
    return this.http.post<UploadResult>(`${this.base}/data/upload`, form);
  }

  reconcile() {
    return this.http.post<ReconcileResult>(`${this.base}/reconcile`, {});
  }
  
  getSummary() {
    return this.http.get<SummaryResponse>(`${this.base}/summary`);
  }

  getExceptions(rule: string, limit: number, offset: number) {
    let params = new HttpParams().set('limit', limit).set('offset', offset);
    if (rule) params = params.set('rule', rule);
    return this.http.get<ExceptionPage>(`${this.base}/exceptions`, { params });
  }
}