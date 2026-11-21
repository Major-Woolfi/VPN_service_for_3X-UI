import assert from "node:assert/strict";
import test from "node:test";

import {
  detectlanguage,
  getServerLegalDocument,
  getServerPageSeo,
  getServerSiteCopy,
  normalizeServerlanguage,
  LEGAL_DOCUMENT_keyS,
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
  ["en;q=0,de;q=0", detectlanguage()],
];

test("detectlanguage selects the supported language with the highest quality", () => {
  for (const [header, expected] of testCases) {
    assert.equal(detectlanguage(header), expected);
  }
});

test("detectlanguage uses the fallback for empty or unsupported languages", () => {
  assert.equal(detectlanguage(), detectlanguage("fr"));
  assert.equal(detectlanguage("   "), detectlanguage("fr"));
});

test("normalizeServerlanguage keeps supported codes and falls back otherwise", () => {
  const languages = getServerLanguages();
  const fallback = detectlanguage();

  for (const language of languages) {
    assert.equal(normalizeServerlanguage(language), language);
    assert.equal(normalizeServerlanguage(language.toUpperCase()), language);
  }
  assert.equal(normalizeServerlanguage("en-US"), "en");
  assert.equal(normalizeServerlanguage("pt_BR"), fallback);
  assert.equal(normalizeServerlanguage(undefined), fallback);
  assert.equal(normalizeServerlanguage(""), fallback);
});

test("getServerSiteCopy resolves SEO texts for every language", () => {
  for (const language of getServerLanguages()) {
    const copy = getServerSiteCopy(language);
    assert.ok(copy.siteDescription.length > 0, language);
    assert.ok(copy.siteTitle.length > 0, language);
    assert.ok(copy.twitterDescription.length > 0, language);
    assert.ok(!copy.siteDescription.includes("{vpnName}"), `siteDescription ${language}`);
    assert.ok(!copy.siteTitle.includes("{siteName}"), `siteTitle ${language}`);
  }
});

test("getServerSiteCopy falls back for unsupported languages", () => {
  const copy = getServerSiteCopy("fr");
  assert.deepEqual(copy, getServerSiteCopy(detectlanguage()));
});

const seoPages = [
  "client",
  "coOwners",
  "login",
  "offer",
  "partner",
  "payment",
  "privacy",
  "profile",
  "referral",
  "register",
  "settings",
  "subscription",
  "tos",
];

test("getServerPageSeo resolves localized metadata for every page", () => {
  for (const language of getServerLanguages()) {
    for (const page of seoPages) {
      const seo = getServerPageSeo(language, page);
      assert.ok(seo.title.length > 0, `${language}/${page} title`);
      assert.ok(seo.description.length > 0, `${language}/${page} description`);
      assert.ok(!seo.title.includes("{"), `${language}/${page} title placeholder`);
      assert.ok(!seo.description.includes("{"), `${language}/${page} description placeholder`);
    }
  }
});

test("getServerPageSeo falls back for unsupported languages", () => {
  const fallback = detectlanguage();
  assert.deepEqual(getServerPageSeo("fr", "profile"), getServerPageSeo(fallback, "profile"));
  assert.deepEqual(getServerPageSeo("en", "unknown"), getServerPageSeo(fallback, "unknown"));
});

test("getServerLegalDocument returns complete documents with formatted sections", () => {
  for (const language of getServerLanguages()) {
    for (const key of LEGAL_DOCUMENT_keyS) {
      const doc = getServerLegalDocument(language, key);
      assert.ok(doc.title.length > 0, `${language}/${key} title`);
      assert.ok(doc.subtitle.length > 0, `${language}/${key} subtitle`);
      assert.ok(doc.effectiveDate.length > 0, `${language}/${key} date`);
      assert.ok(doc.sections.length > 0, `${language}/${key} sections`);

      for (const section of doc.sections) {
        assert.ok(section.title.length > 0, `${language}/${key} section title`);
        assert.ok(section.content.length > 0, `${language}/${key} section body`);
        assert.ok(!section.content.includes("{vpnName}"), `${language}/${key} placeholder`);
        assert.ok(!section.content.includes("{siteName}"), `${language}/${key} siteName`);
      }
    }
  }
});

test("getServerLegalDocument uses the fallback language when a document is missing", () => {
  const fallback = detectlanguage();
  const unsupported = getServerLegalDocument("fr", "tos");
  assert.deepEqual(unsupported, getServerLegalDocument(fallback, "tos"));
});
