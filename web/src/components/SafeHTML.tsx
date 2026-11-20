"use client";

import React, { createElement, type ReactNode } from "react";

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


const VOID_TAGS = new Set(["br"]);


const SAFE_HREF = /^(https?:|mailto:|tel:|\/|#)/i;

function isSafeHref(href: string): boolean {
  return SAFE_HREF.test(href.trim());
}

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

      let tagContent = html.slice(i + 1, closeIdx).trim();
      const isClosing = tagContent.startsWith("/");
      if (isClosing) {
        tagContent = tagContent.slice(1);
      }

      
      
      const selfClosing = tagContent.endsWith("/");
      if (selfClosing) {
        tagContent = tagContent.slice(0, -1);
      }

      const tagName = tagContent.split(/\s/)[0].toLowerCase();

      if (ALLOWED_TAGS.has(tagName)) {
        flushText();

        
        if (VOID_TAGS.has(tagName)) {
          result.push(createElement(tagName, { key: result.length }));
          i = closeIdx + 1;
          continue;
        }

        if (!isClosing && !selfClosing) {
          const contentEnd = findElementEnd(html, tagName, closeIdx);
          if (contentEnd !== -1) {
            const innerHTML = html.slice(closeIdx + 1, contentEnd.end);
            const children = parseHTML(innerHTML);
            const attrs: Record<string, string> = {};
            const attrRegex = /(\w+)\s*=\s*"([^"]*)"/g;
            let attrMatch;
            while ((attrMatch = attrRegex.exec(tagContent)) !== null) {
              attrs[attrMatch[1]] = attrMatch[2];
            }
            if (tagName === "a") {
              const href = attrs.href || "";
              if (href && isSafeHref(href)) {
                result.push(
                  createElement(
                    "a",
                    {
                      key: result.length,
                      href,
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
              } else {
                result.push(...children);
              }
            } else {
              result.push(
                createElement(tagName, { key: result.length }, ...children),
              );
            }
            i = contentEnd.next;
            continue;
          }
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

interface ElementEnd {
  end: number;
  next: number;
}

function findElementEnd(
  html: string,
  tagName: string,
  from: number,
): ElementEnd | -1 {
  const openRe = new RegExp(`<${tagName}(?=[\\s/>])`, "gi");
  const closeRe = new RegExp(`</${tagName}\\s*>`, "gi");

  let depth = 1;
  let pos = from;
  while (pos <= html.length) {
    closeRe.lastIndex = pos;
    const close = closeRe.exec(html);
    if (!close) return -1;

    let opens = 0;
    openRe.lastIndex = pos;
    let open: RegExpExecArray | null = null;
    while ((open = openRe.exec(html)) !== null) {
      if (open.index >= close.index) break;
      opens++;
    }
    depth += opens;

    depth--;
    if (depth === 0) {
      return { end: close.index, next: close.index + close[0].length };
    }
    pos = close.index + close[0].length;
  }
  return -1;
}

export function SafeHTML({ html }: SafeHTMLProps) {
  return <>{parseHTML(html)}</>;
}



