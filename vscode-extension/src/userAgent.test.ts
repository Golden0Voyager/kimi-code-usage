import { describe, it, expect } from 'vitest';
import { getUserAgentVersion, setUserAgentVersion } from './userAgent';

describe('userAgent', () => {
  it('returns the default version', () => {
    expect(getUserAgentVersion()).toBe('0.1.9');
  });

  it('setUserAgentVersion updates the reported version', () => {
    setUserAgentVersion('0.2.1');
    expect(getUserAgentVersion()).toBe('0.2.1');
    setUserAgentVersion('0.1.9');
  });
});
