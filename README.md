# 🔐 VPN_bot_for_3X-UI - VPN-бот для комерческих VPN-проектов

[![Stars](https://img.shields.io/github/stars/Major-Woolfi/VPN_bot_for_3X-UI?style=social)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/stargazers)
[![Issues](https://img.shields.io/github/issues/Major-Woolfi/VPN_bot_for_3X-UI)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/issues)
[![License](https://img.shields.io/github/license/Major-Woolfi/VPN_bot_for_3X-UI)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](https://github.com/Major-Woolfi/.github/blob/main/community/CONTRIBUTING.md)
![Status](https://img.shields.io/badge/Status-active-brightgreen)

[🐛 Сообщить о баге](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/issues/new) •
[💡 Предложить идею](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/discussions)

> Советую также посмотреть тематические репозитории: [рабочие и стабильные конфигурации для XRay, панели 3X-UI и настройки клиентских приложений](https://github.com/Major-Woolfi/3X-UI-Configs) и [продвинутый бот-Inviter для пиара всеми способами](https://github.com/Major-Woolfi/Inviter)

---

## 📑 Содержание

- [🔐 VPN\_bot\_for\_3X-UI - VPN-бот для комерческих VPN-проектов](#-vpn_bot_for_3x-ui---vpn-бот-для-комерческих-vpn-проектов)
  - [📑 Содержание](#-содержание)
  - [📖 Описание проекта](#-описание-проекта)
    - [Идея и концепция](#идея-и-концепция)
    - [Полное описание](#полное-описание)
    - [Для кого этот проект](#для-кого-этот-проект)
  - [✨ Реализованные фичи](#-реализованные-фичи)
  - [🚀 Быстрый старт](#-быстрый-старт)
    - [Предварительные требования](#предварительные-требования)
    - [Установка](#установка)
    - [Конфигурация](#конфигурация)
    - [Запуск](#запуск)
    - [Проверка](#проверка)
  - [🏗️ Архитектура проекта](#️-архитектура-проекта)
  - [🛠️ Технологический стек](#️-технологический-стек)
  - [📊 Статистика проекта](#-статистика-проекта)
  - [🤝 Контрибьюция](#-контрибьюция)
  - [👥 Авторы и благодарности](#-авторы-и-благодарности)
  - [📄 Лицензия](#-лицензия)

## 📖 Описание проекта

### Идея и концепция

**VPN_bot_for_3X-UI** - это проект, созданный для решения конкретной задачи: автоматизация, упрощение и удешивление VPN-бизнеса.

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
- Кастомные подписки с гибкой настройкой
- Рассылки как пользователям, имеющим активную подписку, так и всем кто занесён в БД бота
- Отладочное меню
  - Режим тех.работ
  - Блокировка/разблокировка пользователей с указанием причин
  - Нормализатор подписок
  - Сброс тестовых периодов
  - Удаление подписки пользователя
  - Добавление трафика пользователю
- Раздел с помощью по настройке клиента и рекомендациями
- Гибкая реферальная система
- Блок социальных ссылок
- Удобное меню управления ожидающими платежами
- Мультиязычность

---

## 🚀 Быстрый старт

### Предварительные требования

- Зависимости
  - Runtime - Python 3.13.9+ (возможно и старше, тестирование не проводилось)
  - Библиотеки из requirements.txt
  - 3X-UI (на сервере)
  - Docker (для деплоя)
- Железо (выделеное под бота, минимум для запуска и корректной работы)
  - CPU 1 ядро 1Ггц
  - RAM 200мб
  - ROM 300мб

### Установка

```shell
# Клонируйте репозиторий
git clone https://github.com/Major-Woolfi/VPN_bot_for_3X-UI.git
cd VPN_bot_for_3X-UI
```

### Конфигурация

```shell
# Скопируйте файл переменных окружения
cp .env.example .env
# Отредактируйте .env под ваши нужды
```

### Запуск

```shell
cd /root/bots/VPN_bot_for_3X-UI/ || exit 1

docker build -t vpn_bot_for_3x-ui .
docker rm -f vpn_bot_for_3x-ui 2>/dev/null || true
docker run -d --name vpn_bot_for_3x-ui --restart always -v "$(pwd)":/app vpn_bot_for_3x-ui

echo "✅ Deployed! Logs: docker logs -f  vpn_bot_for_3x-ui "
```

> Вам нужно изменить путь в `cd` или переместить бота в соответствующую папку

### Проверка

Перед запуском убедитесь, что:

- [ ] Вы настроили все .env
- [ ] Вы изменили название проекта (`vpn_bot_for_3x-ui`, `VPN_bot_for_3X-UI`, `VPN_bot`, `vpn`, `vpn_bot`) на название своего проекта **В СООТВЕТСТВУЮЩЕМ РЕГИСТРЕ/ФОРМАТЕ**

---

## 🏗️ Архитектура проекта

```plaintext
├── data/
│  ├── tarifs.json
│  └── ...
├── langs/
│  ├── be.json
│  ├── de.json
│  ├── en.json
│  ├── ja.json
│  ├── pl.json
│  ├── ru.json
│  └── zh.json
├── logs/
│  └── ...
├── .env
├── .env.example
├── main.py
├── requirements.txt
├── Dockerfile
├── deploy_bot.sh
├── api_doc.json
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🛠️ Технологический стек

| Категория    | Технологии                 |
| ------------ | -------------------------- |
| **Backend**  | paramiko, aiohttp, urllib3 |
| **Frontend** | aiogram                    |
| **Database** | aiofiles, aiosqlite        |
| **DevOps**   | Docker, 3X-UI              |

> В `Backend`, `Frontend` и `Database` указаны библиотеки Python, т.к. это единственный язык который тут используется не считая языков на которых написаны сами библиотеки.

---

## 📊 Статистика проекта

| Метрика        | Значение                                                                                                                                                            |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ⭐ Stars        | [![Stars](https://img.shields.io/github/stars/Major-Woolfi/VPN_bot_for_3X-UI)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/stargazers)                        |
| 🍴 Forks        | [![Forks](https://img.shields.io/github/forks/Major-Woolfi/VPN_bot_for_3X-UI)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/network/members)                   |
| 🐛 Issues       | [![Issues](https://img.shields.io/github/issues/Major-Woolfi/VPN_bot_for_3X-UI)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/issues)                          |
| 👥 Contributors | [![Contributors](https://img.shields.io/github/contributors/Major-Woolfi/VPN_bot_for_3X-UI)](https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/graphs/contributors) |

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

<a href="https://github.com/Major-Woolfi/VPN_bot_for_3X-UI/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=Major-Woolfi/VPN_bot_for_3X-UI" />
</a>

---

## 📄 Лицензия

Этот проект распространяется под лицензией **MIT**. Подробности в файле [LICENSE](LICENSE).

---

**⭐ Поставь звезду, если проект понравился!**

**[📧 Контакты](https://Major_Woolfi.t.me)**
