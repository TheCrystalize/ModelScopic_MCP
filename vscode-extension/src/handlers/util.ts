export function ensureObject<T>(params: unknown, requiredKeys: (keyof T)[]): T {
  if (typeof params !== "object" || params === null) {
    throw new Error("params must be an object");
  }
  const obj = params as Record<string, unknown>;
  for (const k of requiredKeys) {
    if (!(k in obj)) {
      throw new Error(`missing required param: ${String(k)}`);
    }
  }
  return params as T;
}

export function asString(v: unknown, name: string): string {
  if (typeof v !== "string") {
    throw new Error(`param ${name} must be a string`);
  }
  return v;
}

export function asNumber(v: unknown, name: string): number {
  if (typeof v !== "number" || !Number.isFinite(v)) {
    throw new Error(`param ${name} must be a finite number`);
  }
  return v;
}

export function asBool(v: unknown, name: string): boolean {
  if (typeof v !== "boolean") {
    throw new Error(`param ${name} must be a boolean`);
  }
  return v;
}
