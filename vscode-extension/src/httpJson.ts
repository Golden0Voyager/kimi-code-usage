import * as https from 'https';

export interface HttpJsonResponse {
  status: number;
  body: string;
  /** Parsed JSON, or null when the body is not valid JSON. */
  json: unknown;
}

/**
 * Shared GET for provider endpoints: Bearer auth, versioned User-Agent,
 * 10s timeout. Resolves with status+body+parsed JSON; network errors reject.
 */
export function httpGetJson(
  url: string,
  apiKey: string,
  userAgentVersion: string,
): Promise<HttpJsonResponse> {
  const { promise, resolve, reject } = Promise.withResolvers<HttpJsonResponse>();
  const req = https.get(
    url,
    {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        'User-Agent': `kimi-usage-vscode/${userAgentVersion}`,
      },
      timeout: 10000,
    },
    (res) => {
      let body = '';
      res.on('data', (chunk: Buffer | string) => (body += chunk));
      res.on('end', () => {
        let json: unknown;
        try {
          json = JSON.parse(body);
        } catch {
          json = null;
        }
        resolve({ status: res.statusCode ?? 0, body, json });
      });
    },
  );
  req.on('error', reject);
  req.on('timeout', () => {
    req.destroy();
    reject(new Error('Request timeout'));
  });
  return promise;
}
