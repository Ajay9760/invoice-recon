import { Component, inject, signal } from '@angular/core';
import { Api, SummaryResponse } from '../api';

@Component({
  selector: 'app-summary',
  templateUrl: './summary.html',
})
export class Summary {
  private api = inject(Api);
  data = signal<SummaryResponse | null>(null);

  constructor() {
    this.api.getSummary().subscribe((s) => this.data.set(s));
  }
}