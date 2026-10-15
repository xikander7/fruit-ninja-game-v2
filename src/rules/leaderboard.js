import { LEADERBOARD_API, MODES } from "../config.js?v=229f44b64d";

const MODE_NAMES = Object.freeze(Object.keys(MODES));
const exactKeys = (value, keys) => value && typeof value === "object" && !Array.isArray(value)
  && Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
const score = (value) => Number.isSafeInteger(value) && value >= 0 && value <= 1_000_000;

export class LeaderboardClient {
  constructor({ baseUrl = LEADERBOARD_API, fetchFn = globalThis.fetch, timeoutMs = 3000 } = {}) {
    this.baseUrl = typeof baseUrl === "string" ? baseUrl.replace(/\/+$/u, "") : "";
    this.fetchFn = fetchFn;
    this.timeoutMs = timeoutMs;
  }

  async request(path, options = {}) {
    if (!this.baseUrl || typeof this.fetchFn !== "function") return null;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchFn(`${this.baseUrl}${path}`, {
        ...options,
        credentials: "omit",
        signal: controller.signal,
        headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(options.headers || {}) },
      });
      if (!response.ok) return null;
      return await response.json();
    } catch (_error) {
      return null;
    } finally {
      clearTimeout(timer);
    }
  }

  async loadScores() {
    const data = await this.request("/v1/scores");
    if (!exactKeys(data, ["scores"]) || !exactKeys(data.scores, MODE_NAMES)) return null;
    if (!MODE_NAMES.every((mode) => score(data.scores[mode]))) return null;
    return Object.fromEntries(MODE_NAMES.map((mode) => [mode, data.scores[mode]]));
  }

  async startRun(mode) {
    if (!MODE_NAMES.includes(mode)) return null;
    const data = await this.request("/v1/runs/start", { method: "POST", body: JSON.stringify({ mode }) });
    if (!data || typeof data.token !== "string" || !data.token || data.token.length > 1024) return null;
    return { token: data.token };
  }

  async finishRun(run, result) {
    if (!run || typeof run.token !== "string" || !MODE_NAMES.includes(result && result.mode)) return null;
    const body = {
      token: run.token,
      score: result.score,
      elapsed: result.elapsed,
      stats: result.stats,
    };
    const data = await this.request("/v1/runs/finish", { method: "POST", body: JSON.stringify(body) });
    if (!exactKeys(data, ["mode", "globalBest", "newRecord"])) return null;
    if (data.mode !== result.mode || !score(data.globalBest) || typeof data.newRecord !== "boolean") return null;
    return { mode: data.mode, globalBest: data.globalBest, newRecord: data.newRecord };
  }
}
