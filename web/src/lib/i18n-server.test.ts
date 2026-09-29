import assert from "node:assert/strict";
import test from "node:test";

import {
  detectLanguage,
  getServerLegalDocument,
  getServerSiteCopy,
  normalizeServerLanguage,
  LEGAL_DOCUMENT_KEYS,
} from "./i18n-server";
import { getServerLanguages } from "./i18n-server";

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

test("normalizeServerLanguage keeps supported codes and falls back otherwise", () => {
  const languages = getServerLanguages();
  const fallback = detectLanguage();

  for (const language of languages) {
    assert.equal(normalizeServerLanguage(language), language);
    assert.equal(normalizeServerLanguage(language.toUpperCase()), language);
  }
  assert.equal(normalizeServerLanguage("en-US"), "en");
  assert.equal(normalizeServerLanguage("pt_BR"), fallback);
  assert.equal(normalizeServerLanguage(undefined), fallback);
  assert.equal(normalizeServerLanguage(""), fallback);
});

test("getServerSiteCopy resolves SEO texts for every language", () => {
  for (const language of getServerLanguages()) {
    const copy = getServerSiteCopy(language);
    assert.ok(copy.siteDescription.length > 0, language);
    assert.ok(copy.siteTitle.length > 0, language);
    assert.ok(copy.twitterDescription.length > 0, language);
    assert.ok(
      !copy.siteDescription.includes("{vpnName}"),
      `siteDescription ${language}`,
    );
    assert.ok(!copy.siteTitle.includes("{siteName}"), `siteTitle ${language}`);
  }
});

test("getServerSiteCopy falls back for unsupported languages", () => {
  const copy = getServerSiteCopy("fr");
  assert.deepEqual(copy, getServerSiteCopy(detectLanguage()));
});

test("getServerLegalDocument returns complete documents with formatted sections", () => {
  for (const language of getServerLanguages()) {
    for (const key of LEGAL_DOCUMENT_KEYS) {
      const doc = getServerLegalDocument(language, key);
      assert.ok(doc.title.length > 0, `${language}/${key} title`);
      assert.ok(doc.subtitle.length > 0, `${language}/${key} subtitle`);
      assert.ok(doc.effectiveDate.length > 0, `${language}/${key} date`);
      assert.ok(doc.sections.length > 0, `${language}/${key} sections`);

      for (const section of doc.sections) {
        assert.ok(section.title.length > 0, `${language}/${key} section title`);
        assert.ok(
          section.content.length > 0,
          `${language}/${key} section body`,
        );
        assert.ok(
          !section.content.includes("{vpnName}"),
          `${language}/${key} placeholder`,
        );
        assert.ok(
          !section.content.includes("{siteName}"),
          `${language}/${key} siteName`,
        );
      }
    }
  }
});

test("getServerLegalDocument uses the fallback language when a document is missing", () => {
  const fallback = detectLanguage();
  const unsupported = getServerLegalDocument("fr", "tos");
  assert.deepEqual(unsupported, getServerLegalDocument(fallback, "tos"));
});
