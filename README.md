# VPN_service_for_3X-UI - полноценный VPN-сервис для комерческих VPN-проектов

[![Stars](https://img.shields.io/github/stars/Major-Woolfi/VPN_service_for_3X-UI?style=social)](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/stargazers)
[![Issues](https://img.shields.io/github/issues/Major-Woolfi/VPN_service_for_3X-UI)](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/issues)
[![License](https://img.shields.io/github/license/Major-Woolfi/VPN_service_for_3X-UI)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Major-Woolfi/.github/blob/main/community/CONTRIBUTING.md)
![Status](https://img.shields.io/badge/Status-active-brightgreen)

[🐛 Сообщить о баге](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/issues/new) •
[💡 Предложить идею](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/discussions)

> Советую также посмотреть тематические репозитории: [рабочие и стабильные конфигурации для XRay, панели 3X-UI и настройки клиентских приложений](https://github.com/Major-Woolfi/3X-UI-Configs) и [продвинутый бот-Inviter для пиара всеми способами](https://github.com/Major-Woolfi/Inviter)

---

## 📖 Описание проекта

### Идея и концепция

**VPN_service_for_3X-UI** - это проект, созданный для решения конкретной задачи: автоматизация, упрощение и удешивление VPN-бизнеса.

Основная идея проекта родилась из необходимости иметь бота для собственного VPN-проекта. Проект воплощает подход автоматизации, упрощения, ускорения и удешивления рутинных задач, что позволяет добится максимально комфортной и быстрой работы.

### Полное описание

Проект ориентирован на администраторов VPN-проектов и решает следующие задачи:

- Автоматизация сервиса
- Устранение дизкомфорта администраторам проекта
- Упрощение UX до комфортного уровня

Ключевые принципы проекта:

1. **Простота** - упрощение сложных процессов
2. **Удобство** - сделать выполнение задачи максимально удобным
3. **Надёжность** - максимальная устойчивость к любому сценарию использования
4. **Гибкость** - максимально гибкие настройки

### Для кого этот проект

- Создатели VPN-проектов
- Разработчики собственных ботов

> Но на этом аудитория не ограничивается. Она ограничивается лишь вашей фантазией.

---

## ✨ Реализованные фичи

Реализовано и работоспособно:

- Автообновление SSL
- Автовыдача подписок
- Гибкая настройка тарифов через JSON
- Система очков доверия с гибкой настройкой
- Партнёрская система с гибкой настройкой
- Кастомные подписки с гибкой настройкой
- Отладочное меню
- Гибкая реферальная система
- Блоки социальных ссылок
- Удобное меню управления ожидающими платежами и заявками
- Мультиязычность

---

## 🚀 Быстрый старт

### Предварительные требования

- Зависимости
  - Суммарно
  - bot
    - Runtime - Python 3.13.9+ (возможно и старше, тестирование не проводилось)
    - Библиотеки из requirements.txt
    - 3X-UI 3.0.0+ (на сервере)
    - Docker (для деплоя)
  - web
    - Runtime - Node.js 26.7.0 (возможно и старше, тестирование не проводилось)
    - Библиотеки из package.json
    - Nginx (для API, Reverse Proxy)
- Железо (выделеное, минимум для запуска и корректной работы)
  - Суммарно
    - CPU 1 ядро 1Ггц
    - RAM 450 мб
    - ROM 1,2 Гб
  - bot
    - CPU 1 ядро 1Ггц
    - RAM 250 мб
    - ROM 400 мб
  - web
    - CPU 1 ядро 1Ггц
    - RAM 150 мб
    - ROM 650 мб

### Установка

```bash
# Клонируйте репозиторий
git clone https://github.com/Major-Woolfi/VPN_service_for_3X-UI.git
cd VPN_service_for_3X-UI
```

### Конфигурация

Настраивайте проект через файл конфигурации `.env`. Пример конфигурации можно найти в файлах `.env.example`.
Настройка требуется как у bot, так и у web. Проверяйте согласованность конфигураций.

### Проверка

Перед запуском убедитесь, что:

- [ ] Все зависимости установлены корректно
- [ ] Файл конфигурации `.env` настроен правильно как в bot, так и в web
- [ ] 3X-UI установлен и работает корректно

После запуска убедитесь, что:

- [ ] Бот успешно подключился к 3X-UI и работает корректно
- [ ] Сайт доступен и корректно отображает информацию

---

## 🏗️ Архитектура проекта

```plaintext
├── bot/
│  ├── data/
│  │  ├── tarifs.json
│  │  └── ...
│  ├── langs/
│  │  ├── be.json
│  │  ├── de.json
│  │  ├── en.json
│  │  ├── ja.json
│  │  ├── pl.json
│  │  ├── ru.json
│  │  └── zh.json
│  ├── logs/
│  │  └── ...
│  ├── .env
│  ├── .env.example
│  ├── 3X-UI_API-doc.json
│  ├── BOT_API-doc.json
│  ├── deploy_bot.sh
│  ├── Dockerfile
│  ├── main.py
│  └── requirements.txt
├── deploy
│  └── Nginx-Proxy.conf
├── web/
│  ├── public/
│  │  ├── translations/
│  │  │  ├── legal/
│  │  │  │  ├── be.json
│  │  │  │  ├── de.json
│  │  │  │  ├── en.json
│  │  │  │  ├── ja.json
│  │  │  │  ├── pl.json
│  │  │  │  ├── ru.json
│  │  │  │  └── zh.json
│  │  │  ├── be.json
│  │  │  ├── de.json
│  │  │  ├── en.json
│  │  │  ├── ja.json
│  │  │  ├── pl.json
│  │  │  ├── ru.json
│  │  │  └── zh.json
│  │  ├── icon.jpg
│  │  └── manifest.json
│  ├── scripts/
│  │  └── generate-i18n.ts
│  ├── src/
│  │  ├── app/
│  │  │  ├── admin/
│  │  │  │  ├── debug/
│  │  │  │  │  └── page.tsx
│  │  │  │  ├── health/
│  │  │  │  │  └── page.tsx
│  │  │  │  ├── users/
│  │  │  │  │  └── page.tsx
│  │  │  │  └── page.tsx
│  │  │  ├── api/
│  │  │  │  └── admin/
│  │  │  │     ├── abuse-users/
│  │  │  │     │  └── route.ts
│  │  │  │     ├── debug/
│  │  │  │     │  ├── search/
│  │  │  │     │  │  └── route.ts
│  │  │  │     │  └── route.ts
│  │  │  │     ├── health/
│  │  │  │     │  └── route.ts
│  │  │  │     ├── panel-status/
│  │  │  │     │  └── route.ts
│  │  │  │     └── users/
│  │  │  │        ├── [user_id]/
│  │  │  │        │  └── clear-abuse/
│  │  │  │        │     └── route.ts
│  │  │  │        └── route.ts
│  │  │  ├── banned/
│  │  │  │  └── page.tsx
│  │  │  ├── client/
│  │  │  │  └── page.tsx
│  │  │  ├── login/
│  │  │  │  └── page.tsx
│  │  │  ├── manifest.json/
│  │  │  │  └── route.ts
│  │  │  ├── offer/
│  │  │  │  └── page.tsx
│  │  │  ├── partner/
│  │  │  │  └── page.tsx
│  │  │  ├── payment/
│  │  │  │  └── page.tsx
│  │  │  ├── privacy/
│  │  │  │  └── page.tsx
│  │  │  ├── profile/
│  │  │  │  └── page.tsx
│  │  │  ├── qa/
│  │  │  │  └── page.tsx
│  │  │  ├── referral/
│  │  │  │  └── page.tsx
│  │  │  ├── register/
│  │  │  │  └── page.tsx
│  │  │  ├── settings/
│  │  │  │  └── page.tsx
│  │  │  ├── subscribe/
│  │  │  │  └── page.tsx
│  │  │  ├── subscription/
│  │  │  │  └── page.tsx
│  │  │  ├── tos/
│  │  │  │  └── page.tsx
│  │  │  ├── error.tsx
│  │  │  ├── favicon.ico
│  │  │  ├── globals.css
│  │  │  ├── layout.tsx
│  │  │  ├── not-found.tsx
│  │  │  ├── page.tsx
│  │  │  ├── robots.ts
│  │  │  └── sitemap.ts
│  │  ├── components/
│  │  │  ├── AuthCallback.tsx
│  │  │  ├── BackToTop.tsx
│  │  │  ├── FaqList.tsx
│  │  │  ├── Header.tsx
│  │  │  ├── LiveStatusBar.tsx
│  │  │  ├── NodeGrid.tsx
│  │  │  ├── NodeStatus.tsx
│  │  │  ├── ScrollAnimations.tsx
│  │  │  ├── TariffGrid.tsx
│  │  │  ├── TariffGridClient.tsx
│  │  │  ├── ThemeInit.tsx
│  │  │  └── UserMenu.tsx
│  │  ├── contexts/
│  │  │  ├── AuthContext.tsx
│  │  │  ├── FeaturesContext.tsx
│  │  │  ├── LanguageContext.tsx
│  │  │  └── ThemeContext.tsx
│  │  ├── data/
│  │  │  └── legal.ts
│  │  └── lib/
│  │     ├── server/
│  │     │  └── admin-proxy.ts
│  │     ├── api.ts
│  │     ├── i18n-generated.ts
│  │     ├── i18n-server.ts
│  │     ├── i18n-types.ts
│  │     ├── i18n.ts
│  │     ├── navigation.ts
│  │     ├── structured-data.ts
│  │     ├── types.ts
│  │     └── validation.ts
│  ├── .env
│  ├── .env.example
│  ├── eslint.config.mjs
│  ├── next.config.ts
│  ├── package-lock.json
│  ├── package.json
│  ├── postcss.config.mjs
│  └── tsconfig.json
├── .gitignore
├── LICENSE
└── README.md
```

## 📊 Статистика проекта

| Метрика        | Значение                                                                                                                                                |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ⭐ Stars        | [![Stars](https://img.shields.io/github/stars/Major-Woolfi/VPN_service_for_3X-UI)](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/stargazers)                        |
| 🍴 Forks        | [![Forks](https://img.shields.io/github/forks/Major-Woolfi/VPN_service_for_3X-UI)](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/network/members)                   |
| 🐛 Issues       | [![Issues](https://img.shields.io/github/issues/Major-Woolfi/VPN_service_for_3X-UI)](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/issues)                          |
| 👥 Contributors | [![Contributors](https://img.shields.io/github/contributors/Major-Woolfi/VPN_service_for_3X-UI)](https://github.com/Major-Woolfi/VPN_service_for_3X-UI/graphs/contributors) |

---

## 🤝 Контрибьюция

Приветствуем любые вклад в проект! Перед созданием PR обязательно прочитай:

- 📋 [CONTRIBUTING](https://github.com/Major-Woolfi/.github/blob/main/community/CONTRIBUTING.md) - правила участия
- 💬 [CODE OF CONDUCT](https://github.com/Major-Woolfi/.github/blob/main/community/CODE_OF_CONDUCT.md) - кодекс поведения
- 🐛 [ISSUE TEMPLATE](https://github.com/Major-Woolfi/.github/tree/main/community/ISSUES.md) - шаблоны багов и фич
- 🔀 [PULL REQUEST TEMPLATE](https://github.com/Major-Woolfi/.github/blob/main/community/PULL_REQUEST_TEMPLATE.md) - требования к PR

Все общие правила хранятся в [репозитории `.github`](https://github.com/Major-Woolfi/.github) в папке `community`.

---

## 👥 Авторы и благодарности

<a href="https://github.com/Major-Woolfi/VPN_service_for_3X-UI/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Major-Woolfi/VPN_service_for_3X-UI" />
</a>

---

## 📄 Лицензия

Этот проект распространяется под лицензией **MIT**. Подробности в файле [LICENSE](LICENSE).

---

**⭐ Поставь звезду, если проект понравился!**

**[📧 Контакты](https://Major_Woolfi.t.me)**
