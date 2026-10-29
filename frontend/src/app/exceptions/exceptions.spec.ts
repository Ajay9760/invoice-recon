import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Exceptions } from './exceptions';

describe('Exceptions', () => {
  let component: Exceptions;
  let fixture: ComponentFixture<Exceptions>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Exceptions],
    }).compileComponents();

    fixture = TestBed.createComponent(Exceptions);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
