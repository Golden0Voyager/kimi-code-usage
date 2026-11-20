let userAgentVersion = '0.1.9';

/** Version reported in the `kimi-usage-vscode/<version>` User-Agent header. */
export function getUserAgentVersion(): string {
  return userAgentVersion;
}

export function setUserAgentVersion(version: string): void {
  userAgentVersion = version;
}
