// API keys are encrypted with the operating system (Electron safeStorage: DPAPI on Windows) and
// never leave the main process: the window only learns whether keys exist and their last 4 characters.
import { readFile, writeFile, rename, unlink, mkdir } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import type { Credentials } from './alpaca.js';

export interface Cipher {
  isEncryptionAvailable(): boolean;
  encryptString(value: string): Buffer;
  decryptString(value: Buffer): string;
}

export const KEY_ID = /^[A-Z0-9]{16,40}$/;
export const SECRET = /^[A-Za-z0-9/+=_-]{20,100}$/;

export function validateCredentials(value: unknown): Credentials {
  const { keyId, secret } = (value ?? {}) as Record<string, unknown>;
  const id = typeof keyId === 'string' ? keyId.trim() : '';
  const key = typeof secret === 'string' ? secret.trim() : '';
  if (!KEY_ID.test(id)) throw new Error('The Alpaca key ID should be 16–40 capital letters and digits (it often starts with PK or AK).');
  if (!SECRET.test(key)) throw new Error('The Alpaca secret key looks incomplete. Copy it again from the Alpaca dashboard.');
  return { keyId: id, secret: key };
}

export class SecretStore {
  constructor(readonly file: string, readonly cipher: Cipher) {}

  async load(): Promise<Credentials | null> {
    let raw: string;
    try { raw = await readFile(this.file, 'utf8'); } catch { return null; }
    if (!this.cipher.isEncryptionAvailable()) return null;
    try {
      const saved = JSON.parse(raw) as { keyId: string; secret: string };
      return validateCredentials({ keyId: this.cipher.decryptString(Buffer.from(saved.keyId, 'base64')),
        secret: this.cipher.decryptString(Buffer.from(saved.secret, 'base64')) });
    } catch { return null; }
  }

  async save(credentials: Credentials): Promise<void> {
    if (!this.cipher.isEncryptionAvailable()) throw new Error('Windows encryption is unavailable, so the keys cannot be stored safely.');
    const content = JSON.stringify({ keyId: this.cipher.encryptString(credentials.keyId).toString('base64'),
      secret: this.cipher.encryptString(credentials.secret).toString('base64') });
    await mkdir(path.dirname(this.file), { recursive: true });
    const temporary = this.file + '.' + randomUUID() + '.tmp';
    try { await writeFile(temporary, content, { mode: 0o600 }); await rename(temporary, this.file); }
    finally { await unlink(temporary).catch(() => {}); }
  }

  async clear(): Promise<void> { await unlink(this.file).catch(() => {}); }
}

export const maskKey = (keyId: string) => '••••' + keyId.slice(-4);
