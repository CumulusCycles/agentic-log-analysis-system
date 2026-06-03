import "@testing-library/jest-dom/vitest";

// Node 25 + jsdom 25 don't install a working Storage on window. Provide a
// minimal in-memory Storage so component code calling localStorage.{getItem,
// setItem, removeItem, clear} works in tests.
class MemoryStorage implements Storage {
  private store = new Map<string, string>();
  get length() {
    return this.store.size;
  }
  clear() {
    this.store.clear();
  }
  getItem(key: string) {
    return this.store.has(key) ? (this.store.get(key) as string) : null;
  }
  key(index: number) {
    return Array.from(this.store.keys())[index] ?? null;
  }
  removeItem(key: string) {
    this.store.delete(key);
  }
  setItem(key: string, value: string) {
    this.store.set(key, String(value));
  }
}

const localStorageInstance = new MemoryStorage();
const sessionStorageInstance = new MemoryStorage();

Object.defineProperty(globalThis, "localStorage", {
  value: localStorageInstance,
  configurable: true,
  writable: true,
});
Object.defineProperty(globalThis, "sessionStorage", {
  value: sessionStorageInstance,
  configurable: true,
  writable: true,
});
if (typeof window !== "undefined") {
  Object.defineProperty(window, "localStorage", {
    value: localStorageInstance,
    configurable: true,
    writable: true,
  });
  Object.defineProperty(window, "sessionStorage", {
    value: sessionStorageInstance,
    configurable: true,
    writable: true,
  });
}
