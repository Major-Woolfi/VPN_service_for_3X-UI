# VPN Bot for 3X‑UI

## Telegram-бот для управления VPN-подписками

[![Stars](https://img.shields.io/github/stars/Major-Woolfi/VPN_bot_for_3X-UI?style=social)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/stargazers)
[![Issues](https://img.shields.io/github/issues/Major-Woolfi/VPN_bot_for_3X-UI)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/issues)
[![License](https://img.shields.io/github/license/Major-Woolfi/VPN_bot_for_3X-UI)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](.github/CONTRIBUTING.md)

[🐛 Сообщить о баге](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/issues/new) •
[💡 Предложить идею](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/discussions)

---

## 📝 Описание

Полнофункциональный Telegram-бот для продажи и управления VPN-подписками с глубокой интеграцией в панель 3X‑UI. Экосистема для бизнеса VPN: от приёма платежей до автоматического создания клиентов и обновления SSL-сертификатов.

### ✨ Ключевые возможности

- 💳 **Продажа подписок** — тарифы с гибкой формулой цены
- 🔗 **Интеграция с 3X‑UI** — автоматическое создание клиентов
- 🎁 **Реферальная система** — бонусные дни по рефералам
- 🏷️ **Trust Score** — система лояльности со скидками до 50%
- 🌍 **Мультиязычность** — 7 языков (ru, en, de, pl, ja, zh, be)
- 🔄 **Автообновление SSL** — через SSH каждые 5 дней
- 📊 **Статистика** — пользователи, активные VPN, платежи

---

## 🏗️ Архитектура проекта

```plaintext
VPN_bot_for_3X-UI/
├── main.py                  # Монолит бота
├── requirements.txt         # Зависимости
├── Dockerfile               # Docker-образ
├── deploy_bot.sh            # Скрипт деплоя
├── api_doc.json             # Документация по API
├── .env.example             # Пример конфигурации
├── langs/                   # Локализация (JSON)
│   ├── be.json              # Беларуская
│   ├── de.json              # Deutsch
│   ├── en.json              # English
│   ├── ja.json              # 日本語
│   ├── pl.json              # Polski
│   ├── ru.json              # Русский
│   └── zh.json              # 中文
├── data/                    # Данные бота
│   └── tarifs.json
├── logs/                    # Логи
├── LICENSE
└── README.md
```

---

## 🛠️ Технологический стек

| Категория           | Технологии                           |
|---------------------|--------------------------------------|
| **Backend**         | Python 3.13.9                        |
| **Telegram API**    | aiogram 3.29.0                       |
| **HTTP-клиент**     | aiohttp 3.14.1                       |
| **База данных**     | aiosqlite 0.22.1 (асинхронный SQLite)|
| **Файлы**           | aiofiles 25.1.0                      |
| **SSH**             | paramiko 5.0.0                       |
| **Контейнеризация** | Docker (python:3.13.9-slim)          |

---

## 🤝 Контрибьюция

Приветствуем любые вклад в проект! Перед созданием PR обязательно прочитай:

- 📋 [CONTRIBUTING](https://github.com/Major-Woolfi/.github/tree/main/workflows/CONTRIBUTING.md) — правила участия
- 💬 [CODE_OF_CONDUCT](https://github.com/Major-Woolfi/.github/tree/main/workflows/CODE_OF_CONDUCT.md) — кодекс поведения
- 🐛 [ISSUE_TEMPLATE](https://github.com/Major-Woolfi/.github/tree/main/workflows/ISSUE_TEMPLATE/) — шаблоны багов и фич
- 🔀 [PULL_REQUEST_TEMPLATE](https://github.com/Major-Woolfi/.github/tree/main/workflows/PULL_REQUEST_TEMPLATE.md) — требования к PR

---

## 👥 Авторы и благодарности

Спасибо всем замечательным людям, которые делают этот проект возможным:

<a href="https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Major-Woolfi/VPN_bot_for_3X-UI" />
</a>

---

## 📄 Лицензия

Этот проект распространяется под лицензией **MIT**. Подробности в файле [LICENSE](LICENSE).

---

**⭐ Поставь звезду, если проект понравился!**
**[📧 Контакты](https://Major_Woolfi.t.me)**
