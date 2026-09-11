// Автогенерированный файл - не редактировать вручную!
// Генерируется скриптом: npx tsx scripts/generate-i18n.ts

import type { TranslationData } from "./i18n-types";

import be from "../../public/translations/be.json";
import de from "../../public/translations/de.json";
import en from "../../public/translations/en.json";
import ja from "../../public/translations/ja.json";
import pl from "../../public/translations/pl.json";
import ru from "../../public/translations/ru.json";
import zh from "../../public/translations/zh.json";

// Все языки: ключ = имя файла без расширения
export const LANGUAGES: Record<string, TranslationData> = { be, de, en, ja, pl, ru, zh };

// Для SSR
export const SERVER_LANGUAGES: Record<string, TranslationData> = LANGUAGES;
