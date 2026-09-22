import assert from "node:assert/strict";
import test from "node:test";

import { detectLanguage } from "./i18n-server";

const testCases: Array<[string, string]> = [
  ["en;q=0.9,ru", "ru"],
  ["de;q=0.4,en;q=0.8,ru;q=0.2", "en"],
  ["fr;q=1,zh-Hant;q=0.7,de", "de"],
  ["en-US;q=0.8,de;q=0.8", "en"],
  ["en;q=0,ru;q=0.5", "ru"],
  ["fr;q=bogus,de;q=0.5", "de"],
  ["en;q=1.1,ru;q=0.8", "ru"],
  ["en;q=0,de;q=0", detectLanguage()],
];

test("detectLanguage selects the supported language with the highest quality", () => {
  for (const [header, expected] of testCases) {
    assert.equal(detectLanguage(header), expected);
  }
});

test("detectLanguage uses the fallback for empty or unsupported languages", () => {
  assert.equal(detectLanguage(), detectLanguage("fr"));
  assert.equal(detectLanguage("   "), detectLanguage("fr"));
});
