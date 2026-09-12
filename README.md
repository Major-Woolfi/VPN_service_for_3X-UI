# VPN_service_for_3X-UI - полноценный VPN-сервис для коммерческих VPN-проектов

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

### 🤖 Bot

#### Основное меню
Главное меню бота (через `build_main_keyboard`) доступно всем пользователям и администраторам:
- **Купить** - покупка/продление подписки
- **Моя подписка** - статус, трафик, VPN-ссылки (sub + JSON), продление
- **Настройка клиента** - инструкции и ссылки на приложения (INCY, v2RayNG, Happ, v2RayTun)
- **FAQ** - часто задаваемые вопросы
- **Реферальная система** - ваша реферальная ссылка
- **Стать партнёром** - заявка на партнёрство
- **Язык** - смена языка интерфейса (7 языков)
- **Сайт** - ссылка на веб-интерфейс
- **Поддержка** - ссылка на Telegram-чат поддержки
- **Публичная оферта / Политика конфиденциальности / Условия ИПП** - юридические ссылки (для админов: дополнительно «Ожидающие платежи», «Партнёрские заявки», «Инструменты отладки»)

#### Подписки
- **Бесплатный trial** - тестовая подписка автоматически создаётся при первом взаимодействии
- **6 готовых тарифов**: Try!, Simple, Medium, Medium +, Premium, Unlimited (см. `bot/data/tarifs.json`)
- **Кастомный тариф** - пошаговый мастер (4 шага): трафик (1-36500 ГБ), IP-лимит (1-15), срок (1-365 дней), локации (выбор из доступных inbound'ов). Цена рассчитывается по формуле: `total = base + GB × gb_coef + IP × D × ip_day_coef + ΣLOC × D`
- **Продление** - обновление конфигурации с сохранением данных пользователя
- **Удаление подписки** - очистка истекших/неактивных подписок (cleanup)

#### VPN-конфиги
- **Протоколы**: VLESS/REALITY (XRay 26.7.28+ с XHTTP-транспортом и REALITY-плагином)
- **Транспорт**: JSON-подписка (рекомендуется для INCY) или прямые VPN-ссылки
- **Настройка клиентов**:
  - **INCY** - лучший клиент, работает превосходно со всеми конфигами на всех устройствах, рекомендуем JSON-подписку
  - **v2RayNG** - стабильно работает на Android со всеми конфигами, кроме v2 (Shadowsocks), только в формате sub; JSON-подписка не работает
  - **Happ** - работает относительно стабильно, но только на JSON-подписке; требует настройки; не работает обход белых списков (WL-конфиги)
  - **v2RayTun** - работает стабильно на JSON-подписке, но требует настроек; на sub работает как v2RayNG
  - **iOS** - для всех клиентов (INCY, v2RayNG, Happ, v2RayTun) необходима ручная настройка конфигураций

#### Статистика трафика
- Отображение трафика по устройству и в агрегате
- Ручной и автоматический сброс (через админ-меню)

#### Платёжные системы
- **P2P перевод на карту** - ручная проверка (рекомендуется писать в поддержку через 5-10 минут с чеком)
- **ЮMoney (Быстрый платёж)** - ручная проверка (YooMoney для некириллических языков, ЮMoney для RU/BE)

#### Очки доверия (Trust Score)
- **Начисление**: 5% от суммы платежа за каждую покупку (максимум 100 очков)
- **Скидка**: применяется автоматически на всех тарифах (зависит от количества очков)
- **Штрафы**: -5 очков при исчерпании трафика, -10 при отклонённом платеже
- **Бан**: обнуляет очки доверия до 0
- **Настройка**: `TRUST_SCORE_MIN`, `TRUST_SCORE_MAX`, `TRUST_SCORE_EARN_PERCENT`, `TRUST_SCORE_MAX_DISCOUNT_PERCENT`, `TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED`, `TRUST_SCORE_PENALTY_PAYMENT_REJECTED` (в `.env`)
- **Управление админом**: добавление/убавление очков через debug-меню

#### Партнёрская программа
- **Реферальные ссылки** - ссылка для привлечения новых пользователей (бонус: +7 дней)
- **Партнёрство** - заявка с указанием соцсетей (Telegram, YouTube, TikTok), минимум 1000 подписчиков (по умолчанию, настраивается через `PARTNER_MIN_FOLLOWERS` в `.env`)
- **Личный кабинет партнёра**: баланс, статистика рефералов, вывод средств через СБП, бонусные дни (`PARTNER_BONUS_DAYS_MIN`-`PARTNER_BONUS_DAYS_MAX`) и очки доверия (`PARTNER_TRUST_POINTS_MIN`-`PARTNER_TRUST_POINTS_MAX`)
- **Период партёрства**: `PARTNER_MIN_PERIOD_MONTHS`-`PARTNER_MAX_PERIOD_MONTHS` месяцев
- **Комиссия**: `PARTNER_COMMISSION_PERCENT`% от суммы оплаты каждого привлечённого пользователя

#### Поддержка
- **Переписка** - прямой чат с администратором через Telegram (кнопка «Поддержка» в меню)

#### Уведомления
- **Напоминание об окончании подписки** - за `EXPIRY_ALERT_DAYS` дней (по умолчанию 7; настраивается в `.env`)
- **Рассылки** - администратор может отправить уведомление всем пользователям или только активным подписчикам

#### Технические особенности
- **Мультиязычность** - 7 языков (ru, en, de, pl, ja, zh, be)
- **FSM** - 30+ состояний для многошаговых сценариев (покупка, вывод, отладка, верификация платежа)
- **Фоновые задачи**: проверка подписок (expire), polling оплат, sync панелей 3X-UI, бэкапы БД, daily-статистика (интервал: `SUBSCRIPTION_CHECK_INTERVAL_SEC`, `PAYMENT_POLL_INTERVAL_SEC`)
- **3X-UI интеграция** - синхронизация клиентов/трафика, управление inbounds, health check панелей
- **Отладочное меню** - cleanup подписок, удаление подписок пользователей, поиск по UID/TID, скан ABUSE, управление trust points, нормализация подписок, техработы, компенсация днями, добавление трафика

#### Admin API
- FastAPI REST API с Bearer-авторизацией
- Эндпоинты: статистика (`/api/v1/stats`), пользователи (`/api/v1/admin/users`), платежи (`/api/v1/admin/payments`), выводы (`/api/v1/admin/withdrawals`), панели (`/api/v1/admin/panel-status`), рассылки (`/api/v1/admin/broadcast`)
- Авторизация через `BOT_API_KEY` и `BOT_ADMIN_KEY` (в `.env`)

### 🌐 Web

#### Структура страниц
Навигация (из `lib/navigation.ts`):
- **Публичные страницы**: Главная, FAQ, ToS, Публичная оферта, Политика конфиденциальности, Партнёры
- **Страницы для авторизованных**: Подписка, Личный кабинет, Клиент, Реферальная программа (скрыта для админов), Настройки
- **Админ-страницы**: Health (`/admin/health`), Пользователи (`/admin/users`), Debug (`/admin/debug`)
- **Страницы с ограничениями**: Бан (`/banned`), Ошибка 404 (`/not-found`)

#### Маршруты и их назначение
| Маршрут | Описание |
|---|---|
| `/` | Главная: статистика сервиса, живой статус серверов (LiveStatusBar, NodeGrid), сетка тарифов (TariffGrid), список фич |
| `/login` | Авторизация: логин/пароль или через Telegram (deep-link `start=web_login_<state>`) |
| `/register` | Регистрация аккаунта |
| `/subscribe` | Покупка/продление: выбор тарифа (6 готовых + кастомный), динамический расчёт цены, P2P на карту или ЮMoney (YooMoney) |
| `/profile` | Личный кабинет: статус подписки, план, срок, трафик с прогресс-баром, очки доверия + скидка, VPN-ссылки (VLESS и JSON), кнопка "Настроить клиента" |
| `/client` | Инструкции по настройке: VPN-ссылки и QR-коды для Android, iOS, Windows, macOS, Linux, Android TV, Router |
| `/settings` | Настройки: язык (7 языков), тема (localStorage + auto-detected), смена пароля, привязка/отвязка Telegram (через deep-link бота и API) |
| `/qa` | FAQ: поиск, категории, раскрывающиеся вопросы (15 Q&A) |
| `/referral` | Реферальная программа: статистика, реферальная ссылка |
| `/partner` | Партнёрская программа: заявка, личный кабинет, баланс, вывод |
| `/offer` | Публичная оферта (на 7 языках) |
| `/privacy` | Политика конфиденциальности (на 7 языках) |
| `/tos` | Условия использования (на 7 языках) |
| `/admin/health` | Админ: системное здоровье (статусы панелей, 3X-UI) |
| `/admin/users` | Админ: список пользователей (пагинация, поиск), ABUSE-управление |
| `/admin/debug` | Админ: инструменты отладки (cleanup подписок, поиск, ABUSE-скан) |
| `/banned` | Бан-страница (для забаненных пользователей) |
| `/payment` | Страница оплаты (перенаправление после выбора тарифа) |
| `/subscription` | Редирект на `/subscribe` (для обратной совместимости) |

#### Потоки данных
1. **Авторизация**: сайт аутентифицируется через bot API (`/api/v1/auth/*`), токен хранится в httpOnly cookie. Вход через логин/пароль или Telegram (deep-link `start=web_login_<state>` в боте).
2. **Подписка**: `/subscribe` → `getTariffs()` + `getLocations()` → выбор тарифа → `createCheckout()` (P2P) или прямая ссылка на YooMoney → подтверждение → `verifySubscription()`.
3. **Кастомный тариф**: `getCustomTariffParams()` → пошаговый ввод (трафик, IP, дни, локации) → `generateCustomTariff()` → динамическая цена → оплата.
4. **Профиль**: `getMe()` → статус подписки, трафик (`used_gb`/`traffic_gb`), trust_score, скидка. `getSubscriptionLink()` → VPN-ссылки (VLESS + JSON).

#### Особенности веб-интерфейса
- **SSR** - серверный рендеринг с i18n (`i18n-server.ts`)
- **PWA** - манифест для установки веб-приложения
- **Live статус серверов** - поллинг каждые 10с (NodeGrid, LiveStatusBar)
- **Тёмная/светлая тема** - localStorage + автоопределение системной темы (ThemeContext)
- **Мультиязычность** - 7 языков с SSR, локализацией и синхронизацией между компонентами (LanguageContext)
- **SEO** - sitemap.xml, robots.txt, Open Graph, Twitter Cards, JSON-LD, динамический sitemap
- **Адаптивный дизайн** - TailwindCSS с компонентами для всех устройств

---

## 🚀 Быстрый старт

### Предварительные требования

- Зависимости
  - bot
    - Runtime - Python 3.13.9+ (возможно и старше, тестирование не проводилось)
    - Библиотеки из requirements.txt
    - 3X-UI 3.0.0+ (на сервере)
    - Docker (для деплоя)
  - web
    - Runtime - Node.js 20+
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
