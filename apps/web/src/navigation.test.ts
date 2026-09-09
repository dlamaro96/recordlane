// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import { navigation } from './navigation';

describe('operator navigation', () => {
  it('exposes all required workspaces with unique routes and order markers', () => {
    expect(navigation).toHaveLength(15);
    expect(new Set(navigation.map(([route]) => route)).size).toBe(15);
    expect(navigation.map(([, , order]) => order)).toEqual(
      Array.from({ length: 15 }, (_, index) => String(index + 1).padStart(2, '0')),
    );
  });
});
