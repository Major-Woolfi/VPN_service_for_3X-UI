"use client";

import { createElement, type ReactNode } from "react";

interface SafeHTMLProps {
  html: string;
}

const ALLOWED_TAGS = new Set([
  "br",
  "strong",
  "b",
  "em",
  "i",
  "a",
  "p",
  "ul",
  "ol",
  "li",
]);

function parseHTML(html: string): ReactNode[] {
  const result: ReactNode[] = [];
  let currentText = "";
  let i = 0;

  function flushText() {
    if (currentText) {
      result.push(currentText);
      currentText = "";
    }
  }

  while (i < html.length) {
    if (html[i] === "<") {
      const closeIdx = html.indexOf(">", i);
      if (closeIdx === -1) {
        currentText += html.slice(i);
        break;
      }

      const tagContent = html.slice(i + 1, closeIdx).trim();
      const isClosing = tagContent.startsWith("/");
      const tagName = isClosing
        ? tagContent.slice(1).split(/\s/)[0]
        : tagContent.split(/\s/)[0];

      if (ALLOWED_TAGS.has(tagName.toLowerCase())) {
        flushText();

        if (!isClosing && !tagContent.endsWith("/")) {
          const endTagIdx = html.indexOf(`</${tagName}>`, closeIdx);
          if (endTagIdx !== -1) {
            const innerHTML = html.slice(closeIdx + 1, endTagIdx);
            const children = parseHTML(innerHTML);
            const attrs: Record<string, string> = {};
            const attrRegex = /(\w+)="([^"]*)"/g;
            let attrMatch;
            while ((attrMatch = attrRegex.exec(tagContent)) !== null) {
              attrs[attrMatch[1]] = attrMatch[2];
            }
            if (tagName === "a" && attrs.href) {
              result.push(
                createElement(
                  "a",
                  {
                    key: result.length,
                    href: attrs.href,
                    target: "_blank",
                    rel: "noopener noreferrer",
                    style: {
                      color: "var(--accent)",
                      textDecoration: "underline",
                    },
                  },
                  ...children,
                ),
              );
            } else if (tagName === "br") {
              result.push(createElement("br", { key: result.length }));
            } else {
              result.push(
                createElement(tagName, { key: result.length }, ...children),
              );
            }
            i = endTagIdx + tagName.length + 3;
            continue;
          }
        } else if (tagName === "br") {
          flushText();
          result.push(createElement("br", { key: result.length }));
          i = closeIdx + 1;
          continue;
        }
      }

      currentText += html.slice(i, closeIdx + 1);
      i = closeIdx + 1;
    } else {
      currentText += html[i];
      i++;
    }
  }

  flushText();
  return result;
}

export function SafeHTML({ html }: SafeHTMLProps) {
  return <>{parseHTML(html)}</>;
}
