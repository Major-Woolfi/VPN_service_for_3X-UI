// Скрипт генерирует:
// 1) src/lib/i18n-generated.ts - импорты всех языков
// Запуск: npx tsx scripts/generate-i18n.ts
import { readdirSync, readFileSync, writeFileSync } from "fs";
import { join } from "path";
import { format } from "prettier";

type TranslationFile = Record<string, unknown> & {
  legal?: Record<string, unknown>;
};

const translationsDir = join(process.cwd(), "public", "translations");
const i18nOutputFile = join(process.cwd(), "src", "lib", "i18n-generated.ts");

async function main() {
  const files = readdirSync(translationsDir)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""))
    .sort();

  if (files.length === 0) {
    throw new Error(`No translation files found in ${translationsDir}`);
  }

  const translationData = new Map<string, Record<string, unknown>>();
  for (const lang of files) {
    const filePath = join(translationsDir, `${lang}.json`);
    const data = JSON.parse(readFileSync(filePath, "utf-8")) as TranslationFile;

    if (
      !data.meta ||
      typeof data.meta !== "object" ||
      !data.buttons ||
      typeof data.buttons !== "object" ||
      !data.texts ||
      typeof data.texts !== "object"
    ) {
      throw new Error(`Invalid translation structure in ${filePath}`);
    }

    const meta = data.meta as Record<string, unknown>;
    if (
      meta.code !== lang ||
      typeof meta.name !== "string" ||
      !meta.name.trim()
    ) {
      throw new Error(`Translation metadata mismatch in ${filePath}`);
    }

    translationData.set(lang, data);
  }

  let i18nContent = `// Автогенерированный файл - не редактировать вручную!
// Генерируется скриптом: npx tsx scripts/generate-i18n.ts

import type { TranslationData } from "./i18n-types";

`;

  i18nContent +=
    files
      .map(
        (lang) =>
          `import ${lang} from "../../public/translations/${lang}.json";`,
      )
      .join("\n") + "\n\n";

  i18nContent += `// Все языки: ключ = имя файла без расширения
export const LANGUAGES: Record<string, TranslationData> = { ${files.join(", ")} };
`;

  i18nContent += `\n// Для SSR
export const SERVER_LANGUAGES: Record<string, TranslationData> = LANGUAGES;
`;

  const formatted = await format(i18nContent, {
    parser: "typescript",
    filepath: i18nOutputFile,
  });

  writeFileSync(i18nOutputFile, formatted, "utf-8");
  console.log(
    `✅ Generated ${files.length} language imports: ${files.join(", ")}`,
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
