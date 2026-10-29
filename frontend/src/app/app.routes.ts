import { Routes } from '@angular/router';
import { Summary } from './summary/summary';
import { Exceptions } from './exceptions/exceptions';
import { Upload } from './upload/upload';

export const routes: Routes = [
  { path: '', redirectTo: 'summary', pathMatch: 'full' },
  { path: 'summary', component: Summary },
  { path: 'exceptions', component: Exceptions },
    { path: 'upload', component: Upload },
];