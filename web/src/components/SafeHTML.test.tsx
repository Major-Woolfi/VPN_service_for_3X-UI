import assert from "node:assert/strict";
import test from "node:test";

import { renderToStaticMarkup } from "react-dom/server";

import { SafeHTML } from "./SafeHTML";

function render(html: string): string {
  return renderToStaticMarkup(<SafeHTML html={html} />);
}

test("br is rendered for every void-tag spelling", () => {
  assert.equal(render("a<br>b"), "a<br/>b");
  assert.equal(render("a<br/>b"), "a<br/>b");
  assert.equal(render("a<br />b"), "a<br/>b");
  assert.equal(render("a<BR>b"), "a<br/>b");
});

test("nested same-name tags are balanced", () => {
  assert.equal(render("<b><b>x</b></b>"), "<b><b>x</b></b>");
  assert.equal(render("<b><b><b>x</b></b></b>"), "<b><b><b>x</b></b></b>");
  assert.equal(render("<b>a</b> <b>b</b>"), "<b>a</b> <b>b</b>");
});

test("nested different-name tags are balanced", () => {
  assert.equal(
    render("<p><strong><em>x</em></strong></p>"),
    "<p><strong><em>x</em></strong></p>",
  );
  assert.equal(
    render("<ul><li>a</li><li>b</li></ul>"),
    "<ul><li>a</li><li>b</li></ul>",
  );
});

test("closing tag with a space before > is consumed correctly", () => {
  assert.equal(render("<b>x</b >y"), "<b>x</b>y");
});

test("allowed formatting tags are kept", () => {
  assert.equal(
    render("<strong>a</strong> <em>b</em>"),
    "<strong>a</strong> <em>b</em>",
  );
  assert.equal(render("<p>text</p>"), "<p>text</p>");
});

test("disallowed tags are escaped to text", () => {
  assert.equal(
    render("<script>alert(1)</script>"),
    "&lt;script&gt;alert(1)&lt;/script&gt;",
  );
  assert.equal(render("<div>x</div>"), "&lt;div&gt;x&lt;/div&gt;");
  assert.equal(
    render("<img src=x onerror=alert(1)>"),
    "&lt;img src=x onerror=alert(1)&gt;",
  );
});

test("unsafe hrefs are dropped but their text is kept", () => {
  assert.equal(render('<a href="javascript:alert(1)">x</a>'), "x");
  assert.equal(render('<a href="data:text/html,x">y</a>'), "y");
  assert.equal(render('<a href="vbscript:x">y</a>'), "y");
});

test("safe hrefs become anchors with rel protection", () => {
  for (const href of [
    "https://example.com",
    "http://example.com",
    "mailto:a@example.com",
    "tel:+79991234567",
    "/profile",
    "#anchor",
  ]) {
    const out = render(`<a href="${href}">x</a>`);
    assert.match(out, /<a /, `anchor missing for ${href}`);
    assert.match(out, /rel="noopener noreferrer"/, `rel missing for ${href}`);
  }
});

test("anchor attributes never leak event handlers or self-closing slash", () => {
  const out = render('<a href="https://example.com" onclick="alert(1)">x</a>');
  assert.doesNotMatch(out, /onclick/);
  assert.doesNotMatch(out, /<a[^>]*\/>/);
});

test("unterminated and stray markup does not hang or lose text", () => {
  assert.equal(render("<b>unclosed"), "&lt;b&gt;unclosed");
  assert.equal(render("stray </b> close"), "stray &lt;/b&gt; close");
  assert.equal(render(""), "");
  assert.equal(render("plain text"), "plain text");
});

test("a bare less-than sign is preserved as text", () => {
  assert.equal(render("a < b"), "a &lt; b");
});
