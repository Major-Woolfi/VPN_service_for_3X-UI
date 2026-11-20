"use client";

import { useEffect } from "react";

const FALLBACK_RESUME_MS = 4_000;

export default function ScrollAnimations() {
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;

    const elements = Array.from(
      document.querySelectorAll<HTMLElement>(".fade-in"),
    );

    const resume = (el: HTMLElement) => {
      el.style.animationPlayState = "running";
    };

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            resume(entry.target as HTMLElement);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.1, rootMargin: "0px 0px -40px 0px" },
    );

    elements.forEach((el) => {
      el.style.animationPlayState = "paused";
      observer.observe(el);
    });

    const fallback = setTimeout(() => {
      elements.forEach(resume);
      observer.disconnect();
    }, FALLBACK_RESUME_MS);

    return () => {
      clearTimeout(fallback);
      observer.disconnect();
    };
  }, []);

  return null;
}
