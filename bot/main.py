import asyncio
import dataclasses
import hashlib
import hmac
import html
import json
import logging
import math
import os
import re
import secrets
import signal
import string
import sys
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, ClassVar, Self, TypeVar
from urllib.parse import quote, urlencode

import aiofiles
import aiohttp
import aiosqlite
import paramiko
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from dotenv import load_dotenv
from fastapi import (
    Body,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

# --- Настройка окружения ---
BASE_DIR: Path = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# --- Настройка логирования ---
LOGS_DIR: Path = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE: Path = LOGS_DIR / f"bot_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.log"

logger = logging.getLogger("bot")
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    file_handler: logging.FileHandler | None = None
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(LOGS_DIR, 0o755)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except (PermissionError, OSError) as e:
        logger.warning(f"Не удалось инициализировать файловый логгер: {e}")
    logger.info("=== Логгер инициализирован ===")

# --- Константы ---

# --- Типы для строгой типизации ---
T = TypeVar("T")
JSONValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonValue = dict[str, JSONValue]


# --- Кастомные исключения ---
class BotError(Exception):
    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ConfigError(BotError):
    def __init__(self, message: str):
        super().__init__(message, code=400)


class DatabaseError(BotError):
    def __init__(self, message: str, original_error: Exception | None = None):
        self.original_error = original_error
        super().__init__(message, code=500)


class PanelError(BotError):
    def __init__(self, message: str, status_code: int | None = None):
        self.status_code = status_code
        super().__init__(message, code=status_code or 500)


class ValidationError(BotError):
    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message, code=400)


# --- Утилиты логирования ---
_SENSITIVE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("BOT_TOKEN", re.compile(r"(\d+:[A-Za-z0-9_-]{3})[A-Za-z0-9_-]+", re.IGNORECASE)),
    ("PANEL_TOKEN", re.compile(r"(Bearer\s+)[A-Za-z0-9_-]{20,}", re.IGNORECASE)),
    ("API_KEY", re.compile(r"(api_key=)[A-Za-z0-9_-]{8,}", re.IGNORECASE)),
    ("SESSION_TOKEN", re.compile(r"(session_token=)[A-Za-z0-9_-]{8,}", re.IGNORECASE)),
    ("SECRET", re.compile(r"(secret=)[A-Za-z0-9_-]{8,}", re.IGNORECASE)),
    (
        "PASSWORD",
        re.compile(r"(password[_]?[hop]?[y]?[=:\s]+)[^\s,}\]]+", re.IGNORECASE),
    ),
    (
        "password_hash",
        re.compile(r'("password_hash"\s*:\s*)"([a-f0-9]{40,})"', re.IGNORECASE),
    ),
    (
        "session_token",
        re.compile(r'("session_token"\s*:\s*)"([a-zA-Z0-9_-]{20,})"', re.IGNORECASE),
    ),
    ("subId", re.compile(r'("subId"\s*:\s*)"([a-zA-Z0-9_-]{12,})"', re.IGNORECASE)),
]

_SENSITIVE_KEYS: set[str] = {
    "password",
    "password_hash",
    "session_token",
    "session_expires_at",
    "BOT_TOKEN",
    "PANEL_TOKEN",
    "PANEL_PASSWORD",
    "SSH_PASSWORD",
    "BOT_API_KEY",
    "BOT_ADMIN_KEY",
    "SESSION_SECRET",
}


def _mask_sensitive(data: Any) -> Any:
    if data is None:
        return "None"
    if isinstance(data, (int, float, bool)):
        return str(data)
    if isinstance(data, (dict, list, tuple, set)):
        if isinstance(data, dict):
            return {
                k: "***REDACTED***" if k in _SENSITIVE_KEYS else _mask_sensitive(v)
                for k, v in data.items()
            }
        return [_mask_sensitive(item) for item in data]
    text = str(data)
    for _name, pattern in _SENSITIVE_PATTERNS:
        text = pattern.sub(lambda m: m.group(0)[:12] + "***", text)
    if len(text) > 500:
        text = text[:500] + "... [truncated]"
    return text


def log_request(
    method: str,
    url: str,
    *,
    status: int = 0,
    duration_ms: float = 0.0,
    extra: str | None = None,
) -> None:
    safe_url = re.sub(r"(Bearer\s+)[A-Za-z0-9_-]{10,}", r"\1***", str(url))
    safe_url = re.sub(
        r"[?&](token|key|password|secret)=[^&]*",
        r"\1=***",
        safe_url,
        flags=re.IGNORECASE,
    )
    msg = f"{method} {safe_url} → {status} ({duration_ms:.0f}ms)"
    if extra:
        msg += f" | {extra}"
    logger.info(msg)


def log_error(func: Callable) -> Callable:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception:
            logger.exception(f"Ошибка в {func.__name__}")
            raise

    return wrapper


# --- Утилиты для работы с событиями ---
async def safe_send_message(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> bool:
    if not bot.session:
        logger.error(f"safe_send_message: сессия бота не инициализирована для user {user_id}")
        return False
    try:
        await bot.send_message(user_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return True
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if (
            "blocked" in error_msg
            or "bot was blocked" in error_msg
            or "chat not found" in error_msg
        ):
            return False
        try:
            await bot.send_message(
                user_id,
                text,
                reply_markup=reply_markup,
            )
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка отправки сообщения {user_id}: {e}")
            return False
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка отправки {user_id}: {e}")
        return False


async def smart_answer(
    event: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    delete_origin: bool = False,
) -> bool:
    try:
        if isinstance(event, Message):
            await event.answer(text, reply_markup=reply_markup)
        elif isinstance(event, CallbackQuery):
            if event.message:
                await event.message.answer(text, reply_markup=reply_markup)
                if delete_origin:
                    try:
                        await event.message.delete()
                    except Exception:  # noqa: BLE001, S110
                        pass
            try:
                await event.answer()
            except Exception:  # noqa: BLE001, S110
                pass
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"smart_answer error: {e}")
        return False


# --- Retry декоратор для самоисправления ---
async def retry_async(
    func: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type, ...] = (Exception,),
) -> Any:
    if max_retries <= 0:
        raise BotError("max_retries должен быть больше 0")

    last_exception: Exception | None = None

    for attempt in range(max_retries):
        try:
            return await func()
        except exceptions as e:
            last_exception = e
            if attempt < max_retries - 1:
                wait_time = delay * (backoff**attempt)
                logger.warning(
                    f"Повторная попытка {attempt + 1}/{max_retries} "
                    f"через {wait_time:.1f}с: {type(e).__name__}: {e}"
                )
                await asyncio.sleep(wait_time)
            else:
                logger.exception(f"Все {max_retries} попытки исчерпаны")

    if last_exception:
        raise last_exception

    raise BotError("Неизвестная ошибка в retry_async")


# --- Валидация данных ---
def validate_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_non_empty_string(value: Any, field_name: str = "value") -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} не может быть пустым", field_name)
    return text


def validate_positive_number(value: Any, field_name: str = "value") -> float:
    try:
        num = float(value)
        if num < 0:
            raise ValidationError(f"{field_name} должен быть положительным", field_name)
        return num
    except (ValueError, TypeError) as e:
        raise ValidationError(f"Некорректное значение {field_name}: {value}", field_name) from e


def validate_user_id(user_id: Any) -> bool:
    return isinstance(user_id, int) and user_id > 0


# --- In-memory cache for expiry alerts ---
_expiry_alert_cache: dict[int, float] = {}
_EXPIRY_ALERT_CACHE_MAX_SIZE: int = 10000
_EXPIRY_ALERT_CACHE_TTL: int = 86400


async def should_send_expiry_alert(user_id: int) -> bool:
    if not validate_user_id(user_id):
        logger.warning(f"Некорректный user_id для проверки уведомления: {user_id}")
        return False

    user_data = await db.get_user_by_any_id(user_id)
    if user_data and to_int(user_data.get("expiry_alert_sent"), 0) == 1:
        return False

    now = time.time()

    if len(_expiry_alert_cache) >= _EXPIRY_ALERT_CACHE_MAX_SIZE:
        _expiry_alert_cache.clear()

    last_alert = _expiry_alert_cache.get(user_id, 0)
    if now - last_alert > _EXPIRY_ALERT_CACHE_TTL:
        _expiry_alert_cache[user_id] = now
        return True
    return False


def str_to_bool(val: str) -> bool:
    return str(val).strip().lower() in ("1", "true", "yes", "y", "on")


def is_valid_bot_token_format(token: str) -> bool:
    return bool(re.fullmatch(r"\d+:[A-Za-z0-9_-]+", str(token or "").strip()))


def env_int(name: str, default: int = 0) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except Exception:  # noqa: BLE001
        return default


def env_float(name: str, default: float = 0.0) -> float:
    try:
        return float(str(os.getenv(name, default)).strip())
    except Exception:  # noqa: BLE001
        return default


def env_int_list(name: str) -> list[int]:
    values: list[int] = []
    for raw in os.getenv(name, "").split(","):
        item = raw.strip()
        if item:
            try:
                values.append(int(item))
            except Exception:  # noqa: BLE001
                logger.warning(f"Некорректное значение в {name}: {item}")
    return values


def resolve_local_path(value: Any, default: str = "") -> str:
    raw = str(value if value not in (None, "") else default).strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    resolved = path.resolve()
    try:
        resolved.relative_to(BASE_DIR.resolve())
    except ValueError:
        return ""
    return str(resolved)


class Config:
    VPN_NAME: str = os.getenv("VPN_NAME", "VPN").strip()

    DEFAULT_LANGUAGE: str = os.getenv("DEFAULT_LANGUAGE", "ru").strip().lower()
    DEFAULT_LANGUAGE_NAME: str = os.getenv("DEFAULT_LANGUAGE_NAME", "Русский").strip()

    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
    ADMIN_USER_IDS: list[int] = env_int_list("ADMIN_USER_IDS")
    ADMIN_AUTO_SUBSCRIBE_DAYS: int = env_int("ADMIN_AUTO_SUBSCRIBE_DAYS", 3650)

    FASTAPI_HOST: str = os.getenv("FASTAPI_HOST", "0.0.0.0").strip()
    FASTAPI_PORT: int = env_int("FASTAPI_PORT", 2005)
    FASTAPI_DOCS: bool = str_to_bool(os.getenv("FASTAPI_DOCS", "false"))
    FASTAPI_CORS_ENABLED: bool = str_to_bool(os.getenv("FASTAPI_CORS_ENABLED", "false"))
    BOT_API_ENABLED: bool = str_to_bool(os.getenv("BOT_API_ENABLED", "true"))
    FASTAPI_ALLOW_ORIGINS: str = os.getenv(
        "FASTAPI_ALLOW_ORIGINS",
        "http://localhost:3000,http://localhost:2005",
    ).strip()
    PANEL_HTTP_TIMEOUT_SEC: int = env_int("PANEL_HTTP_TIMEOUT_SEC", 15)
    SQLITE_TIMEOUT_SEC: int = env_int("SQLITE_TIMEOUT_SEC", 30)
    BOT_API_KEY: str = os.getenv("BOT_API_KEY", "").strip()
    BOT_ADMIN_KEY: str = os.getenv("BOT_ADMIN_KEY", "").strip()
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "").strip()
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "").strip() or SESSION_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = env_int("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", 15)
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = env_int("JWT_REFRESH_TOKEN_EXPIRE_DAYS", 7)
    SESSION_MAX_AGE: int = env_int("SESSION_MAX_AGE", 21600)
    PASSWORD_MIN_LENGTH: int = env_int("PASSWORD_MIN_LENGTH", 10)

    PAYMENT_CARD_NUMBER: str = os.getenv("PAYMENT_CARD_NUMBER", "").strip()
    YOOMONEY_WALLET: str = os.getenv("YOOMONEY_WALLET", "").strip()
    PAYMENT_PROCESSING_TIMEOUT_SEC: int = env_int("PAYMENT_PROCESSING_TIMEOUT_SEC", 900)

    PANEL_BASE: str = os.getenv("PANEL_BASE", "").rstrip("/")
    SUB_PANEL_BASE: str = os.getenv("SUB_PANEL_BASE", "").rstrip("/")
    JSON_SUB_PANEL_BASE: str = os.getenv("JSON_SUB_PANEL_BASE", "").rstrip("/")
    PANEL_LOGIN: str = os.getenv("PANEL_LOGIN", "").strip()
    PANEL_PASSWORD: str = os.getenv("PANEL_PASSWORD", "").strip()
    PANEL_TOKEN: str = os.getenv("PANEL_TOKEN", "").strip()
    VERIFY_SSL: bool = str_to_bool(os.getenv("VERIFY_SSL", "true"))

    LANGS_DIR: str = resolve_local_path(os.getenv("LANGS_DIR"), "langs")
    DATA_DIR: str = resolve_local_path(os.getenv("DATA_DIR"), "data")
    DATA_FILE: str = resolve_local_path(os.getenv("DATA_FILE"), os.path.join(DATA_DIR, "users.db"))
    DATA_AWAIT: str = resolve_local_path(
        os.getenv("DATA_AWAIT"), os.path.join(DATA_DIR, "await_payments.json")
    )
    TARIFFS_PATH: str = resolve_local_path(
        os.getenv("TARIFFS_PATH"), os.path.join(DATA_DIR, "tarifs.json")
    )
    PARTNER_OPS_FILE: str = resolve_local_path(
        os.getenv("PARTNER_OPS_FILE"),
        os.path.join("data", "partner_operations.json"),
    )

    SSH_HOST: str = os.getenv("SSH_HOST", "").strip()
    SSH_USER: str = os.getenv("SSH_USER", "root").strip()
    SSH_KEY_PATH: str = os.getenv("SSH_KEY_PATH", "").strip()
    SSH_PASSWORD: str = os.getenv("SSH_PASSWORD", "").strip()

    SITE_URL: str = os.getenv("SITE_URL", "").strip()
    SUPPORT_URL: str = os.getenv("SUPPORT_URL", "").strip()
    QNA_URL: str = os.getenv("QNA_URL", "").strip()
    PRIVACY_POLICY_URL: str = os.getenv("PRIVACY_POLICY_URL", "").strip()
    PUBLIC_OFFER_URL: str = os.getenv("PUBLIC_OFFER_URL", "").strip()
    TIKTOK_URL: str = os.getenv("TIKTOK_URL", "").strip()
    YOUTUBE_URL: str = os.getenv("YOUTUBE_URL", "").strip()
    TELEGRAM_URL: str = os.getenv("TELEGRAM_URL", "").strip()
    SETUP_GUIDE_URL: str = os.getenv("SETUP_GUIDE_URL", "").strip()
    CLIENT_APP_URL: str = os.getenv("CLIENT_APP_URL", "").strip()
    TERMS_OF_SERVICE_URL: str = os.getenv("TERMS_OF_SERVICE_URL", "").strip()

    EXPIRY_ALERT_DAYS: int = env_int("EXPIRY_ALERT_DAYS", 7)

    REF_BONUS_DAYS: int = env_int("REF_BONUS_DAYS", 7)

    TRUST_SCORE_MIN: int = env_int("TRUST_SCORE_MIN", 0)
    TRUST_SCORE_MAX: int = env_int("TRUST_SCORE_MAX", 100)

    TECH_WORK_BACKUP_INBOUND: str = os.getenv("TECH_WORK_BACKUP_INBOUND", "").strip()
    TRUST_SCORE_EARN_PERCENT: int = env_int("TRUST_SCORE_EARN_PERCENT", 5)
    TRUST_SCORE_MAX_DISCOUNT_PERCENT: int = env_int("TRUST_SCORE_MAX_DISCOUNT_PERCENT", 50)
    TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED: int = env_int("TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED", 5)
    TRUST_SCORE_PENALTY_PAYMENT_REJECTED: int = env_int("TRUST_SCORE_PENALTY_PAYMENT_REJECTED", 10)

    CUSTOM_TARIFF_ENABLED: bool = str_to_bool(os.getenv("CUSTOM_TARIFF_ENABLED", "false"))
    CUSTOM_TARIFF_MIN_IP: int = env_int("CUSTOM_TARIFF_MIN_IP", 1)
    CUSTOM_TARIFF_MAX_IP: int = env_int("CUSTOM_TARIFF_MAX_IP", 30)
    CUSTOM_TARIFF_MIN_GB: int = env_int("CUSTOM_TARIFF_MIN_GB", 1)
    CUSTOM_TARIFF_MAX_GB: int = env_int("CUSTOM_TARIFF_MAX_GB", 36500)
    CUSTOM_TARIFF_MIN_DAYS: int = env_int("CUSTOM_TARIFF_MIN_DAYS", 1)
    CUSTOM_TARIFF_MAX_DAYS: int = env_int("CUSTOM_TARIFF_MAX_DAYS", 365)
    CUSTOM_TARIFF_BASE_PRICE: float = env_float("CUSTOM_TARIFF_BASE_PRICE", 20.0)
    CUSTOM_TARIFF_GB_COEF: float = env_float("CUSTOM_TARIFF_GB_COEF", 0.2)
    CUSTOM_TARIFF_IP_DAY_COEF: float = env_float("CUSTOM_TARIFF_IP_DAY_COEF", 1.5)
    CUSTOM_TARIFF_LOCATION_DAY_PRICE: float = env_float("CUSTOM_TARIFF_LOCATION_DAY_PRICE", 2.0)

    PARTNER_ENABLED: bool = str_to_bool(os.getenv("PARTNER_ENABLED", "true"))
    PARTNER_MIN_FOLLOWERS: int = env_int("PARTNER_MIN_FOLLOWERS", 1000)
    PARTNER_MIN_AVG_REACH: int = env_int("PARTNER_MIN_AVG_REACH", 5000)
    PARTNER_REQUIRED_SOCIALS: str = os.getenv(
        "PARTNER_REQUIRED_SOCIALS", "telegram,youtube,tiktok"
    ).strip()
    PARTNER_TERMS_URL: str = os.getenv("PARTNER_TERMS_URL", "").strip()
    PARTNER_MIN_PERIOD_MONTHS: int = env_int("PARTNER_MIN_PERIOD_MONTHS", 1)
    PARTNER_MAX_PERIOD_MONTHS: int = env_int("PARTNER_MAX_PERIOD_MONTHS", 12)
    PARTNER_BONUS_DAYS_MIN: int = env_int("PARTNER_BONUS_DAYS_MIN", 3)
    PARTNER_BONUS_DAYS_MAX: int = env_int("PARTNER_BONUS_DAYS_MAX", 10)
    PARTNER_TRUST_POINTS_MIN: int = env_int("PARTNER_TRUST_POINTS_MIN", 10)
    PARTNER_TRUST_POINTS_MAX: int = env_int("PARTNER_TRUST_POINTS_MAX", 40)
    PARTNER_COMMISSION_PERCENT: int = env_int("PARTNER_COMMISSION_PERCENT", 10)
    PARTNER_EXPIRY_GRACE_DAYS: int = env_int("PARTNER_EXPIRY_GRACE_DAYS", 7)

    RATE_LIMIT_COOLDOWN: float = env_float("RATE_LIMIT_COOLDOWN", 0.3)
    API_RATE_LIMIT: int = env_int("API_RATE_LIMIT", 60)
    API_RATE_WINDOW: int = env_int("API_RATE_WINDOW", 60)
    API_RATE_LIMIT_SENSITIVE_MAX: int = env_int("API_RATE_LIMIT_SENSITIVE_MAX", 10)
    API_RATE_LIMIT_SENSITIVE_WINDOW: int = env_int("API_RATE_LIMIT_SENSITIVE_WINDOW", 60)

    SUBSCRIPTION_CHECK_INTERVAL_SEC: int = env_int("SUBSCRIPTION_CHECK_INTERVAL_SEC", 3600)
    TRAFFIC_ABUSE_CHECK_INTERVAL_SEC: int = env_int("TRAFFIC_ABUSE_CHECK_INTERVAL_SEC", 86400)
    TRAFFIC_ABUSE_DAILY_LIMIT_GB: float = env_float("TRAFFIC_ABUSE_DAILY_LIMIT_GB", 50.0)
    TRAFFIC_ABUSE_TOTAL_LIMIT_GB: float = env_float("TRAFFIC_ABUSE_TOTAL_LIMIT_GB", 1000.0)
    PAYMENT_CLEANUP_INTERVAL_SEC: int = env_int("PAYMENT_CLEANUP_INTERVAL_SEC", 259200)

    @classmethod
    def required_socials_list(cls) -> list[str]:
        return [s.strip().lower() for s in cls.PARTNER_REQUIRED_SOCIALS.split(",") if s.strip()]

    @classmethod
    def validate(cls) -> None:
        errors: list[str] = []

        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не установлен")

        if len(cls.BOT_API_KEY) < 32:
            errors.append("BOT_API_KEY должен быть уникальным ключом не короче 32 символов")

        if len(cls.BOT_ADMIN_KEY) < 32:
            errors.append("BOT_ADMIN_KEY должен быть уникальным ключом не короче 32 символов")

        if not cls.PANEL_BASE:
            errors.append("PANEL_BASE не установлен")

        if not (cls.PANEL_TOKEN or (cls.PANEL_LOGIN and cls.PANEL_PASSWORD)):
            errors.append(
                "Не настроена авторизация в панели (PANEL_TOKEN или PANEL_LOGIN+PANEL_PASSWORD)"
            )

        if cls.FASTAPI_CORS_ENABLED:
            if not cls.FASTAPI_ALLOW_ORIGINS:
                errors.append("FASTAPI_ALLOW_ORIGINS не установлен")
            elif "*" in {origin.strip() for origin in cls.FASTAPI_ALLOW_ORIGINS.split(",")}:
                errors.append("FASTAPI_ALLOW_ORIGINS не может содержать *")
            else:
                origins = [o.strip() for o in cls.FASTAPI_ALLOW_ORIGINS.split(",") if o.strip()]
                if len(origins) != len(set(origins)):
                    errors.append("FASTAPI_ALLOW_ORIGINS содержит дубликаты")

        if not cls.SESSION_SECRET:
            errors.append("SESSION_SECRET не установлен")

        if not cls.JWT_SECRET_KEY:
            errors.append("JWT_SECRET_KEY не установлен")

        if cls.SESSION_MAX_AGE <= 0:
            errors.append("SESSION_MAX_AGE должен быть больше 0")

        if (
            len(cls.SESSION_SECRET) < 32
            or cls.SESSION_SECRET == "change-this-to-a-random-secret-string"
        ):
            errors.append("SESSION_SECRET должен быть уникальной строкой не короче 32 символов")

        if len(cls.JWT_SECRET_KEY) < 32:
            errors.append("JWT_SECRET_KEY должен быть уникальной строкой не короче 32 символов")

        if not os.getenv("SESSION_COOKIE_SECURE"):
            logger.warning("SESSION_COOKIE_SECURE использует значение по умолчанию (true)")

        if not cls.VPN_NAME or cls.VPN_NAME == "VPN":
            errors.append("VPN_NAME не установлен (не может быть пустым или 'VPN')")

        if not cls.SUB_PANEL_BASE and not cls.JSON_SUB_PANEL_BASE:
            errors.append(
                "Хотя бы один SUB_PANEL_BASE или JSON_SUB_PANEL_BASE должен быть настроен"
            )

        if not cls.ADMIN_USER_IDS:
            errors.append("ADMIN_USER_IDS не установлен")

        if errors:
            error_msg = "Ошибка конфигурации:\n" + "\n".join(f"  • {e}" for e in errors)
            logger.critical(error_msg)
            raise ConfigError(error_msg)


# --- JWT утилиты ---
def _create_admin_jwt(admin_id: int = 0, *, refresh: bool = False) -> str:
    now = datetime.now(timezone.utc)
    if refresh:
        expire = now + timedelta(days=Config.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    else:
        expire = now + timedelta(minutes=Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": "admin",
        "admin_id": admin_id,
        "type": "refresh" if refresh else "access",
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM)


def _verify_admin_jwt(token: str) -> dict[str, Any] | None:
    try:
        payload = jwt.decode(token, Config.JWT_SECRET_KEY, algorithms=[Config.JWT_ALGORITHM])
        if payload.get("sub") != "admin":
            return None
        return payload
    except JWTError:
        return None


def _is_valid_admin_jwt(token: str | None) -> bool:
    if not token or not Config.JWT_SECRET_KEY:
        return False
    payload = _verify_admin_jwt(token)
    return payload is not None


def _is_admin_token(token: str | None) -> bool:
    if not token:
        return False
    return _is_valid_admin_jwt(token) or bool(
        Config.BOT_ADMIN_KEY and secrets.compare_digest(token, Config.BOT_ADMIN_KEY)
    )


# --- Features ---
class Features:
    @staticmethod
    def available_panel_types() -> dict[str, bool]:
        return {
            "main": bool(Config.SUB_PANEL_BASE),
            "json": bool(Config.JSON_SUB_PANEL_BASE),
        }

    @staticmethod
    def available_payment_methods() -> list[str]:
        methods: list[str] = []
        if Config.YOOMONEY_WALLET:
            methods.append("yoomoney")
        if Config.PAYMENT_CARD_NUMBER:
            methods.append("card")
        return methods

    @staticmethod
    def custom_tariff_available() -> bool:
        return bool(Config.CUSTOM_TARIFF_ENABLED)

    @staticmethod
    def features_dict() -> dict[str, bool]:
        return {
            "custom_tariff": Features.custom_tariff_available(),
            "partner": Features.partner_available(),
            "telegram_login": bool(BOT_USERNAME),
            "main_panel": bool(Config.SUB_PANEL_BASE),
            "json_panel": bool(Config.JSON_SUB_PANEL_BASE),
            "card_payment": bool(Config.PAYMENT_CARD_NUMBER),
            "yoomoney_payment": bool(Config.YOOMONEY_WALLET),
        }

    @staticmethod
    def has_any_panel() -> bool:
        return bool(Config.PANEL_BASE)

    @staticmethod
    def partner_available() -> bool:
        return bool(Config.PARTNER_ENABLED)

    @staticmethod
    def payment_methods_count() -> int:
        return len(Features.available_payment_methods())

    @staticmethod
    def public_links() -> dict[str, str]:
        links: dict[str, str] = {}
        for key, attr in (
            ("site_url", "SITE_URL"),
            ("support_url", "SUPPORT_URL"),
            ("qna_url", "QNA_URL"),
            ("privacy_policy_url", "PRIVACY_POLICY_URL"),
            ("public_offer_url", "PUBLIC_OFFER_URL"),
            ("tiktok_url", "TIKTOK_URL"),
            ("youtube_url", "YOUTUBE_URL"),
            ("telegram_url", "TELEGRAM_URL"),
            ("setup_guide_url", "SETUP_GUIDE_URL"),
            ("client_app_url", "CLIENT_APP_URL"),
            ("terms_of_service_url", "TERMS_OF_SERVICE_URL"),
        ):
            value = getattr(Config, attr, "").strip()
            if value:
                links[key] = value
        return links

    @staticmethod
    def validate() -> list[str]:
        errors: list[str] = []

        if not Config.BOT_TOKEN:
            errors.append("BOT_TOKEN не установлен")

        if not Config.ADMIN_USER_IDS:
            errors.append("ADMIN_USER_IDS не установлен")

        if not Features.has_any_panel():
            errors.append("PANEL_BASE не настроен")

        panel_types = Features.available_panel_types()
        if not panel_types.get("main") and not panel_types.get("json"):
            errors.append(
                "Хотя бы один SUB_PANEL_BASE или JSON_SUB_PANEL_BASE должен быть настроен"
            )

        if not Features.available_payment_methods():
            errors.append(
                "Ни один метод оплаты не настроен (YOOMONEY_WALLET или PAYMENT_CARD_NUMBER)"
            )

        if not Config.PANEL_TOKEN and not (Config.PANEL_LOGIN and Config.PANEL_PASSWORD):
            errors.append(
                "Не настроена авторизация в панели (PANEL_TOKEN или PANEL_LOGIN+PANEL_PASSWORD)"
            )

        return errors


try:
    os.makedirs(Config.DATA_DIR, exist_ok=True)
except Exception as e:  # noqa: BLE001
    logger.warning(f"Не удалось создать DATA_DIR: {e}")

ADMIN_USER_ID_SET = set(Config.ADMIN_USER_IDS)
BYTES_IN_GB = 1073741824
SECONDS_IN_DAY = 86400
SECONDS_IN_HOUR = 3600
SECONDS_IN_YEAR = 31536000
BEARER_PREFIX = "Bearer "

_admin_startup_completed: bool = False


def hash_session_token(token: str) -> str:
    return hmac.new(
        Config.SESSION_SECRET.encode("utf-8"), token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


# --- Session cookie helpers ---
SESSION_COOKIE_NAME: str = "vpn_token"
_SESSION_COOKIE_SAMESITE: str = "lax"
_SESSION_COOKIE_SECURE: bool = bool(
    os.getenv("SESSION_COOKIE_SECURE", "true").lower() in ("1", "true", "yes", "on")
)


def _build_clear_session_cookie_header() -> str:
    parts = [
        f"{SESSION_COOKIE_NAME}=",
        "Path=/",
        "HttpOnly",
        f"SameSite={_SESSION_COOKIE_SAMESITE}",
        "Max-Age=0",
    ]
    if _SESSION_COOKIE_SECURE:
        parts.append("Secure")
    return "; ".join(parts)


def _build_session_cookie_header(token: str, *, max_age: int | None = None) -> str:
    parts = [f"{SESSION_COOKIE_NAME}={token}"]
    parts.append("Path=/")
    parts.append("HttpOnly")
    parts.append(f"SameSite={_SESSION_COOKIE_SAMESITE}")
    if _SESSION_COOKIE_SECURE:
        parts.append("Secure")
    if max_age is None:
        max_age = int(Config.SESSION_MAX_AGE)
    parts.append(f"Max-Age={max_age}")
    return "; ".join(parts)


def _cookie_headers_clear() -> dict[str, str]:
    return {"Set-Cookie": _build_clear_session_cookie_header()}


def _cookie_headers_for_session(token: str, *, max_age: int | None = None) -> dict[str, str]:
    return {"Set-Cookie": _build_session_cookie_header(token, max_age=max_age)}


# --- Rate limiting ---
_user_request_times: dict[int, float] = {}
_subscription_creation_locks: dict[int, asyncio.Lock] = {}

# --- Brute force protection for auth endpoints ---
_auth_failures: dict[str, dict[str, Any]] = {}
_AUTH_MAX_FAILURES = 5
_AUTH_LOCKOUT_SECONDS = 300
_AUTH_FAILURE_TTL = 600
_registrations_per_ip: dict[str, list[float]] = {}
_REGISTRATION_LIMIT = 10
_REGISTRATION_WINDOW = 3600


def _cleanup_registrations_per_ip() -> None:
    now = time.time()
    expired = [
        ip
        for ip, times in _registrations_per_ip.items()
        if not times or now - times[-1] > _REGISTRATION_WINDOW
    ]
    for ip in expired:
        del _registrations_per_ip[ip]


def get_subscription_lock(user_id: int) -> asyncio.Lock:
    if user_id not in _subscription_creation_locks:
        _subscription_creation_locks[user_id] = asyncio.Lock()
    return _subscription_creation_locks[user_id]


def _get_auth_key(username: str, client_ip: str) -> str:
    return f"{username.strip().lower()}:{client_ip}"


def _check_auth_lockout(username: str, client_ip: str) -> int | None:
    key = _get_auth_key(username, client_ip)
    record = _auth_failures.get(key)
    if not record:
        return None
    now = time.time()
    if now - record.get("last_failure", 0) > _AUTH_LOCKOUT_SECONDS:
        del _auth_failures[key]
        return None
    if record.get("count", 0) >= _AUTH_MAX_FAILURES:
        remaining = _AUTH_LOCKOUT_SECONDS - (now - record.get("last_failure", 0))
        return max(0, int(remaining))
    return None


def _record_auth_failure(username: str, client_ip: str) -> None:
    key = _get_auth_key(username, client_ip)
    now = time.time()
    _auth_failures[key] = {
        "count": _auth_failures.get(key, {}).get("count", 0) + 1,
        "last_failure": now,
    }
    if len(_auth_failures) > 10000:
        oldest = min(_auth_failures.items(), key=lambda x: x[1].get("last_failure", 0))
        if oldest:
            del _auth_failures[oldest[0]]
    expired_keys = [
        k for k, v in _auth_failures.items() if now - v.get("last_failure", 0) > _AUTH_FAILURE_TTL
    ]
    for k in expired_keys:
        del _auth_failures[k]


def _clear_auth_failures(username: str, client_ip: str) -> None:
    key = _get_auth_key(username, client_ip)
    _auth_failures.pop(key, None)


async def _notify_account_change(user_id: int, text_template: str, **kwargs: Any) -> None:
    user = await db.get_user_by_any_id(user_id)
    if not user:
        return
    tg_id = user.get("telegram_id", 0)
    if not tg_id:
        return
    lang = await db.get_user_language_by_user_id(user_id) or Config.DEFAULT_LANGUAGE
    try:
        await safe_send_message(bot, tg_id, translate(lang, text_template, **kwargs))
    except Exception:  # noqa: BLE001, S110
        pass


# --- Tech work mode ---
class TechWorkService:
    def __init__(self) -> None:
        self._enabled = False
        self._lock = asyncio.Lock()
        self._original_inbounds: dict[str, list[int]] = {}

    def clear_original_inbounds(self) -> None:
        self._original_inbounds.clear()

    def get_backup_inbound_id(self) -> int | None:
        if not Config.TECH_WORK_BACKUP_INBOUND:
            return None
        return None

    def get_original_inbounds(self, email: str) -> list[int] | None:
        return self._original_inbounds.get(email)

    def is_enabled(self) -> bool:
        return self._enabled

    def save_original_inbounds(self, email: str, inbound_ids: list[int]) -> None:
        if email not in self._original_inbounds:
            self._original_inbounds[email] = inbound_ids

    async def set_enabled(self, enabled: bool) -> bool:
        async with self._lock:
            self._enabled = enabled
            if not enabled:
                self._original_inbounds.clear()
            logger.info(f"Тех. работы {'ВКЛЮЧЕНЫ' if enabled else 'ВЫКЛЮЧЕНЫ'}")
            return self._enabled


tech_work_service = TechWorkService()


async def disconnect_all_subscriptions(reason: str) -> dict[str, int]:
    result = {"total": 0, "success": 0, "failed": 0}
    try:
        user_ids = await db.get_subscribed_user_ids()
        result["total"] = len(user_ids)
        users_list = await db.get_users_by_telegram_ids(user_ids)
        users_by_tgid = {u["telegram_id"]: u for u in users_list}

        for user_id in user_ids:
            try:
                user = users_by_tgid.get(user_id)
                sub_id = normalize_sub_id(user.get("vpn_url")) if user else ""
                if sub_id:
                    if await panel.disconnect_subscription(sub_id):
                        result["success"] += 1
                        logger.info(f"Подписка отключена для user {user_id}: {reason}")
                    else:
                        result["failed"] += 1
                else:
                    result["failed"] += 1
            except Exception as e:  # noqa: BLE001
                result["failed"] += 1
                logger.error(f"Ошибка отключения для user {user_id}: {e}")
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка при отключении всех подписок: {e}")

    return result


async def switch_all_clients_to_backup() -> dict[str, int]:
    result = {"total": 0, "switched": 0, "failed": 0, "skipped": 0}
    if not Config.TECH_WORK_BACKUP_INBOUND:
        logger.warning("TECH_WORK_BACKUP_INBOUND не настроен")
        return result

    backup_inbound_id = await panel.get_inbound_id_by_name(Config.TECH_WORK_BACKUP_INBOUND)
    if not backup_inbound_id:
        logger.error(f"Backup inbound '{Config.TECH_WORK_BACKUP_INBOUND}' не найден на панели")
        return result

    try:
        clients = await panel.get_all_clients()
        if not clients:
            logger.warning("Нет клиентов для переключения")
            return result

        result["total"] = len(clients)
        for client_row in clients:
            email = str(client_row.get("email") or "")
            if not email:
                result["skipped"] += 1
                continue

            current_inbounds = client_row.get("inboundIds") or []
            current_inbounds_ints = sorted(
                {to_int(x, 0) for x in current_inbounds if to_int(x, 0) > 0}
            )

            if not current_inbounds_ints:
                result["skipped"] += 1
                continue

            tech_work_service.save_original_inbounds(email, current_inbounds_ints)

            if backup_inbound_id in current_inbounds_ints and len(current_inbounds_ints) == 1:
                result["skipped"] += 1
                continue

            try:
                client = await panel.get_client_by_email(email)
                if not client:
                    client = client_row

                clean_ids = [
                    to_int(x, 0)
                    for x in current_inbounds
                    if to_int(x, 0) > 0 and x != backup_inbound_id
                ]
                new_inbounds = [backup_inbound_id] + clean_ids
                payload = panel._client_payload_for_update(client)
                payload["inboundIds"] = new_inbounds
                payload["enable"] = True

                url = f"{panel.apibase}/panel/api/clients/update/{panel._quote_path(email)}"
                status, data, _ = await panel._request_json_with_reauth(
                    "POST", url, headers=panel._headers(), json=payload
                )
                if status in (200, 201) and data.get("success"):
                    result["switched"] += 1
                    logger.info(f"Клиент {email} переключен на backup inbound {backup_inbound_id}")
                else:
                    result["failed"] += 1
                    logger.error(f"Ошибка переключения {email}: {data.get('msg')}")
            except (
                aiohttp.ClientError,
                asyncio.TimeoutError,
                KeyError,
                ValueError,
                OSError,
            ) as e:
                result["failed"] += 1
                logger.error(f"Исключение при переключении {email}: {e}")

    except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
        logger.error(f"Ошибка при переключении клиентов на backup: {e}")

    return result


async def restore_all_clients_from_backup() -> dict[str, int]:
    result = {"total": 0, "restored": 0, "failed": 0, "skipped": 0}
    original_inbounds = tech_work_service._original_inbounds

    if not original_inbounds:
        logger.info("Нет сохранённых оригинальных inbound для восстановления")
        return result

    result["total"] = len(original_inbounds)

    for email, original_ids in original_inbounds.items():
        if not original_ids:
            result["skipped"] += 1
            continue

        try:
            client = await panel.get_client_by_email(email)
            if not client:
                result["failed"] += 1
                logger.error(f"Клиент {email} не найден для восстановления")
                continue

            client["enable"] = True
            client["inboundIds"] = original_ids
            payload = panel._client_payload_for_update(client)

            url = f"{panel.apibase}/panel/api/clients/update/{panel._quote_path(email)}"
            status, data, _ = await panel._request_json_with_reauth(
                "POST", url, headers=panel._headers(), json=payload
            )
            if status in (200, 201) and data.get("success"):
                result["restored"] += 1
                logger.info(f"Клиент {email} восстановлен на inbound {original_ids}")
            else:
                result["failed"] += 1
                logger.error(f"Ошибка восстановления {email}: {data.get('msg')}")
        except (
            aiohttp.ClientError,
            asyncio.TimeoutError,
            KeyError,
            ValueError,
            OSError,
        ) as e:
            result["failed"] += 1
            logger.error(f"Исключение при восстановлении {email}: {e}")

    tech_work_service.clear_original_inbounds()
    return result


async def notify_all_users(message: str) -> dict[str, int]:
    result = {"sent": 0, "failed": 0, "no_subscription": 0}

    try:
        user_ids = await db.get_subscribed_user_ids()
        users_list = await db.get_users_by_telegram_ids(user_ids)
        users_by_tgid = {u["telegram_id"]: u for u in users_list}

        for user_id in user_ids:
            user = users_by_tgid.get(user_id)
            if user and normalize_sub_id(user.get("vpn_url")):
                try:
                    if await safe_send_message(bot, user_id, message):
                        result["sent"] += 1
                    else:
                        result["failed"] += 1
                    logger.info(f"Уведомление отправлено user {user_id}")
                except Exception as e:  # noqa: BLE001
                    result["failed"] += 1
                    logger.error(f"Ошибка отправки уведомления user {user_id}: {e}")
            else:
                result["no_subscription"] += 1
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка при отправке уведомлений: {e}")

    return result


async def compensate_all_users(days: int) -> dict[str, int]:
    result = {"processed": 0, "errors": 0}

    if days <= 0:
        logger.warning(f"Компенсация: некорректное число дней ({days})")
        return result

    try:
        user_ids = await db.get_subscribed_user_ids()
        logger.info(f"Компенсация {days} дней для {len(user_ids)} пользователей")

        semaphore = asyncio.Semaphore(10)

        async def _compensate(uid: int) -> bool:
            async with semaphore:
                try:
                    user = await db.get_user_by_any_id(uid)
                    internal_uid = user.get("user_id", uid) if user else uid
                    base_email = build_base_email(internal_uid)
                    extended = await panel.extend_client_expiry(base_email, days)
                    if extended:
                        logger.info("✓ Компенсация %s дней для user %s", days, uid)
                        return True
                    logger.warning(
                        "✗ Не удалось продлить user %s (клиент не найден на панели)",
                        uid,
                    )
                    return False
                except Exception as e:  # noqa: BLE001
                    logger.error("✗ Ошибка компенсации для user %s: %s", uid, type(e).__name__)
                    return False

        results = await asyncio.gather(
            *[_compensate(uid) for uid in user_ids], return_exceptions=False
        )
        result["processed"] = sum(1 for r in results if r)
        result["errors"] = len(results) - result["processed"]
    except Exception:
        logger.exception("Ошибка при компенсации")

    logger.info(f"Компенсация завершена: {result}")
    return result


# --- Языки и перевод ---
def load_languages() -> dict[str, dict[str, Any]]:
    languages: dict[str, dict[str, Any]] = {}
    langs_dir = Path(Config.LANGS_DIR) if Config.LANGS_DIR else None
    if not langs_dir or not langs_dir.exists():
        logger.warning(f"Папка языков не найдена: {langs_dir}")
        return languages
    for path in sorted(langs_dir.glob("*.json")):
        try:
            raw = path.read_bytes()
            if raw[:3] == b"\xef\xbb\xbf":
                raw = raw[3:]
            data = json.loads(raw.decode("utf-8"))
            code = str(data.get("meta", {}).get("code", path.stem)).strip().lower() or path.stem
            languages[code] = data
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ошибка загрузки {path.stem}: {e}")
    if not languages:
        logger.warning("Не удалось загрузить ни одного языка")
    return languages


LANGUAGES = load_languages()


def get_available_languages() -> list[str]:
    return list(LANGUAGES.keys())


def get_language_display_name(code: str) -> str:
    data = LANGUAGES.get(code, {})
    return str(data.get("meta", {}).get("name", code)).strip() or code


def _resolve_key(data: dict[str, Any], key: str) -> Any | None:
    node = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# --- Кэширование языков ---
_LANG_CACHE: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
_LANG_CACHE_MAX_SIZE: int = 100


def translate(language_code: str, key: str, **kwargs: Any) -> str:
    lang = (language_code or Config.DEFAULT_LANGUAGE).strip().lower()

    if lang not in _LANG_CACHE:
        if len(_LANG_CACHE) >= _LANG_CACHE_MAX_SIZE:
            _LANG_CACHE.popitem(last=False)
        try:
            path = Path(Config.LANGS_DIR) / f"{lang}.json" if Config.LANGS_DIR else None
            if path and path.exists():
                raw = path.read_bytes()
                if raw[:3] == b"\xef\xbb\xbf":
                    raw = raw[3:]
                _LANG_CACHE[lang] = json.loads(raw.decode("utf-8"))
            else:
                _LANG_CACHE[lang] = {}
        except Exception:  # noqa: BLE001
            _LANG_CACHE[lang] = {}
    else:
        _LANG_CACHE.move_to_end(lang)

    data = _LANG_CACHE.get(lang) or LANGUAGES.get(Config.DEFAULT_LANGUAGE, {})
    text = _resolve_key(data, key)
    if text is None and lang != Config.DEFAULT_LANGUAGE:
        data = LANGUAGES.get(Config.DEFAULT_LANGUAGE, {})
        text = _resolve_key(data, key)
    if text is None:
        return key
    if kwargs and isinstance(text, str):
        try:
            escaped_kwargs = {k: html.escape(str(v)) for k, v in kwargs.items()}
            return text.format(**escaped_kwargs)
        except Exception:  # noqa: BLE001
            return text
    return str(text)


# --- Утилиты ---
def is_cancel_text(text: str, lang: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    if normalized == "/cancel":
        return True
    try:
        cancel_label = translate(lang, "buttons.cancel").lower()
    except Exception:  # noqa: BLE001
        cancel_label = "отмена"
    return normalized == cancel_label or normalized in {"отмена", "cancel"}


def format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (ValueError, TypeError):
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return default


def country_code_to_flag(value: Any) -> str:
    code = str(value or "").strip().upper()
    if len(code) != 2 or not code.isalpha() or not code.isascii():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def flag_to_country_code(value: Any) -> str:
    text = str(value or "").strip()
    if len(text) < 2:
        return ""
    regional = [ch for ch in text if 0x1F1E6 <= ord(ch) <= 0x1F1E6 + 25]
    if len(regional) < 2:
        return ""
    return "".join(chr(ord(ch) - 0x1F1E6 + ord("A")) for ch in regional[:2])


def normalize_server_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    flag = flag_to_country_code(text)
    if flag:
        return flag
    return text.upper() if text.isascii() else text


def normalize_servers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        raw = [part.strip() for part in value.replace(";", ",").split(",")]
    elif isinstance(value, list):
        raw = value
    else:
        raw = [value]
    result = []
    seen = set()
    for r in raw:
        code = normalize_server_code(r)
        if code and code not in seen:
            seen.add(code)
            result.append(code)
    return result


def parse_float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).strip())
    except Exception:  # noqa: BLE001
        return default


def format_traffic(traffic_gb: Any, lang: str = Config.DEFAULT_LANGUAGE) -> str:
    try:
        v = float(traffic_gb)
    except Exception:  # noqa: BLE001
        return str(traffic_gb)
    if v >= 1024 and v % 1024 == 0:
        return translate(lang, "texts.traffic_tb", value=int(v / 1024))
    if v.is_integer():
        return translate(lang, "texts.traffic_gb", value=int(v))
    return translate(lang, "texts.traffic_gb", value=v)


def format_duration(days: int, lang: str = Config.DEFAULT_LANGUAGE) -> str:
    return translate(lang, "texts.duration_days", days=days)


def generate_ref_code() -> str:
    return "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))


def build_base_email(user_id: int) -> str:
    return f"user_{user_id}@{Config.VPN_NAME.lower()}.com"


def get_user_panel_email(user_id: int, user: dict[str, Any]) -> str:
    if user.get("is_mate"):
        nickname = user.get("mate_nickname", "")
        sanitized = nickname.lower().replace(" ", "_") if nickname else str(user_id)
        return f"mate_{user_id}_{sanitized}@{Config.VPN_NAME.lower()}.com"
    sub_id = normalize_sub_id(user.get("vpn_url") or user.get("subscription_id") or "")
    if sub_id == "Admin":
        return f"admin@{Config.VPN_NAME.lower()}.com"
    return build_base_email(user_id)


def normalize_sub_id(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    value = value.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    if len(value) < 3:
        logger.warning(f"Подозрительный sub_id: {value[:20]}...")
        return ""
    return value.strip()


def build_subscription_url(sub_id: Any, json_format: bool = False) -> str:
    clean = normalize_sub_id(sub_id)
    if not clean:
        logger.warning("build_subscription_url: пустой sub_id")
        return ""
    base = str(Config.JSON_SUB_PANEL_BASE if json_format else Config.SUB_PANEL_BASE).strip()
    if not base:
        logger.warning("build_subscription_url: базовый URL не настроен")
        return clean
    base = base.rstrip("/")
    return f"{base}/{clean}"


def build_json_subscription_url(sub_id: Any) -> str:
    return build_subscription_url(sub_id, json_format=True)


def get_ref_link(ref_code: str) -> str:
    if BOT_USERNAME:
        return f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    return f"https://t.me/?start={ref_code}"


async def is_admin_user(user_id: int) -> bool:
    return user_id in ADMIN_USER_ID_SET


def parse_stored_servers(value: Any) -> list[str]:
    if isinstance(value, list):
        return normalize_servers(value)
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return normalize_servers(parsed)
    except Exception:  # noqa: BLE001
        return normalize_servers(text)


def get_user_plan_servers(user: dict[str, Any] | None) -> list[str]:
    if not user:
        return []
    stored = parse_stored_servers(user.get("plan_servers"))
    if stored:
        return stored
    plan_text = str(user.get("plan_text") or "").strip()
    base = plan_text.split(" (", 1)[0].strip()
    plan = get_by_name(base) if base else None
    return get_plan_servers(plan)


def format_servers(servers: Any) -> str:
    norm = normalize_servers(servers)
    if not norm:
        return translate(Config.DEFAULT_LANGUAGE, "texts.all_available")
    labels = []
    for s in norm:
        loc = get_location_by_code(s)
        if loc:
            labels.append(str(loc.get("label") or s))
        else:
            flag = country_code_to_flag(s)
            labels.append(f"{flag} {s}".strip() if flag else s)
    return ", ".join(labels)


def format_server_label(code: Any) -> str:
    norm = normalize_server_code(code)
    if not norm:
        return ""
    loc = get_location_by_code(norm)
    if loc:
        return str(loc.get("label") or norm)
    flag = country_code_to_flag(norm)
    return f"{flag} {norm}".strip() if flag else norm


def get_server_match_tokens(server: Any) -> list[str]:
    norm = normalize_server_code(server)
    if not norm:
        return []
    tokens = []

    def add(t: Any):
        t = str(t or "").strip()
        if t and t not in tokens:
            tokens.append(t)

    add(server)
    add(norm)
    add(country_code_to_flag(norm))
    loc = get_location_by_code(norm)
    if loc:
        add(loc.get("flag"))
        for token in loc.get("match_tokens") or []:
            add(token)
    return tokens


def token_matches_inbound_label(label: str, token: Any) -> bool:
    value = str(token or "").strip()
    if not value:
        return False

    norm_value = normalize_server_code(value)
    norm_label = normalize_server_code(label)

    if not norm_value or not norm_label:
        return False

    matched = norm_label.upper().startswith(norm_value.upper())
    return matched


def _filter_inbounds_for_servers_list(
    inbounds: list[dict[str, Any]], servers: list[str]
) -> list[dict[str, Any]]:
    if not servers:
        return [dict(i) for i in inbounds if isinstance(i, dict)]
    result: list[dict[str, Any]] = []
    for inb in inbounds:
        if not isinstance(inb, dict):
            continue
        if not bool(inb.get("enable", True)):
            continue
        remark = str(inb.get("remark") or "").strip()
        tag = str(inb.get("tag") or "").strip()
        if not remark and not tag:
            continue
        for server in servers:
            loc = get_location_by_code(server)
            if not loc:
                continue
            label = str(loc.get("label") or "").strip()
            if not label:
                continue
            if remark.upper().startswith(label.upper()) or tag.upper().startswith(label.upper()):
                result.append(inb)
                break
    return result


def format_payment_time(timestamp: Any) -> str:
    raw = str(timestamp or "")
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(raw).strftime("%d.%m.%Y %H:%M")
    except Exception:  # noqa: BLE001
        return raw


def is_expiring_soon(state: dict[str, Any], days: int | None = None) -> bool:
    days = days if days is not None else Config.EXPIRY_ALERT_DAYS
    max_expiry = to_int(state.get("max_expiry"), 0)
    if max_expiry <= 0:
        return False
    return 0 < (max_expiry - int(time.time() * 1000)) <= days * SECONDS_IN_DAY * 1000


def kb(rows: list[list[dict[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(**btn) for btn in row] for row in rows]
    )


# --- Тарифы ---
class TariffCatalog:
    def __init__(self, path: str):
        self.path = path
        self._active: list[dict[str, Any]] = []
        self._by_id: dict[str, dict[str, Any]] = {}
        self._by_name: dict[str, dict[str, Any]] = {}
        self._locations: list[dict[str, Any]] = []
        self._locations_by_code: dict[str, dict[str, Any]] = {}

    def get_all_active(self) -> list[dict[str, Any]]:
        return self._active

    def get_all_location_codes(self) -> list[str]:
        return [loc.get("code", "") for loc in self._locations if loc.get("code")]

    def get_by_id(self, plan_id: str) -> dict[str, Any] | None:
        return self._by_id.get(plan_id)

    def get_by_name(self, plan_name: str) -> dict[str, Any] | None:
        return self._by_name.get(plan_name)

    def get_location_by_code(self, code: str) -> dict[str, Any] | None:
        loc = self._locations_by_code.get(normalize_server_code(code))
        return dict(loc) if loc else None

    def get_locations(self) -> list[dict[str, Any]]:
        return [dict(loc) for loc in self._locations]

    def get_minimal_by_price(self) -> dict[str, Any] | None:
        eligible = [p for p in self._active if not self.is_trial(p)]
        if not eligible:
            return None
        return min(
            eligible,
            key=lambda p: (
                p.get("price_rub", 0),
                p.get("traffic_gb", 0),
                p.get("ip_limit", 0),
            ),
        )

    @staticmethod
    def is_trial(plan: dict[str, Any] | None) -> bool:
        if not plan:
            return False
        return plan.get("id") == "trial" or plan.get("price_rub", 0) == 0

    def load(self) -> None:
        if not os.path.exists(self.path):
            logger.error(f"Файл тарифов не найден: {self.path}")
            raise FileNotFoundError(f"Файл тарифов не найден: {self.path}")
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка парсинга тарифов: {e}")
            raise ValueError("Некорректный формат файла тарифов") from e
        except Exception as e:
            logger.error(f"Ошибка загрузки тарифов: {e}")
            raise

        raw_locations = data.get("locations") or []
        locations = []
        locations_by_code = {}
        for i, raw in enumerate(raw_locations):
            if not isinstance(raw, dict):
                continue
            try:
                code = normalize_server_code(
                    raw.get("code") or raw.get("id") or raw.get("flag") or raw.get("name")
                )
                if not code:
                    continue
                flag = str(raw.get("flag") or country_code_to_flag(code)).strip()
                name = str(raw.get("name") or raw.get("title") or code)
                label = str(raw.get("label") or "").strip()
                if not label:
                    label = f"{flag} {code}".strip() if flag else code
                price = parse_float_value(
                    raw.get("price_per_day_rub"),
                    Config.CUSTOM_TARIFF_LOCATION_DAY_PRICE,
                )
                aliases = raw.get("aliases") or []
                if not isinstance(aliases, list):
                    aliases = [aliases]
                match = raw.get("match") or []
                if not isinstance(match, list):
                    match = [match]
                match_tokens = normalize_servers([code, flag] + aliases + match)
                loc = {
                    "code": code,
                    "flag": flag,
                    "name": name,
                    "label": label,
                    "price_per_day_rub": max(0.0, price),
                    "match_tokens": match_tokens,
                }
                locations_by_code[code] = loc
                locations.append(loc)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка обработки локации {i}: {e}")

        plans = data.get("plans") or []
        normalized = []
        for raw in plans:
            if not isinstance(raw, dict):
                continue
            try:
                plan = dict(raw)
                plan["servers"] = normalize_servers(
                    plan.get("servers") if "servers" in plan else plan.get("description")
                )
                plan.setdefault("active", True)
                normalized.append(plan)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка обработки плана: {e}")

        self._locations = locations
        self._locations_by_code = locations_by_code
        self._active = [p for p in normalized if p.get("active", True)]
        self._active.sort(key=lambda p: (p.get("sort", 9999), p.get("price_rub", 0)))
        self._by_id = {p.get("id"): p for p in normalized if p.get("id")}
        self._by_name = {p.get("name"): p for p in normalized if p.get("name")}


tariff_catalog = TariffCatalog(Config.TARIFFS_PATH)


def load_tariffs() -> None:
    tariff_catalog.load()


def get_all_active() -> list[dict[str, Any]]:
    return tariff_catalog.get_all_active()


def get_by_id(plan_id: str) -> dict[str, Any] | None:
    return tariff_catalog.get_by_id(plan_id)


def get_by_name(plan_name: str) -> dict[str, Any] | None:
    return tariff_catalog.get_by_name(plan_name)


def is_trial_plan(plan: dict[str, Any] | None) -> bool:
    return tariff_catalog.is_trial(plan)


def get_minimal_by_price() -> dict[str, Any] | None:
    return tariff_catalog.get_minimal_by_price()


def get_custom_locations() -> list[dict[str, Any]]:
    return tariff_catalog.get_locations()


def get_location_by_code(code: str) -> dict[str, Any] | None:
    return tariff_catalog.get_location_by_code(code)


def get_all_location_codes() -> list[str]:
    return tariff_catalog.get_all_location_codes()


def get_plan_servers(plan: dict[str, Any] | None) -> list[str]:
    if not plan:
        return []
    return normalize_servers(plan.get("servers"))


def get_location_price_per_day(code: str) -> float:
    loc = get_location_by_code(code)
    if not loc:
        return Config.CUSTOM_TARIFF_LOCATION_DAY_PRICE
    return max(0.0, parse_float_value(loc.get("price_per_day_rub"), 0.0))


def get_purchasable_catalog_plan(plan_id: str) -> tuple[dict[str, Any] | None, str]:
    plan = get_by_id(plan_id)
    if not plan or not plan.get("active", True):
        return None, translate(Config.DEFAULT_LANGUAGE, "texts.plan_not_found")
    if is_trial_plan(plan):
        return None, translate(Config.DEFAULT_LANGUAGE, "texts.trial_note")
    return plan, ""


# --- Кастомный тариф ---
def custom_days_bounds() -> tuple[int, int]:
    mn = max(1, min(Config.CUSTOM_TARIFF_MIN_DAYS, Config.CUSTOM_TARIFF_MAX_DAYS))
    mx = max(1, max(Config.CUSTOM_TARIFF_MIN_DAYS, Config.CUSTOM_TARIFF_MAX_DAYS))
    return mn, mx


def custom_gb_bounds() -> tuple[int, int]:
    mn = max(1, min(Config.CUSTOM_TARIFF_MIN_GB, Config.CUSTOM_TARIFF_MAX_GB))
    mx = max(1, max(Config.CUSTOM_TARIFF_MIN_GB, Config.CUSTOM_TARIFF_MAX_GB))
    return mn, mx


def custom_ip_bounds() -> tuple[int, int]:
    mn = max(1, min(Config.CUSTOM_TARIFF_MIN_IP, Config.CUSTOM_TARIFF_MAX_IP))
    mx = max(1, max(Config.CUSTOM_TARIFF_MIN_IP, Config.CUSTOM_TARIFF_MAX_IP))
    return mn, mx


def custom_tariff_enabled() -> bool:
    return bool(Config.CUSTOM_TARIFF_ENABLED)


def is_valid_custom_limits(traffic_gb: int, ip_limit: int, duration_days: int) -> bool:
    min_gb, max_gb = custom_gb_bounds()
    min_ip, max_ip = custom_ip_bounds()
    min_days, max_days = custom_days_bounds()
    return (
        min_gb <= traffic_gb <= max_gb
        and min_ip <= ip_limit <= max_ip
        and min_days <= duration_days <= max_days
    )


def is_valid_custom_servers(servers: Any) -> bool:
    selected = normalize_servers(servers)
    if not selected:
        return False
    available = {loc.get("code") for loc in get_custom_locations()}
    return all(s in available for s in selected)


def calculate_custom_tariff_total(
    traffic_gb: int,
    ip_limit: int,
    duration_days: int,
    servers: list[str] | None = None,
) -> float:
    loc_total = sum(get_location_price_per_day(s) for s in normalize_servers(servers))
    return (
        Config.CUSTOM_TARIFF_BASE_PRICE
        + traffic_gb * Config.CUSTOM_TARIFF_GB_COEF
        + ip_limit * duration_days * Config.CUSTOM_TARIFF_IP_DAY_COEF
        + loc_total * duration_days
    )


def build_custom_plan_name(
    traffic_gb: int,
    ip_limit: int,
    duration_days: int,
    servers: list[str] | None = None,
) -> str:
    return translate(
        Config.DEFAULT_LANGUAGE,
        "texts.custom_plan_name",
        traffic_gb=traffic_gb,
        ip_limit=ip_limit,
        days=duration_days,
        servers_text=format_servers(servers),
    )


def build_custom_plan(
    traffic_gb: int,
    ip_limit: int,
    duration_days: int,
    *,
    servers: list[str] | None = None,
    plan_name: str | None = None,
) -> dict[str, Any]:
    selected = normalize_servers(servers)
    base = int(  # noqa: RUF046
        round(calculate_custom_tariff_total(traffic_gb, ip_limit, duration_days, selected))
    )
    return {
        "id": "custom",
        "name": plan_name or build_custom_plan_name(traffic_gb, ip_limit, duration_days, selected),
        "price_rub": base,
        "ip_limit": ip_limit,
        "traffic_gb": traffic_gb,
        "duration_days": duration_days,
        "servers": selected,
        "active": True,
    }


def build_custom_tariff_info_block(lang: str = Config.DEFAULT_LANGUAGE) -> str:
    min_gb, max_gb = custom_gb_bounds()
    min_ip, max_ip = custom_ip_bounds()
    min_days, max_days = custom_days_bounds()
    base = format_number(Config.CUSTOM_TARIFF_BASE_PRICE)
    gb_coef = format_number(Config.CUSTOM_TARIFF_GB_COEF)
    ip_day_coef = format_number(Config.CUSTOM_TARIFF_IP_DAY_COEF)
    locations = get_custom_locations()
    if locations:
        loc_lines = "\n".join(
            translate(
                lang,
                "texts.custom_tariff_location_line",
                label=loc.get("label"),
                price=format_number(parse_float_value(loc.get("price_per_day_rub"), 0.0)),
            )
            for loc in locations
        )
    else:
        loc_lines = translate(lang, "texts.custom_tariff_no_locations")
    return (
        translate(lang, "texts.custom_tariff_info_title")
        + translate(
            lang,
            "texts.custom_tariff_info_formula",
            base=base,
            gb_coef=gb_coef,
            ip_day_coef=ip_day_coef,
        )
        + translate(lang, "texts.custom_tariff_info_params")
        + translate(
            lang,
            "texts.custom_tariff_info_gb",
            min_gb=min_gb,
            max_gb=max_gb,
        )
        + translate(
            lang,
            "texts.custom_tariff_info_ip",
            min_ip=min_ip,
            max_ip=max_ip,
        )
        + translate(
            lang,
            "texts.custom_tariff_info_days",
            min_days=min_days,
            max_days=max_days,
        )
        + translate(
            lang,
            "texts.custom_tariff_info_locations",
            location_lines=loc_lines,
        )
    )


def build_custom_plan_from_payment(
    payment: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    custom = payment.get("custom_plan")
    if not isinstance(custom, dict):
        return None, translate(Config.DEFAULT_LANGUAGE, "texts.custom_plan_invalid_params")
    traffic = to_int(custom.get("traffic_gb"), 0)
    ip = to_int(custom.get("ip_limit"), 0)
    days = to_int(custom.get("duration_days"), 0)
    servers = normalize_servers(custom.get("servers"))
    if not is_valid_custom_limits(traffic, ip, days):
        return None, translate(Config.DEFAULT_LANGUAGE, "texts.custom_plan_limits_out_of_range")
    if not is_valid_custom_servers(servers):
        return None, translate(Config.DEFAULT_LANGUAGE, "texts.custom_plan_invalid_locations")
    plan_name = str(custom.get("plan_name") or "").strip()
    return (
        build_custom_plan(traffic, ip, days, servers=servers, plan_name=plan_name or None),
        "",
    )


# --- Очки доверия ---
TRUST_SCORE_MIN = Config.TRUST_SCORE_MIN
TRUST_SCORE_MAX = Config.TRUST_SCORE_MAX
TRUST_SCORE_EARN_PERCENT = Config.TRUST_SCORE_EARN_PERCENT
TRUST_SCORE_MAX_DISCOUNT_PERCENT = Config.TRUST_SCORE_MAX_DISCOUNT_PERCENT
TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED = Config.TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED
TRUST_SCORE_PENALTY_PAYMENT_REJECTED = Config.TRUST_SCORE_PENALTY_PAYMENT_REJECTED


def calculate_discount_percent(trust_score: int) -> int:
    if trust_score <= 0:
        return 0
    return min(
        TRUST_SCORE_MAX_DISCOUNT_PERCENT,
        (trust_score * TRUST_SCORE_MAX_DISCOUNT_PERCENT) // TRUST_SCORE_MAX,
    )


def apply_trust_discount(price: float, trust_score: int) -> tuple[float, int]:
    if trust_score <= 0:
        return price, 0
    disc = calculate_discount_percent(trust_score)
    return price - (price * disc / 100.0), disc


async def apply_trust_score_delta(user_id: int, delta: int) -> tuple[bool, int, int, int]:
    user = await db.get_user_by_any_id(user_id)
    if not user:
        return False, 0, 0, 0
    tg_id = to_int(user.get("telegram_id"), user_id)
    async with db.lock:
        before = await db._get_trust_score_raw(tg_id)
        if delta == 0:
            return True, before, before, 0
        new_score = max(TRUST_SCORE_MIN, min(TRUST_SCORE_MAX, before + delta))
        updated = await db._set_trust_score_raw(tg_id, new_score)
        if not updated:
            return False, before, before, 0
        return True, before, new_score, new_score - before


def build_trust_change_line(delta: int, before: int, after: int) -> str:
    if delta > 0:
        return translate(
            Config.DEFAULT_LANGUAGE,
            "texts.trust_change_positive",
            delta=delta,
            before=before,
            after=after,
        )
    if delta < 0:
        return translate(
            Config.DEFAULT_LANGUAGE,
            "texts.trust_change_negative",
            delta=delta,
            before=before,
            after=after,
        )
    return translate(Config.DEFAULT_LANGUAGE, "texts.trust_change_none", after=after)


# --- База данных SQLite ---
class Database:
    USER_COLUMN_DEFS: ClassVar[dict[str, str]] = {
        "join_date": "TIMESTAMP",
        "banned": "BOOLEAN",
        "ban_reason": "TEXT",
        "ref_code": "TEXT",
        "ref_by": "INTEGER",
        "ref_rewarded": "INTEGER",
        "bonus_days_pending": "INTEGER",
        "trial_used": "INTEGER",
        "has_subscription": "INTEGER",
        "plan_text": "TEXT",
        "plan_servers": "TEXT",
        "subscription_id": "TEXT",
        "ip_limit": "INTEGER",
        "traffic_gb": "INTEGER",
        "vpn_url": "TEXT",
        "trust_score": "INTEGER",
        "language": "TEXT",
        "expiry_alert_sent": "INTEGER",
        "cleanup_notification_sent": "INTEGER",
        "expiry_sub_datatime": "TEXT",
        "extra_sub_gb": "INTEGER",
        "is_mate": "INTEGER",
        "mate_nickname": "TEXT",
        "mate_social_links": "TEXT",
        "mate_followers": "INTEGER",
        "mate_avg_reach": "INTEGER",
        "mate_period_months": "INTEGER",
        "mate_bonus_type": "TEXT",
        "mate_bonus_value": "INTEGER",
        "mate_ref_link_code": "TEXT",
        "mate_subscription_id": "TEXT",
        "mate_expiry": "TEXT",
        "mate_balance": "REAL",
        "mate_commission_total": "REAL",
        "mate_withdrawal_requests": "TEXT",
        "mate_status": "TEXT",
        "telegram_id": "INTEGER DEFAULT 0",
        "web_id": "INTEGER DEFAULT 0",
        "web_registered_at": "TEXT DEFAULT ''",
        "web_last_login": "TEXT DEFAULT ''",
        "web_auth_method": "TEXT DEFAULT ''",
        "session_token": "TEXT DEFAULT ''",
        "session_expires_at": "TEXT DEFAULT ''",
        "session_created_at": "TEXT DEFAULT ''",
        "session_version": "INTEGER DEFAULT 0",
        "password_hash": "TEXT DEFAULT ''",
        "username": "TEXT DEFAULT ''",
        "discount_percent": "INTEGER DEFAULT 0",
        "abuse_status": "TEXT DEFAULT ''",
        "daily_traffic_date": "TEXT DEFAULT ''",
        "daily_traffic_gb": "REAL DEFAULT 0.0",
        "total_traffic_gb": "REAL DEFAULT 0.0",
    }

    DEPRECATED_USER_COLUMNS: ClassVar[set[str]] = {
        "email",
        "username_updated_at",
        "web_linked_tg",
    }

    def __init__(self, db_path: str):
        self.db_path: str = db_path
        self.conn: aiosqlite.Connection | None = None
        self.lock: asyncio.Lock = asyncio.Lock()
        self._init_in_progress: bool = False
        self._db_initialized: bool = False

    async def connect(self) -> None:
        try:
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)
                try:
                    os.chmod(parent, 0o755)
                except (PermissionError, OSError):
                    pass

            async def _connect() -> aiosqlite.Connection:
                conn = await asyncio.wait_for(
                    aiosqlite.connect(self.db_path, timeout=Config.SQLITE_TIMEOUT_SEC),
                    timeout=10.0,
                )
                return conn

            try:
                self.conn = await retry_async(
                    _connect,
                    max_retries=3,
                    delay=1.0,
                    exceptions=(aiosqlite.Error, asyncio.TimeoutError),
                )
                logger.info("Подключение к БД создано")
            except (asyncio.TimeoutError, aiosqlite.Error):
                logger.warning(
                    f"Не удалось открыть БД по пути {self.db_path}, пробуем временный каталог"
                )
                fallback_dir = os.path.join("/tmp", os.getenv("VPN_NAME", "vpn"))
                os.makedirs(fallback_dir, exist_ok=True)
                fallback_path = os.path.join(fallback_dir, "users.db")
                self.db_path = fallback_path
                self.conn = await retry_async(
                    _connect,
                    max_retries=3,
                    delay=1.0,
                    exceptions=(aiosqlite.Error, asyncio.TimeoutError),
                )
                logger.warning(f"Используется временная БД: {self.db_path}")
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA foreign_keys = ON")
            logger.info("PRAGMA foreign_keys = ON")
            await self.conn.execute("PRAGMA journal_mode = WAL")
            logger.info("PRAGMA journal_mode = WAL")
            await self.conn.execute("PRAGMA busy_timeout = 5000")
            await self.conn.execute("PRAGMA cache_size = -256000")
            await self.init_db()
            logger.info(f"База данных подключена: {self.db_path}")
        except Exception as e:
            logger.critical(f"Не удалось подключиться к базе данных: {e}")
            raise DatabaseError(f"Ошибка подключения к БД: {e}") from e

    async def close(self) -> None:
        if self.conn:
            try:
                await self.conn.close()
                logger.info("База данных закрыта")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Ошибка закрытия БД: {e}")
            finally:
                self.conn = None

    async def init_db(self) -> None:
        if not self.conn or self._db_initialized:
            if self._db_initialized:
                logger.info("init_db: база уже инициализирована, пропуск")
            return
        logger.info("init_db: начало инициализации")
        async with self.lock:
            if self._db_initialized:
                return
            logger.info("init_db: lock захвачен")
            self._init_in_progress = True
            try:
                logger.info("init_db: выполняется CREATE TABLE")
                await self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        telegram_id INTEGER DEFAULT 0,
                        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        banned BOOLEAN DEFAULT FALSE,
                        ban_reason TEXT DEFAULT '',
                        ref_code TEXT,
                        ref_by INTEGER,
                        ref_rewarded INTEGER DEFAULT 0,
                        bonus_days_pending INTEGER DEFAULT 0,
                        trial_used INTEGER DEFAULT 0,
                        has_subscription INTEGER DEFAULT 0,
                        plan_text TEXT DEFAULT '',
                        plan_servers TEXT DEFAULT '',
                        subscription_id TEXT DEFAULT '',
                        ip_limit INTEGER DEFAULT 0,
                        traffic_gb INTEGER DEFAULT 0,
                        vpn_url TEXT DEFAULT '',
                        trust_score INTEGER DEFAULT 0,
                        language TEXT DEFAULT '',
                        expiry_alert_sent INTEGER DEFAULT 0,
                        cleanup_notification_sent INTEGER DEFAULT 0,
                        expiry_sub_datatime TEXT DEFAULT '',
                        extra_sub_gb INTEGER DEFAULT 0,
                        is_mate INTEGER DEFAULT 0,
                        mate_nickname TEXT DEFAULT '',
                        mate_social_links TEXT DEFAULT '',
                        mate_followers INTEGER DEFAULT 0,
                        mate_avg_reach INTEGER DEFAULT 0,
                        mate_period_months INTEGER DEFAULT 0,
                        mate_bonus_type TEXT DEFAULT '',
                        mate_bonus_value INTEGER DEFAULT 0,
                        mate_ref_link_code TEXT DEFAULT '',
                        mate_subscription_id TEXT DEFAULT '',
                        mate_expiry TEXT DEFAULT '',
                        mate_balance REAL DEFAULT 0.0,
                        mate_commission_total REAL DEFAULT 0.0,
                        mate_withdrawal_requests TEXT DEFAULT '[]',
                        mate_status TEXT DEFAULT '',
                        web_id INTEGER DEFAULT 0,
                        web_registered_at TEXT DEFAULT '',
                        web_last_login TEXT DEFAULT '',
                        web_auth_method TEXT DEFAULT '',
                        session_token TEXT DEFAULT '',
                        session_expires_at TEXT DEFAULT '',
                        session_created_at TEXT DEFAULT '',
                        session_version INTEGER DEFAULT 0,
                        password_hash TEXT DEFAULT '',
                        username TEXT DEFAULT '',
                        discount_percent INTEGER DEFAULT 0,
                        abuse_status TEXT DEFAULT '',
                        daily_traffic_date TEXT DEFAULT '',
                        daily_traffic_gb REAL DEFAULT 0.0,
                        total_traffic_gb REAL DEFAULT 0.0
                    )
                """)
                logger.info("init_db: CREATE TABLE выполнен, запуск _migrate_users_table")
                await self._migrate_users_table()
                logger.info("init_db: _migrate_users_table выполнен")
                await self._migrate_json_user_ids()
                try:
                    await self.conn.execute("""
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_ref_code
                        ON users(ref_code)
                        WHERE ref_code IS NOT NULL AND ref_code != ''
                        """)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Не удалось создать индекс ref_code: {e}")
                await self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_ref_by ON users(ref_by)"
                )
                await self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_vpn_url ON users(vpn_url)"
                )
                await self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_is_mate ON users(is_mate)"
                )
                await self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_session_token ON users(session_token)"
                )
                await self.conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_id "
                    "ON users(telegram_id) WHERE telegram_id != 0"
                )
                await self.conn.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_web_id "
                    "ON users(web_id) WHERE web_id != 0"
                )
                logger.info("init_db: индексы созданы, запуск _cleanup_duplicate_users")
                await self._cleanup_duplicate_users()
                await self.conn.commit()
                self._init_in_progress = False
                self._db_initialized = True
                logger.info("Таблица users создана/проверена")
            except Exception as e:
                self._init_in_progress = False
                logger.error(f"Ошибка инициализации БД: {e}")
                raise DatabaseError(f"Ошибка init_db: {e}") from e

    async def _migrate_users_table(self) -> None:
        if not self.conn:
            return
        logger.info("init_db._migrate_users_table: начало")
        cur = await self.conn.execute("PRAGMA table_info(users)")
        rows = await cur.fetchall()
        existing = {str(row[1]) for row in rows}
        for column, definition in self.USER_COLUMN_DEFS.items():
            if column in existing:
                continue
            await self.conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
            logger.info(f"Добавлена колонка users.{column}")

        for column in self.DEPRECATED_USER_COLUMNS:
            if column not in existing:
                continue
            try:
                await self.conn.execute(f"ALTER TABLE users DROP COLUMN {column}")
                logger.info(f"Удалена устаревшая колонка users.{column}")
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    f"Не удалось удалить users.{column}: {e}. "
                    f"Удалите вручную после резервной копии."
                )

        if "telegram_id" not in existing:
            await self.conn.execute("ALTER TABLE users ADD COLUMN telegram_id INTEGER DEFAULT 0")
            await self.conn.execute("UPDATE users SET telegram_id = user_id WHERE telegram_id = 0")
            await self.conn.commit()
            logger.info("telegram_id миграция завершена")
        logger.info("init_db._migrate_users_table: конец")

    async def _migrate_json_user_ids(self) -> None:
        for path in (Config.DATA_AWAIT, Config.PARTNER_OPS_FILE):
            if not os.path.exists(path):
                continue
            try:
                import aiofiles

                async with aiofiles.open(path, "r", encoding="utf-8") as f:
                    content = await f.read()
                data = json.loads(content) if content else []
                if not isinstance(data, list):
                    continue
                changed = False
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    uid = to_int(item.get("user_id"), 0)
                    if uid <= 0:
                        continue
                    if item.get("tg_id") and to_int(item.get("tg_id"), 0) == uid:
                        continue
                    tg = await self._resolve_to_tg_id(uid)
                    if tg and tg != uid:
                        item["tg_id"] = tg
                        item["user_id"] = tg
                        changed = True
                if changed:
                    tmp = f"{path}.tmp"
                    async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
                        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
                    os.replace(tmp, path)
                    logger.info(f"Миграция user_id → tg_id завершена в {path}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Миграция {path}: {e}")

    async def _resolve_to_tg_id(self, raw_id: int) -> int:
        if not self.conn or raw_id <= 0:
            return 0
        user = await self.get_user_by_any_id(raw_id)
        if user:
            return to_int(user.get("telegram_id"), raw_id)
        return 0

    async def _cleanup_duplicate_users(self) -> None:
        if not self.conn:
            return
        logger.info("init_db._cleanup_duplicate_users: начало")
        try:
            cur = await self.conn.execute(
                "SELECT telegram_id, COUNT(*) as cnt FROM users "
                "WHERE telegram_id != 0 GROUP BY telegram_id HAVING cnt > 1"
            )
            dup_tg = await cur.fetchall()
            for row in dup_tg:
                tg_id = row[0]
                await self.conn.execute(
                    "DELETE FROM users WHERE telegram_id = ? AND user_id NOT IN "
                    "(SELECT MIN(user_id) FROM users WHERE telegram_id = ?)",
                    (tg_id, tg_id),
                )

            cur = await self.conn.execute(
                "SELECT web_id, COUNT(*) as cnt FROM users "
                "WHERE web_id != 0 GROUP BY web_id HAVING cnt > 1"
            )
            dup_web = await cur.fetchall()
            for row in dup_web:
                web_id = row[0]
                await self.conn.execute(
                    "DELETE FROM users WHERE web_id = ? AND user_id NOT IN "
                    "(SELECT MIN(user_id) FROM users WHERE web_id = ?)",
                    (web_id, web_id),
                )

            await self.conn.commit()
            if dup_tg or dup_web:
                logger.info(f"Очистка дубликатов: telegram_id={len(dup_tg)}, web_id={len(dup_web)}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"_cleanup_duplicate_users: {e}")
        logger.info("init_db._cleanup_duplicate_users: конец")

    @log_error
    async def add_user(self, telegram_id: int, *, force: bool = False) -> bool:
        if not force and await is_admin_user(telegram_id):
            return False
        if not self.conn:
            return False

        try:
            existing = await self.get_user_by_telegram_id(telegram_id)
            if existing:
                return True
            async with self.lock:
                await self.conn.execute(
                    "INSERT OR IGNORE INTO users (telegram_id) VALUES (?)",
                    (telegram_id,),
                )
                await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"add_user {telegram_id}: {e}")
            return False

    @log_error
    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        if not self.conn:
            logger.error(f"get_user {user_id}: соединение с БД отсутствует")
            return None

        try:
            async with self.lock:
                cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                row = await cur.fetchone()
                return dict(row) if row else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user {user_id}: {e}")
            return None

    @log_error
    async def get_user_by_any_id(self, raw_id: int) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            user = await self.get_user_by_id(raw_id)
            if user:
                return user
            user = await self.get_user_by_telegram_id(raw_id)
            if user:
                return user
            if await self.add_user(raw_id):
                return await self.get_user_by_telegram_id(raw_id)
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_by_any_id {raw_id}: {e}")
            return None

    @log_error
    async def get_user_by_id(self, user_id: int) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            return dict(row) if row else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_by_id {user_id}: {e}")
            return None

    @log_error
    async def get_user_by_ref_code(self, ref_code: str) -> dict[str, Any] | None:
        if not self.conn:
            return None

        try:
            cur = await self.conn.execute("SELECT * FROM users WHERE ref_code = ?", (ref_code,))
            row = await cur.fetchone()
            return dict(row) if row else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_by_ref_code {ref_code}: {e}")
            return None

    @log_error
    async def get_user_by_telegram_id(self, telegram_id: int) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            if self._init_in_progress:
                cur = await self.conn.execute(
                    "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
                )
                row = await cur.fetchone()
                return dict(row) if row else None
            async with self.lock:
                cur = await self.conn.execute(
                    "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
                )
                row = await cur.fetchone()
                return dict(row) if row else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_by_telegram_id {telegram_id}: {e}")
            return None

    @log_error
    async def get_users_by_ids(self, user_ids: list[int]) -> list[dict[str, Any]]:
        if not self.conn or not user_ids:
            return []
        try:
            placeholders = ",".join("?" for _ in user_ids)
            async with self.lock:
                cur = await self.conn.execute(
                    f"SELECT * FROM users WHERE user_id IN ({placeholders})",
                    user_ids,
                )
                return [dict(row) for row in await cur.fetchall()]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_users_by_ids: {e}")
            return []

    @log_error
    async def get_users_by_telegram_ids(self, telegram_ids: list[int]) -> list[dict[str, Any]]:
        if not self.conn or not telegram_ids:
            return []
        try:
            placeholders = ",".join("?" for _ in telegram_ids)
            async with self.lock:
                cur = await self.conn.execute(
                    f"SELECT * FROM users WHERE telegram_id IN ({placeholders})",
                    telegram_ids,
                )
                return [dict(row) for row in await cur.fetchall()]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_users_by_telegram_ids: {e}")
            return []

    @log_error
    async def get_users_with_abuse(self) -> list[dict[str, Any]]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute(
                "SELECT * FROM users WHERE abuse_status IS NOT NULL AND abuse_status != ''"
            )
            return [dict(row) for row in await cur.fetchall()]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_users_with_abuse: {e}")
            return []

    @log_error
    async def count_referrals_batch(self, user_ids: list[int]) -> dict[int, int]:
        if not self.conn or not user_ids:
            return {}
        try:
            placeholders = ",".join("?" for _ in user_ids)
            cur = await self.conn.execute(
                f"SELECT ref_by, COUNT(*) FROM users WHERE ref_by IN ({placeholders}) GROUP BY ref_by",
                user_ids,
            )
            return {row[0]: row[1] for row in await cur.fetchall()}
        except Exception as e:  # noqa: BLE001
            logger.error(f"count_referrals_batch: {e}")
            return {}

    @log_error
    async def count_referrals_paid_batch(self, user_ids: list[int]) -> dict[int, int]:
        if not self.conn or not user_ids:
            return {}
        try:
            placeholders = ",".join("?" for _ in user_ids)
            cur = await self.conn.execute(
                f"""SELECT ref_by, COUNT(*) FROM users WHERE ref_by IN ({placeholders}) AND (ref_rewarded = 1 OR has_subscription = 1) GROUP BY ref_by""",
                user_ids,
            )
            return {row[0]: row[1] for row in await cur.fetchall()}
        except Exception as e:  # noqa: BLE001
            logger.error(f"count_referrals_paid_batch: {e}")
            return {}

    @log_error
    async def update_user(self, user_id: int, *, force: bool = False, **kwargs) -> bool:
        if not self.conn or not kwargs:
            return False
        if not force:
            user = await self.get_user_by_id(user_id)
            if user and await is_admin_user(to_int(user.get("telegram_id"), 0)):
                logger.warning(f"Попытка обновления пользователя-админа {user_id}")
                return False
        if not validate_user_id(user_id):
            logger.warning(f"Некорректный user_id для обновления: {user_id}")
            return False

        allowed = set(self.USER_COLUMN_DEFS.keys())
        values_by_column = {k: v for k, v in kwargs.items() if k in allowed}
        invalid = sorted(set(kwargs) - allowed - {"force"})
        if invalid:
            logger.warning(f"Игнорируются неизвестные поля users: {', '.join(invalid)}")
        if not values_by_column:
            return False

        set_clause: str = ", ".join(f"{k} = ?" for k in values_by_column)
        values: list[Any] = list(values_by_column.values()) + [user_id]

        try:
            async with self.lock:
                await self.conn.execute(
                    f"UPDATE users SET {set_clause} WHERE user_id = ?",
                    values,
                )
                await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"update_user {user_id}: {e}")
            return False

    @log_error
    async def update_user_by_telegram_id(
        self, telegram_id: int, *, force: bool = False, **kwargs
    ) -> bool:
        if not self.conn or not kwargs:
            return False
        if not force and await is_admin_user(telegram_id):
            logger.warning(f"Попытка обновления пользователя-админа {telegram_id}")
            return False
        if not validate_user_id(telegram_id):
            logger.warning(f"Некорректный telegram_id для обновления: {telegram_id}")
            return False

        allowed = set(self.USER_COLUMN_DEFS.keys())
        values_by_column = {k: v for k, v in kwargs.items() if k in allowed}
        invalid = sorted(set(kwargs) - allowed - {"force"})
        if invalid:
            logger.warning(f"Игнорируются неизвестные поля users: {', '.join(invalid)}")
        if not values_by_column:
            return False

        set_clause: str = ", ".join(f"{k} = ?" for k in values_by_column)
        values: list[Any] = list(values_by_column.values()) + [telegram_id]

        try:
            async with self.lock:
                await self.conn.execute(
                    f"UPDATE users SET {set_clause} WHERE telegram_id = ?",
                    values,
                )
                await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"update_user_by_telegram_id {telegram_id}: {e}")
            return False

    @log_error
    async def delete_user(self, user_id: int) -> bool:
        if not self.conn or user_id <= 0:
            return False
        try:
            async with self.lock:
                await self.conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"delete_user {user_id}: {e}")
            return False

    @log_error
    async def get_total_users(self) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE (web_id IS NOT NULL AND web_id != 0) OR (telegram_id IS NOT NULL AND telegram_id != 0)"
            )
            row = await cur.fetchone()
            return row[0] if row else 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_total_users: {e}")
            return 0

    @log_error
    async def get_banned_users_count(self) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE banned = 1 AND ((web_id IS NOT NULL AND web_id != 0) OR (telegram_id IS NOT NULL AND telegram_id != 0))"
            )
            row = await cur.fetchone()
            return row[0] if row else 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_banned_users_count: {e}")
            return 0

    @log_error
    async def get_banned_user_ids(self) -> list[int]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute(
                "SELECT telegram_id FROM users WHERE banned = 1 AND telegram_id != 0"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_banned_user_ids: {e}")
            return []

    @log_error
    async def get_subscribed_user_ids(self) -> list[int]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute(
                "SELECT telegram_id FROM users WHERE has_subscription = 1 AND telegram_id != 0"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_subscribed_user_ids: {e}")
            return []

    @log_error
    async def get_all_non_banned_user_ids(self) -> list[int]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute(
                "SELECT telegram_id FROM users WHERE banned = 0 AND telegram_id != 0"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_all_non_banned_user_ids: {e}")
            return []

    @log_error
    async def get_all_users(self) -> list[dict[str, Any]]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute("SELECT * FROM users ORDER BY user_id")
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_all_users: {e}")
            return []

    @log_error
    async def ban_user(self, user_id: int, reason: str = "") -> bool:
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.ban_user_by_uid(internal_uid, reason=reason)

    @log_error
    async def ban_user_by_uid(self, internal_uid: int, reason: str = "") -> bool:
        user = await self.get_user_by_id(internal_uid)
        if not user:
            return False
        if await is_admin_user(to_int(user.get("telegram_id"), 0)):
            return False
        return await self.update_user(internal_uid, banned=True, ban_reason=reason, trust_score=0)

    @log_error
    async def unban_user(self, user_id: int) -> bool:
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.unban_user_by_uid(internal_uid)

    @log_error
    async def unban_user_by_uid(self, internal_uid: int) -> bool:
        user = await self.get_user_by_id(internal_uid)
        if not user:
            return False
        if await is_admin_user(to_int(user.get("telegram_id"), 0)):
            return False
        return await self.update_user(internal_uid, banned=False, ban_reason="")

    @log_error
    async def set_subscription(
        self,
        user_id: int,
        plan_text: str,
        ip_limit: int,
        vpn_url: str,
        traffic_gb: int,
        plan_servers: list[str] | None = None,
        subscription_id: str | None = None,
        expiry_sub_datatime: str = "",
    ) -> bool:
        user = await self.get_user_by_any_id(user_id)
        if not user:
            logger.error(f"set_subscription: пользователь не найден user_id={user_id}")
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(
            internal_uid,
            force=True,
            plan_text=plan_text,
            plan_servers=(
                json.dumps(normalize_servers(plan_servers), ensure_ascii=False)
                if plan_servers
                else ""
            ),
            subscription_id=subscription_id or "",
            ip_limit=ip_limit,
            vpn_url=vpn_url,
            traffic_gb=traffic_gb,
            expiry_alert_sent=0,
            cleanup_notification_sent=0,
            has_subscription=1,
            expiry_sub_datatime=expiry_sub_datatime,
        )

    @log_error
    async def remove_subscription(self, user_id: int) -> bool:
        return await self.update_user(
            user_id,
            force=True,
            plan_text="",
            plan_servers="",
            subscription_id="",
            ip_limit=0,
            vpn_url="",
            traffic_gb=0,
            expiry_alert_sent=0,
            cleanup_notification_sent=0,
            has_subscription=0,
            expiry_sub_datatime="",
            extra_sub_gb=0,
        )

    @log_error
    async def set_expiry_notification_sent(self, user_id: int, sent: bool) -> bool:
        if await is_admin_user(user_id):
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(internal_uid, expiry_alert_sent=1 if sent else 0)

    @log_error
    async def add_extra_traffic(self, user_id: int, extra_gb: int) -> bool:
        if extra_gb <= 0:
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        current_extra = to_int(user.get("extra_sub_gb"), 0)
        return await self.update_user(
            internal_uid, force=True, extra_sub_gb=current_extra + int(extra_gb)
        )

    @log_error
    async def get_user_language(self, telegram_id: int) -> str:
        if not self.conn:
            return ""
        try:
            user = await self.get_user_by_telegram_id(telegram_id)
            return str(user.get("language", "") if user else "").strip().lower()
        except Exception:  # noqa: BLE001
            return ""

    @log_error
    async def set_user_language(self, user_id: int, language: str, *, force: bool = False) -> bool:
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(internal_uid, force=force, language=language)

    @log_error
    async def get_user_language_by_user_id(self, user_id: int) -> str:
        if not self.conn:
            return ""
        try:
            user = await self.get_user_by_id(user_id)
            return str(user.get("language", "") if user else "").strip().lower()
        except Exception:  # noqa: BLE001
            return ""

    @log_error
    async def set_user_language_by_user_id(self, user_id: int, language: str) -> bool:
        if not self.conn:
            return False
        try:
            user = await self.get_user_by_id(user_id)
            if not user:
                return False
            return await self.update_user(user_id, force=True, language=language)
        except Exception:  # noqa: BLE001
            return False

    @log_error
    async def change_username(self, user_id: int, new_username: str) -> bool:
        if user_id <= 0 or not new_username:
            return False
        try:
            existing = await self.get_user_by_username(new_username)
            if existing and to_int(existing.get("user_id"), 0) != user_id:
                return False
            user = await self.get_user_by_id(user_id)
            if not user:
                return False
            return await self.update_user(user_id, force=True, username=new_username)
        except Exception as e:  # noqa: BLE001
            logger.error(f"change_username error: {e}")
            return False

    @log_error
    async def change_password(self, user_id: int, hashed_password: str) -> bool:
        if user_id <= 0 or not hashed_password:
            return False
        try:
            user = await self.get_user_by_id(user_id)
            if not user:
                return False
            return await self.update_user(user_id, force=True, password_hash=hashed_password)
        except Exception as e:  # noqa: BLE001
            logger.error(f"change_password error: {e}")
            return False

    @log_error
    async def set_ref_by(self, user_id: int, referrer_id: int) -> bool:
        if await is_admin_user(user_id) or await is_admin_user(referrer_id):
            return False
        if user_id <= 0 or referrer_id <= 0 or user_id == referrer_id:
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user or to_int(user.get("ref_by"), 0):
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(internal_uid, ref_by=referrer_id)

    @log_error
    async def set_has_subscription(self, user_id: int) -> bool:
        if await is_admin_user(user_id):
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(internal_uid, has_subscription=1)

    @log_error
    async def mark_trial_used(self, user_id: int) -> bool:
        if await is_admin_user(user_id):
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(internal_uid, trial_used=1, has_subscription=1)

    @log_error
    async def mark_ref_rewarded(self, user_id: int) -> bool:
        if await is_admin_user(user_id):
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(internal_uid, ref_rewarded=1)

    @log_error
    async def count_referrals(self, user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute("SELECT COUNT(*) FROM users WHERE ref_by = ?", (user_id,))
            row = await cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"count_referrals {user_id}: {e}")
            return 0

    @log_error
    async def count_referrals_paid(self, user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE ref_by = ? AND (ref_rewarded = 1 OR has_subscription = 1)
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"count_referrals_paid {user_id}: {e}")
            return 0

    @log_error
    async def get_bonus_days_pending(self, user_id: int) -> int:
        user = await self.get_user_by_any_id(user_id)
        return max(0, to_int(user.get("bonus_days_pending"), 0)) if user else 0

    @log_error
    async def add_bonus_days_pending(self, user_id: int, days: int) -> bool:
        if await is_admin_user(user_id) or days <= 0:
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        current = await self.get_bonus_days_pending(internal_uid)
        return await self.update_user(internal_uid, bonus_days_pending=max(0, current + int(days)))

    @log_error
    async def clear_bonus_days_pending(self, user_id: int) -> bool:
        if await is_admin_user(user_id):
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            return False
        internal_uid = user.get("user_id", user_id)
        return await self.update_user(internal_uid, bonus_days_pending=0)

    @log_error
    async def get_trust_score(self, user_id: int) -> int:
        user = await self.get_user_by_id(user_id)
        if not user:
            user = await self.get_user_by_telegram_id(user_id)
        if not user:
            return 0
        return to_int(user.get("trust_score"), 0)

    @log_error
    async def add_trust_score(self, user_id: int, points: int) -> bool:
        if await is_admin_user(user_id):
            return False
        await self.add_user(user_id)
        current = await self.get_trust_score(user_id)
        new_score = max(TRUST_SCORE_MIN, min(TRUST_SCORE_MAX, current + points))
        return await self.update_user_by_telegram_id(user_id, trust_score=new_score)

    @log_error
    async def _get_trust_score_raw(self, user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute(
                "SELECT trust_score FROM users WHERE telegram_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
            return to_int(row[0] if row else 0, 0)
        except Exception as e:  # noqa: BLE001
            logger.error(f"_get_trust_score_raw {user_id}: {e}")
            return 0

    @log_error
    async def _set_trust_score_raw(self, user_id: int, trust_score: int) -> bool:
        if not self.conn:
            return False
        try:
            await self.conn.execute(
                "UPDATE users SET trust_score = ? WHERE telegram_id = ?",
                (trust_score, user_id),
            )
            await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"_set_trust_score_raw {user_id}: {e}")
            return False

    @log_error
    @log_error
    async def ensure_ref_code(self, user_id: int) -> str | None:
        if await is_admin_user(user_id):
            return None
        user = await self.get_user_by_any_id(user_id)
        if not user:
            await self.add_user(user_id)
            user = await self.get_user_by_any_id(user_id)
        if not user:
            return None
        internal_uid = user.get("user_id", user_id)
        if user.get("ref_code"):
            return user.get("ref_code")
        for attempt in range(20):
            code = generate_ref_code()
            existing = await self.get_user_by_ref_code(code)
            if existing:
                continue
            if await self.update_user(internal_uid, ref_code=code):
                return code
        return None

    @log_error
    async def ensure_ref_code_by_user_id(self, user_id: int) -> str | None:
        if not self.conn:
            return None
        try:
            user = await self.get_user_by_id(user_id)
            if not user:
                return None
            if user.get("ref_code"):
                return user.get("ref_code")
            for attempt in range(20):
                code = generate_ref_code()
                existing = await self.get_user_by_ref_code(code)
                if existing:
                    continue
                if await self.update_user(user_id, ref_code=code):
                    return code
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"ensure_ref_code_by_user_id {user_id}: {e}")
            return None

    @log_error
    async def reset_all_trials(self) -> tuple[int, int]:
        if not self.conn:
            return 0, 1
        try:
            cur_count = await self.conn.execute("SELECT COUNT(*) FROM users")
            total = cur_count.fetchone()[0]

            await self.conn.execute("UPDATE users SET trial_used = 0")
            await self.conn.commit()

            return total, 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"reset_all_trials: {e}")
            return 0, 1

    @log_error
    async def get_partner_by_user_id(self, user_id: int) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            if not row:
                return None
            return dict(row)
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_partner_by_user_id {user_id}: {e}")
            return None

    @log_error
    async def get_mate_user_ids(self) -> list[int]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute(
                "SELECT telegram_id FROM users WHERE is_mate = 1 AND telegram_id != 0"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_mate_user_ids: {e}")
            return []

    @log_error
    async def count_partner_referrals(self, user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute("SELECT COUNT(*) FROM users WHERE ref_by = ?", (user_id,))
            row = await cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"count_partner_referrals {user_id}: {e}")
            return 0

    @log_error
    async def count_partner_referrals_paid(self, user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute(
                """
                SELECT COUNT(*)
                FROM users
                WHERE ref_by = ? AND (ref_rewarded = 1 OR has_subscription = 1)
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:  # noqa: BLE001
            logger.error(f"count_partner_referrals_paid {user_id}: {e}")
            return 0

    @log_error
    async def set_user_as_partner(
        self,
        user_id: int,
        *,
        nickname: str,
        social_links: str,
        followers: int,
        avg_reach: int,
        period_months: int,
        bonus_type: str,
        bonus_value: int,
        ref_link_code: str,
    ) -> bool:
        if not self.conn:
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            logger.error(f"set_user_as_partner: пользователь не найден user_id={user_id}")
            return False
        internal_uid = user.get("user_id", user_id)
        try:
            async with self.lock:
                cursor = await self.conn.execute(
                    """UPDATE users SET
                        is_mate = 1,
                        mate_nickname = ?,
                        mate_social_links = ?,
                        mate_followers = ?,
                        mate_avg_reach = ?,
                        mate_period_months = ?,
                        mate_bonus_type = ?,
                        mate_bonus_value = ?,
                        mate_ref_link_code = ?,
                        mate_status = 'active'
                    WHERE user_id = ?""",
                    (
                        nickname,
                        social_links,
                        followers,
                        avg_reach,
                        period_months,
                        bonus_type,
                        bonus_value,
                        ref_link_code,
                        internal_uid,
                    ),
                )
                await self.conn.commit()
                if cursor.rowcount == 0:
                    logger.warning(f"set_user_as_partner {user_id}: 0 строк обновлено")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"set_user_as_partner {user_id}: {e}")
            return False

    @log_error
    async def update_partner_subscription(
        self, user_id: int, *, subscription_id: str, expiry: str
    ) -> bool:
        if not self.conn:
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            logger.error(f"update_partner_subscription: пользователь не найден user_id={user_id}")
            return False
        internal_uid = user.get("user_id", user_id)
        try:
            async with self.lock:
                await self.conn.execute(
                    """UPDATE users SET
                        mate_subscription_id = ?,
                        mate_expiry = ?
                    WHERE user_id = ?""",
                    (subscription_id, expiry, internal_uid),
                )
                await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"update_partner_subscription {user_id}: {e}")
            return False

    @log_error
    async def update_partner_balance(self, user_id: int, amount: float) -> bool:
        if not self.conn:
            return False
        user = await self.get_user_by_any_id(user_id)
        if not user:
            logger.error(f"update_partner_balance: пользователь не найден user_id={user_id}")
            return False
        internal_uid = user.get("user_id", user_id)
        try:
            async with self.lock:
                await self.conn.execute(
                    """UPDATE users SET
                        mate_balance = mate_balance + ?,
                        mate_commission_total = CASE
                            WHEN ? > 0 THEN mate_commission_total + ?
                            ELSE mate_commission_total
                        END
                    WHERE user_id = ?""",
                    (amount, amount, amount, internal_uid),
                )
                await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"update_partner_balance {user_id}: {e}")
            return False

    @log_error
    async def add_partner_application(
        self,
        telegram_id: int,
        followers: int,
        social_links: str,
        nickname: str,
        period_months: int,
        bonus_type: str,
        bonus_value: int,
        pd_consent: int,
    ) -> str | None:
        if not self.conn:
            return None
        try:
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user:
                logger.error(f"add_partner_application: пользователь не найден tg_id={telegram_id}")
                return None
            internal_user_id = user["user_id"]
            app_id = f"app_{telegram_id}_{int(time.time() * 1000)}"
            async with self.lock:
                await self.conn.execute(
                    """UPDATE users SET
                        mate_status = 'pending',
                        mate_nickname = ?,
                        mate_social_links = ?,
                        mate_followers = ?,
                        mate_period_months = ?,
                        mate_bonus_type = ?,
                        mate_bonus_value = ?
                    WHERE user_id = ?""",
                    (
                        nickname,
                        social_links,
                        followers,
                        period_months,
                        bonus_type,
                        bonus_value,
                        internal_user_id,
                    ),
                )
                await self.conn.commit()
            return app_id
        except Exception as e:  # noqa: BLE001
            logger.error(f"add_partner_application {telegram_id}: {e}")
            return None

    @log_error
    async def add_partner_withdrawal_request(
        self,
        telegram_id: int,
        amount: float,
        *,
        fio: str = "",
        phone: str = "",
        bank: str = "",
    ) -> str | None:
        if not self.conn:
            return None
        try:
            withdrawal_id = f"wd_{telegram_id}_{int(time.time() * 1000)}"
            user = await self.get_user_by_telegram_id(telegram_id)
            if not user:
                return None
            internal_user_id = user["user_id"]
            existing_requests = []
            raw = user.get("mate_withdrawal_requests", "[]")
            if raw:
                try:
                    existing_requests = json.loads(raw)
                except Exception:  # noqa: BLE001
                    existing_requests = []
            existing_requests.append(
                {
                    "withdrawal_id": withdrawal_id,
                    "amount": amount,
                    "fio": fio,
                    "phone": phone,
                    "bank": bank,
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            async with self.lock:
                await self.conn.execute(
                    """UPDATE users SET
                        mate_withdrawal_requests = ?
                    WHERE user_id = ?""",
                    (json.dumps(existing_requests), internal_user_id),
                )
                await self.conn.commit()
            return withdrawal_id
        except Exception as e:  # noqa: BLE001
            logger.error(f"add_partner_withdrawal_request {telegram_id}: {e}")
            return None

    # === Web auth methods ---
    @log_error
    async def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            cur = await self.conn.execute(
                "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
                (username.strip(),),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_by_username {username}: {e}")
            return None

    @log_error
    async def get_user_by_web_id(self, web_id: int) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            cur = await self.conn.execute("SELECT * FROM users WHERE web_id = ?", (web_id,))
            row = await cur.fetchone()
            return dict(row) if row else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_by_web_id {web_id}: {e}")
            return None

    @log_error
    async def get_unlinked_web_account(
        self,
    ) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            cur = await self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE telegram_id = 0 AND web_id > 0"
            )
            row = await cur.fetchone()
            if not row or row[0] != 1:
                return None
            cur = await self.conn.execute(
                "SELECT * FROM users WHERE telegram_id = 0 AND web_id > 0 LIMIT 1"
            )
            single = await cur.fetchone()
            return dict(single) if single else None
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_unlinked_web_account: {e}")
            return None

    @log_error
    async def get_user_by_session_token(self, token: str) -> dict[str, Any] | None:
        return await self.get_user_by_session_token_hash(hash_session_token(token))

    @log_error
    async def get_user_by_session_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            cur = await self.conn.execute(
                "SELECT * FROM users WHERE session_token = ?", (token_hash,)
            )
            row = await cur.fetchone()
            if not row:
                return None
            user = dict(row)
            expires_str = user.get("session_expires_at", "")
            if expires_str:
                try:
                    expires_at = datetime.fromisoformat(expires_str)
                    if datetime.now(timezone.utc) > expires_at:
                        logger.info(f"Session expired for user_id={user.get('user_id')}")
                        await self.update_web_auth(
                            user["user_id"], session_token="", session_expires_at=""
                        )
                        return None
                except (ValueError, TypeError):
                    pass
            return user
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_by_session_token_hash: {e}")
            return None

    @log_error
    async def create_web_account(
        self, username: str, password_hash: str, telegram_id: int | None = None
    ) -> dict[str, Any] | None:
        if not self.conn:
            return None
        try:
            now = datetime.now(timezone.utc).isoformat()
            tg_id = telegram_id if telegram_id else 0
            async with self.lock:
                cursor = await self.conn.execute(
                    "INSERT INTO users (telegram_id, username, password_hash, web_registered_at, web_auth_method, session_token, session_expires_at, session_created_at) VALUES (?, ?, ?, ?, 'local', '', '', '')",
                    (
                        tg_id,
                        username.strip(),
                        password_hash,
                        now,
                    ),
                )
                user_id = cursor.lastrowid
                if not user_id:
                    return None
                await self.conn.execute(
                    "UPDATE users SET web_id = ? WHERE user_id = ?",
                    (user_id, user_id),
                )
                await self.conn.commit()
            return await self.get_user_by_id(user_id)
        except Exception as e:  # noqa: BLE001
            logger.error(f"create_web_account: {e}")
            return None

    @log_error
    async def update_web_auth(
        self,
        user_id: int,
        *,
        password_hash: str | None = None,
        telegram_id: int | None = None,
        web_auth_method: str | None = None,
        session_token: str | None = None,
        session_expires_at: str | None = None,
        session_created_at: str | None = None,
        web_last_login: str | None = None,
        web_id: int | None = None,
        web_registered_at: str | None = None,
    ) -> bool:
        if not self.conn:
            return False
        try:
            updates = []
            values = []
            if password_hash is not None:
                updates.append("password_hash = ?")
                values.append(password_hash)
            if telegram_id is not None:
                updates.append("telegram_id = ?")
                values.append(telegram_id)
            if web_auth_method is not None:
                updates.append("web_auth_method = ?")
                values.append(web_auth_method)
            if session_token is not None:
                updates.append("session_token = ?")
                values.append(hash_session_token(session_token) if session_token else "")
            if session_expires_at is not None:
                updates.append("session_expires_at = ?")
                values.append(session_expires_at)
            if session_created_at is not None:
                updates.append("session_created_at = ?")
                values.append(session_created_at)
            if web_last_login is not None:
                updates.append("web_last_login = ?")
                values.append(web_last_login)
            if web_id is not None:
                updates.append("web_id = ?")
                values.append(web_id)
            if web_registered_at is not None:
                updates.append("web_registered_at = ?")
                values.append(web_registered_at)
            if not updates:
                return False
            values.append(user_id)
            async with self.lock:
                await self.conn.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?",
                    values,
                )
                await self.conn.commit()
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"update_web_auth {user_id}: {e}")
            return False

    @log_error
    async def get_user_stats(self) -> dict[str, Any]:
        if not self.conn:
            return {}
        try:
            stats: dict[str, Any] = {}
            cur = await self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE (web_id IS NOT NULL AND web_id != 0) OR (telegram_id IS NOT NULL AND telegram_id != 0)"
            )
            row = await cur.fetchone()
            stats["total_users"] = int(row[0]) if row else 0
            cur = await self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE has_subscription = 1 AND ((web_id IS NOT NULL AND web_id != 0) OR (telegram_id IS NOT NULL AND telegram_id != 0))"
            )
            row = await cur.fetchone()
            stats["active_subscriptions"] = int(row[0]) if row else 0
            try:
                banned = await self.get_banned_users_count()
                stats["banned_users"] = banned
            except Exception:  # noqa: BLE001
                stats["banned_users"] = 0
            return stats
        except Exception as e:  # noqa: BLE001
            logger.error(f"get_user_stats: {e}")
            return {}

    @log_error
    async def _compare_subscriptions(self, user_a: dict[str, Any], user_b: dict[str, Any]) -> int:
        try:
            a_sub = user_a.get("has_subscription", 0)
            b_sub = user_b.get("has_subscription", 0)
            if a_sub and not b_sub:
                return 1
            if b_sub and not a_sub:
                return -1
            if not a_sub and not b_sub:
                return 0

            a_expiry = user_a.get("expiry_sub_datatime", "")
            b_expiry = user_b.get("expiry_sub_datatime", "")
            if a_expiry and b_expiry:
                try:
                    a_dt = datetime.fromisoformat(a_expiry)
                    b_dt = datetime.fromisoformat(b_expiry)
                    if a_dt > b_dt:
                        return 1
                    if b_dt > a_dt:
                        return -1
                except (ValueError, TypeError):
                    pass

            a_traffic = user_a.get("traffic_gb", 0) + user_a.get("extra_sub_gb", 0)
            b_traffic = user_b.get("traffic_gb", 0) + user_b.get("extra_sub_gb", 0)
            if a_traffic > b_traffic:
                return 1
            if b_traffic > a_traffic:
                return -1

            a_ip = user_a.get("ip_limit", 0)
            b_ip = user_b.get("ip_limit", 0)
            if a_ip > b_ip:
                return 1
            if b_ip > a_ip:
                return -1

            return 0
        except Exception:  # noqa: BLE001
            return 0

    @log_error
    async def merge_accounts(self, user_a_id: int, user_b_id: int) -> bool:
        if not self.conn or user_a_id == user_b_id:
            return False
        try:
            async with self.lock:
                cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_a_id,))
                row_a = await cur.fetchone()
                if not row_a:
                    return False
                data_a = dict(row_a)

                cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_b_id,))
                row_b = await cur.fetchone()
                if not row_b:
                    return False
                data_b = dict(row_b)

                better = await self._compare_subscriptions(data_a, data_b)
                if better >= 0:
                    keep_data = data_a
                    delete_data = data_b
                    keep_id = user_a_id
                    delete_id = user_b_id
                else:
                    keep_data = data_b
                    delete_data = data_a
                    keep_id = user_b_id
                    delete_id = user_a_id

                sub_fields = [
                    "has_subscription",
                    "plan_text",
                    "plan_servers",
                    "subscription_id",
                    "ip_limit",
                    "traffic_gb",
                    "vpn_url",
                    "expiry_sub_datatime",
                    "extra_sub_gb",
                    "expiry_alert_sent",
                    "cleanup_notification_sent",
                ]
                updates = {}
                for field in sub_fields:
                    val = delete_data.get(field)
                    if val is not None and val != "" and val != 0:  # noqa: SIM102
                        if (
                            not keep_data.get(field)
                            or keep_data.get(field) == ""
                            or keep_data.get(field) == 0
                        ):
                            updates[field] = val

                if delete_data.get("ref_code") and not keep_data.get("ref_code"):
                    updates["ref_code"] = delete_data["ref_code"]
                if delete_data.get("ref_by") and not keep_data.get("ref_by"):
                    updates["ref_by"] = delete_data["ref_by"]

                if delete_data.get("trust_score", 0) > keep_data.get("trust_score", 0):
                    updates["trust_score"] = delete_data["trust_score"]

                if delete_data.get("discount_percent", 0) > keep_data.get("discount_percent", 0):
                    updates["discount_percent"] = delete_data["discount_percent"]

                if updates:
                    set_clause = ", ".join(f"{k} = ?" for k in updates)
                    values = list(updates.values()) + [keep_id]
                    await self.conn.execute(
                        f"UPDATE users SET {set_clause} WHERE user_id = ?",
                        values,
                    )

                if delete_data.get("telegram_id") and delete_data["telegram_id"] != keep_data.get(
                    "telegram_id"
                ):
                    if not keep_data.get("telegram_id"):
                        await self.conn.execute(
                            "UPDATE users SET telegram_id = ? WHERE user_id = ?",
                            (delete_data["telegram_id"], keep_id),
                        )
                    await self.conn.execute(
                        "UPDATE users SET telegram_id = 0 WHERE user_id = ?",
                        (delete_id,),
                    )

                await self.conn.execute(
                    "DELETE FROM users WHERE user_id = ?",
                    (delete_id,),
                )
                await self.conn.commit()
            logger.info(f"merge_accounts: kept user_id={keep_id}, deleted user_id={delete_id}")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"merge_accounts {user_a_id}<->{user_b_id}: {e}")
            return False

    @log_error
    async def search_users(self, query: str) -> list[dict[str, Any]]:
        if not self.conn:
            return []
        try:
            q = query.strip()
            if not q:
                return []
            query_int = None
            try:
                query_int = int(q)
            except (ValueError, TypeError):
                pass

            sql = "SELECT * FROM users WHERE 1=0"
            params: list[Any] = []
            order_clause = "ORDER BY CASE WHEN 1=0 THEN 0"

            if query_int is not None:
                sql += " OR user_id = ? OR telegram_id = ?"
                params.extend([query_int, query_int])
                order_clause += " WHEN user_id = ? THEN 1 WHEN telegram_id = ? THEN 2"
                params.extend([query_int, query_int])

            like_pattern = f"%{q}%"
            sql += " OR username LIKE ? OR ref_code LIKE ? OR vpn_url LIKE ? OR mate_nickname LIKE ? OR mate_ref_link_code LIKE ?"
            params.extend([like_pattern, like_pattern, like_pattern, like_pattern, like_pattern])
            order_clause += " ELSE 3 END, user_id"
            sql += f" {order_clause} LIMIT 50"

            async with self.lock:
                cur = await self.conn.execute(sql, params)
                rows = await cur.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:  # noqa: BLE001
            logger.error(f"search_users {query}: {e}")
            return []

    @log_error
    async def smart_lookup(self, query: int) -> list[dict[str, Any]]:
        if not self.conn:
            return []
        try:
            results: list[dict[str, Any]] = []

            async with self.lock:
                cur = await self.conn.execute(
                    "SELECT * FROM users WHERE user_id = ? LIMIT 5",
                    (query,),
                )
                by_uid = await cur.fetchall()
                for row in by_uid:
                    d = dict(row)
                    d["_match_type"] = "user_id"
                    results.append(d)

                if len(results) < 5:
                    cur = await self.conn.execute(
                        "SELECT * FROM users WHERE telegram_id = ? LIMIT ?",
                        (query, 5 - len(results)),
                    )
                    by_tgid = await cur.fetchall()
                    for row in by_tgid:
                        if not any(r.get("user_id") == row["user_id"] for r in results):
                            d = dict(row)
                            d["_match_type"] = "telegram_id"
                            results.append(d)

            return results[:5]
        except Exception as e:  # noqa: BLE001
            logger.error(f"smart_lookup {query}: {e}")
            return []

    @log_error
    async def reconcile_telegram_account(self, telegram_id: int) -> int | None:
        if not self.conn or not telegram_id:
            return None
        try:
            async with self.lock:
                cur = await self.conn.execute(
                    "SELECT * FROM users WHERE telegram_id = ?",
                    (telegram_id,),
                )
                rows = [dict(r) for r in await cur.fetchall()]
            if not rows:
                return None
            admin_rows = [u for u in rows if await is_admin_user(u.get("telegram_id", 0) or 0)]
            if len(rows) == 1:
                only = rows[0]
                if only.get("telegram_id", 0) != telegram_id:
                    await self.update_web_auth(
                        only["user_id"],
                        telegram_id=telegram_id,
                    )
                return only["user_id"]

            def has_web(u: dict[str, Any]) -> bool:
                return bool(u.get("username")) or (u.get("web_id") not in (None, 0))

            web_rows = [u for u in rows if has_web(u)]
            if admin_rows:
                keeper = max(
                    admin_rows,
                    key=lambda u: (
                        int(u.get("has_subscription", 0) or 0),
                        u.get("expiry_sub_datatime") or "",
                    ),
                )
            elif web_rows:
                keeper = max(
                    web_rows,
                    key=lambda u: (
                        int(u.get("has_subscription", 0) or 0),
                        u.get("expiry_sub_datatime") or "",
                    ),
                )
            else:
                keeper = max(
                    rows,
                    key=lambda u: (
                        int(u.get("has_subscription", 0) or 0),
                        u.get("expiry_sub_datatime") or "",
                    ),
                )

            sub_fields = [
                "has_subscription",
                "plan_text",
                "plan_servers",
                "subscription_id",
                "ip_limit",
                "traffic_gb",
                "vpn_url",
                "expiry_sub_datatime",
                "extra_sub_gb",
                "expiry_alert_sent",
                "cleanup_notification_sent",
            ]
            updates: dict[str, Any] = {}
            for other in rows:
                if other["user_id"] == keeper["user_id"]:
                    continue
                for field in sub_fields + [
                    "ref_code",
                    "ref_by",
                    "trust_score",
                    "discount_percent",
                ]:
                    val = other.get(field)
                    if val not in (None, "", 0) and not keeper.get(field):
                        updates[field] = val
                for field in ["password_hash"]:
                    if not keeper.get(field) and other.get(field):
                        updates[field] = other[field]
                for field in [
                    "web_id",
                    "web_registered_at",
                    "web_auth_method",
                    "web_last_login",
                ]:
                    if not keeper.get(field) and other.get(field):
                        updates[field] = other[field]
                await self.conn.execute("DELETE FROM users WHERE user_id = ?", (other["user_id"],))
            updates["telegram_id"] = telegram_id
            if updates:
                set_clause = ", ".join(f"{k} = ?" for k in updates)
                values = list(updates.values()) + [keeper["user_id"]]
                async with self.lock:
                    await self.conn.execute(
                        f"UPDATE users SET {set_clause} WHERE user_id = ?",
                        values,
                    )
                    await self.conn.commit()
            logger.info(
                f"reconcile_telegram_account: tg={telegram_id} -> kept user_id={keeper['user_id']}"
            )
            return keeper["user_id"]
        except Exception as e:  # noqa: BLE001
            logger.error(f"reconcile_telegram_account {telegram_id}: {e}")
            return None

    @log_error
    async def delete_phantom_account(self, user_id: int) -> bool:
        if not self.conn:
            return False
        try:
            async with self.lock:
                cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
                row = await cur.fetchone()
                if not row:
                    return False
                data = dict(row)
                if data.get("has_subscription", 0):
                    return False
                if data.get("web_id"):
                    return False
                if data.get("username") or data.get("password_hash"):
                    return False
                await self.conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                await self.conn.commit()
            logger.info(f"delete_phantom_account: deleted user_id={user_id}")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"delete_phantom_account {user_id}: {e}")
            return False

    @log_error
    async def cleanup_telegram_phantoms(self, telegram_id: int, keep_user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            async with self.lock:
                cur = await self.conn.execute(
                    "SELECT user_id FROM users WHERE telegram_id = ? AND user_id != ?",
                    (telegram_id, keep_user_id),
                )
                rows = await cur.fetchall()
                deleted = 0
                for row in rows:
                    uid = row[0]
                    cur2 = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (uid,))
                    data = dict(await cur2.fetchone())
                    if data.get("has_subscription", 0):
                        continue
                    if data.get("web_id"):
                        continue
                    await self.conn.execute("DELETE FROM users WHERE user_id = ?", (uid,))
                    deleted += 1
                if deleted:
                    await self.conn.commit()
            logger.info(f"cleanup_telegram_phantoms: tg={telegram_id}, deleted={deleted}")
            return deleted
        except Exception as e:  # noqa: BLE001
            logger.error(f"cleanup_telegram_phantoms {telegram_id}: {e}")
            return 0


# --- JSON Storage для платежей ---

try:
    import fcntl as _fcntl
except ImportError:
    _fcntl = None  # Windows fallback

try:
    import msvcrt as _msvcrt
except ImportError:
    _msvcrt = None


class _InterProcessFileLock:
    def __init__(self, lock_path: str) -> None:
        self.lock_path = lock_path

    async def __aenter__(self) -> Self:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._acquire)
        return self

    async def __aexit__(self, *exc: object) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._release)

    def _acquire(self) -> None:
        if getattr(self, "_fh", None) is not None:
            return
        fh = open(self.lock_path, "a+")  # noqa: SIM115
        self._fh = fh
        try:
            if _fcntl:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
            elif _msvcrt:
                _msvcrt.locking(fh.fileno(), _msvcrt.LK_LOCK, 1)
        except OSError:
            fh.close()
            self._fh = None  # type: ignore[attr-defined]
            raise

    def _release(self) -> None:
        fh = getattr(self, "_fh", None)
        if fh is None:
            return
        try:
            if _fcntl:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt:
                _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, 1)
        except (OSError, ValueError):
            pass
        finally:
            try:
                fh.close()
            except OSError:
                pass
            self._fh = None  # type: ignore[attr-defined]


class JSONStorage:
    def __init__(self, path: str) -> None:
        self.path: str = path
        self._lock: asyncio.Lock = asyncio.Lock()
        self._file_lock: _InterProcessFileLock = _InterProcessFileLock(f"{path}.lock")
        self._data: list[dict[str, Any]] = []

    async def _ensure_file(self) -> None:
        if os.path.exists(self.path):
            return
        try:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        except Exception:  # noqa: BLE001, S110
            pass
        if not os.path.exists(self.path):
            try:
                async with aiofiles.open(self.path, "w", encoding="utf-8") as f:
                    await f.write("[]")
            except Exception:  # noqa: BLE001, S110
                pass

    @log_error
    async def _load(self) -> list[dict[str, Any]]:
        async with self._file_lock:
            return await self._load_data()

    async def _load_data(self) -> list[dict[str, Any]]:
        if os.path.exists(self.path):
            try:
                async with aiofiles.open(self.path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    if content:
                        parsed = json.loads(content)
                        if not isinstance(parsed, list):
                            logger.error(f"Некорректный формат {self.path}: ожидался список")
                            self._data = []
                        else:
                            self._data = parsed
                            logger.info(f"Загружено {len(self._data)} записей из {self.path}")
                    else:
                        self._data = []
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка загрузки {self.path}: {e}")
                self._data = []
        else:
            self._data = []
        return self._data

    async def _run_locked(self, callback):
        async with self._file_lock:
            await self._load_data()
            result = await callback(self._data)
            await self._save_data()
            return result

    @log_error
    async def _save(self) -> None:
        async with self._file_lock:
            await self._save_data()

    async def _save_data(self) -> None:
        try:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            tmp_path = f"{self.path}.tmp"
            async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                await f.write(json.dumps(self._data, ensure_ascii=False, indent=2))
            os.replace(tmp_path, self.path)
        except Exception as e:
            logger.error(f"Ошибка сохранения {self.path}: {e}")
            raise

    @log_error
    async def add_pending_for_user(self, user_id: int, payment: dict[str, Any]) -> bool:
        try:
            async with self._lock:
                await self._load()
                existing = [
                    p
                    for p in self._data
                    if str(p.get("user_id")) == str(user_id)
                    and p.get("status") in {"pending", "processing"}
                ]
                if existing:
                    return False
                self._data.append(payment)
                await self._save()
                return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка add_pending_for_user {user_id}: {e}")
            return False

    @log_error
    async def claim_pending_payment(
        self, payment_id: str, moderator_id: int, action: str
    ) -> dict[str, Any] | None:
        async def _claim(data: list[dict[str, Any]]) -> dict[str, Any] | None:
            for p in data:
                if str(p.get("payment_id")) == str(payment_id):
                    if p.get("status") != "pending":
                        return None
                    processing = p.get("processing_by")
                    if processing is not None and processing != moderator_id:
                        return None
                    p["status"] = "processing"
                    p["processing_by"] = moderator_id
                    p["processing_action"] = action
                    p["processing_at"] = datetime.now(timezone.utc).isoformat()
                    return dict(p)
            return None

        try:
            return await self._run_locked(_claim)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка claim_pending_payment {payment_id}: {e}")
            return None

    @log_error
    async def finalize_claimed_payment(
        self,
        payment_id: str,
        moderator_id: int,
        action: str,
        final_status: str,
    ) -> bool:
        async def _finalize(data: list[dict[str, Any]]) -> bool:
            for p in data:
                if str(p.get("payment_id")) == str(payment_id):
                    if p.get("status") != "processing":
                        return False
                    if p.get("processing_by") != moderator_id:
                        return False
                    if p.get("processing_action") not in (None, action):
                        return False
                    p["status"] = final_status
                    p["processed_by"] = moderator_id
                    p["processed_action"] = action
                    p["processed_at"] = datetime.now(timezone.utc).isoformat()
                    p["processing_by"] = None
                    p["processing_at"] = None
                    return True
            return False

        try:
            return await self._run_locked(_finalize)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка finalize_claimed_payment {payment_id}: {e}")
            return False

    @log_error
    async def find_by_id(self, payment_id: str) -> dict[str, Any] | None:
        try:
            async with self._lock:
                await self._load()
                for p in self._data:
                    if str(p.get("payment_id")) == str(payment_id):
                        return dict(p)
                return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка find_by_id {payment_id}: {e}")
            return None

    @log_error
    async def has_pending_payment_for_user(self, user_id: int) -> bool:
        try:
            async with self._lock:
                await self._load()
                return any(
                    str(p.get("user_id")) == str(user_id)
                    and p.get("status") in {"pending", "processing"}
                    for p in self._data
                    if isinstance(p, dict)
                )
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка has_pending_payment_for_user {user_id}: {e}")
            return False

    @log_error
    async def read_all(self) -> list[dict[str, Any]]:
        try:
            async with self._lock:
                await self._load()
                return [dict(item) for item in self._data if isinstance(item, dict)]
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка read_all: {e}")
            return []

    @log_error
    async def release_stale_processing_payments(self) -> int:
        try:
            async with self._lock:
                await self._load()
                released = 0
                now = datetime.now(timezone.utc)
                for p in self._data:
                    if p.get("status") != "processing":
                        continue
                    processing_at = p.get("processing_at")
                    if not processing_at:
                        continue
                    try:
                        pt = datetime.fromisoformat(processing_at)
                        if (now - pt).total_seconds() > Config.PAYMENT_PROCESSING_TIMEOUT_SEC:
                            p["status"] = "pending"
                            p["processing_by"] = None
                            p["processing_at"] = None
                            p["processing_action"] = None
                            p["last_error"] = "Timeout"
                            released += 1
                    except Exception:  # noqa: BLE001, S112
                        continue
                if released > 0:
                    await self._save()
                return released
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка release_stale_processing_payments: {e}")
            return 0

    @log_error
    async def remove(self, predicate: Callable[[dict[str, Any]], bool]) -> None:
        try:
            async with self._lock:
                await self._load()
                before = len(self._data)
                self._data = [p for p in self._data if not predicate(p)]
                after = len(self._data)
                if before != after:
                    await self._save()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка remove: {e}")

    @log_error
    async def rollback_claimed_payment(
        self,
        payment_id: str,
        moderator_id: int,
        action: str,
        error_message: str = "",
    ) -> None:
        async def _rollback(data: list[dict[str, Any]]) -> None:
            for p in data:
                if str(p.get("payment_id")) == str(payment_id):
                    if p.get("status") != "processing":
                        return
                    if p.get("processing_by") != moderator_id:
                        return
                    if p.get("processing_action") not in (None, action):
                        return
                    p["status"] = "pending"
                    p["processing_by"] = None
                    p["processing_at"] = None
                    p["processing_action"] = None
                    p["last_error"] = error_message
                    return

        try:
            await self._run_locked(_rollback)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка rollback_claimed_payment {payment_id}: {e}")


# --- In-memory bot auth states ---
_bot_auth_states: dict[str, dict[str, Any]] = {}
_bot_auth_lock = asyncio.Lock()


async def create_bot_auth_state(
    state: str, state_type: str, session_token: str = "", ttl: int = 300
) -> bool:
    try:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
        async with _bot_auth_lock:
            _bot_auth_states[state] = {
                "state": state,
                "state_type": state_type,
                "session_token": (hash_session_token(session_token) if session_token else ""),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat(),
                "completed": False,
                "auth_token": "",
            }
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"create_bot_auth_state: {e}")
        return False


async def complete_bot_auth_state(state: str, auth_token: str) -> bool:
    try:
        async with _bot_auth_lock:
            if state in _bot_auth_states:
                _bot_auth_states[state]["completed"] = True
                _bot_auth_states[state]["auth_token"] = auth_token
                # Schedule cleanup after 30 seconds to allow polling to complete
                asyncio.create_task(_delayed_auth_state_cleanup(state, 30))
                return True
        return False
    except Exception as e:  # noqa: BLE001
        logger.error(f"complete_bot_auth_state: {e}")
        return False


async def _delayed_auth_state_cleanup(state: str, delay: int) -> None:
    await asyncio.sleep(delay)
    async with _bot_auth_lock:
        _bot_auth_states.pop(state, None)


async def get_bot_auth_state(state: str) -> dict[str, Any] | None:
    try:
        async with _bot_auth_lock:
            data = _bot_auth_states.get(state)
        if not data:
            return None
        expires_str = data.get("expires_at", "")
        if expires_str:
            try:
                expires_at = datetime.fromisoformat(expires_str)
                if datetime.now(timezone.utc) > expires_at:
                    return None
            except (ValueError, TypeError):
                pass
        return data
    except Exception as e:  # noqa: BLE001
        logger.error(f"get_bot_auth_state: {e}")
        return None


async def consume_bot_auth_state(state: str) -> dict[str, Any] | None:
    try:
        async with _bot_auth_lock:
            data = _bot_auth_states.pop(state, None)
        if not data:
            return None
        expires_str = data.get("expires_at", "")
        if expires_str:
            try:
                expires_at = datetime.fromisoformat(expires_str)
                if datetime.now(timezone.utc) > expires_at:
                    return None
            except (ValueError, TypeError):
                pass
        return data
    except Exception as e:  # noqa: BLE001
        logger.error(f"consume_bot_auth_state: {e}")
        return None


_bot_telegram_verifications: dict[str, int] = {}
_bot_telegram_verifications_expiry: dict[str, datetime] = {}


async def store_telegram_verification(state: str, telegram_id: int, ttl: int = 300) -> None:
    try:
        async with _bot_auth_lock:
            _bot_telegram_verifications[state] = telegram_id
            _bot_telegram_verifications_expiry[state] = datetime.now(timezone.utc) + timedelta(
                seconds=ttl
            )
    except Exception as e:  # noqa: BLE001
        logger.error(f"store_telegram_verification: {e}")


async def consume_telegram_verification(state: str) -> int | None:
    try:
        async with _bot_auth_lock:
            telegram_id = _bot_telegram_verifications.pop(state, None)
            expiry = _bot_telegram_verifications_expiry.pop(state, None)
        if telegram_id is None:
            return None
        if expiry and datetime.now(timezone.utc) > expiry:
            return None
        return telegram_id
    except Exception as e:  # noqa: BLE001
        logger.error(f"consume_telegram_verification: {e}")
        return None


# --- Partner Operations Storage (JSON) ---
_partner_storage: JSONStorage | None = None


def _get_partner_storage() -> JSONStorage:
    global _partner_storage
    if _partner_storage is None:
        _partner_storage = JSONStorage(Config.PARTNER_OPS_FILE)
    return _partner_storage


async def _ensure_partner_ops_file() -> None:
    storage = _get_partner_storage()
    await storage._ensure_file()


async def add_partner_operation(user_id: int, op_type: str, data: dict[str, Any]) -> str | None:
    try:
        storage = _get_partner_storage()
        async with storage._lock:
            await storage._load()
            existing = [
                o
                for o in storage._data
                if str(o.get("user_id")) == str(user_id)
                and o.get("op_type") == op_type
                and o.get("status") in {"pending", "processing"}
            ]
            if existing:
                logger.warning(
                    f"У пользователя {user_id} уже есть pending/processing операция типа {op_type}"
                )
                return None
            op_id = f"partner_{op_type}_{user_id}_{int(time.time() * 1000)}"
            operation = {
                "operation_id": op_id,
                "user_id": user_id,
                "op_type": op_type,
                **data,
                "status": "pending",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            storage._data.append(operation)
            await storage._save()
            logger.info(f"Добавлена партнёрская операция {op_id} для user {user_id}")
            return op_id
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка add_partner_operation: {e}")
        return None


async def get_pending_partner_operations() -> list[dict[str, Any]]:
    try:
        storage = _get_partner_storage()
        async with storage._lock:
            await storage._load()
            return [dict(o) for o in storage._data if o.get("status") == "pending"]
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка get_pending_partner_operations: {e}")
        return []


async def claim_partner_operation(
    operation_id: str, admin_id: int, action: str
) -> dict[str, Any] | None:
    try:
        storage = _get_partner_storage()
        async with storage._lock:
            await storage._load()
            for o in storage._data:
                if str(o.get("operation_id")) == str(operation_id):
                    if o.get("status") != "pending":
                        return None
                    processing = o.get("processing_by")
                    if processing is not None and processing != admin_id:
                        return None
                    o["status"] = "processing"
                    o["processing_by"] = admin_id
                    o["processing_action"] = action
                    o["processing_at"] = datetime.now(timezone.utc).isoformat()
                    await storage._save()
                    return dict(o)
            return None
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка claim_partner_operation {operation_id}: {e}")
        return None


async def finalize_partner_operation(
    operation_id: str,
    admin_id: int,
    action: str,
    final_status: str,
) -> bool:
    try:
        storage = _get_partner_storage()
        async with storage._lock:
            await storage._load()
            for o in storage._data:
                if str(o.get("operation_id")) == str(operation_id):
                    if o.get("status") != "processing":
                        return False
                    if o.get("processing_by") != admin_id:
                        return False
                    if o.get("processing_action") not in (None, action):
                        return False
                    o["status"] = final_status
                    o["processed_by"] = admin_id
                    o["processed_action"] = action
                    o["processed_at"] = datetime.now(timezone.utc).isoformat()
                    o["processing_by"] = None
                    o["processing_at"] = None
                    await storage._save()
                    return True
            return False
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка finalize_partner_operation {operation_id}: {e}")
        return False


async def release_stale_partner_operations() -> int:
    try:
        storage = _get_partner_storage()
        async with storage._lock:
            await storage._load()
            released = 0
            now = datetime.now(timezone.utc)
            for o in storage._data:
                if o.get("status") != "processing":
                    continue
                processing_at = o.get("processing_at")
                if not processing_at:
                    continue
                try:
                    pt = datetime.fromisoformat(processing_at)
                    if (now - pt).total_seconds() > Config.PAYMENT_PROCESSING_TIMEOUT_SEC:
                        o["status"] = "pending"
                        o["processing_by"] = None
                        o["processing_at"] = None
                        o["processing_action"] = None
                        o["last_error"] = "Timeout"
                        released += 1
                except Exception:  # noqa: BLE001, S112
                    continue
            if released > 0:
                await storage._save()
            return released
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка release_stale_partner_operations: {e}")
        return 0


async def remove_partner_operation(predicate: Callable[[dict[str, Any]], bool]) -> None:
    try:
        storage = _get_partner_storage()
        async with storage._lock:
            await storage._load()
            before = len(storage._data)
            storage._data = [o for o in storage._data if not predicate(o)]
            after = len(storage._data)
            if before != after:
                await storage._save()
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка remove_partner_operation: {e}")


# --- 3X-UI Panel API ---
class PanelAPI:
    def __init__(self) -> None:
        self.apibase: str = Config.PANEL_BASE.rstrip("/")
        self.username: str = Config.PANEL_LOGIN
        self.password: str = Config.PANEL_PASSWORD
        self.verifyssl: bool = Config.VERIFY_SSL
        self.session: aiohttp.ClientSession | None = None
        self.token: str | None = Config.PANEL_TOKEN or None
        self.logged_in: bool = bool(self.token)
        self.lock: asyncio.Lock = asyncio.Lock()
        self._clients_cache: dict[str, Any] | None = None
        self._clients_cache_ts: float = 0.0
        self._clients_cache_ttl: float = 5.0

    @staticmethod
    def _client_payload_for_update(client: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(client, dict):
            return {}
        passthrough = (
            "id",
            "email",
            "enable",
            "flow",
            "limitIp",
            "totalGB",
            "expiryTime",
            "subId",
            "tgId",
            "uuid",
            "password",
            "method",
            "security",
            "alterId",
            "reset",
            "comment",
            "reverse",
            "inboundIds",
        )
        payload: dict[str, Any] = {
            key: client[key] for key in passthrough if key in client and client.get(key) is not None
        }
        if "id" in payload:
            payload["id"] = str(payload["id"])
        if "email" not in payload:
            payload["email"] = str(client.get("email") or "")
        if "enable" not in payload:
            payload["enable"] = bool(client.get("enable", True))
        if "limitIp" not in payload:
            payload["limitIp"] = max(0, to_int(client.get("limitIp"), 0))
        if "totalGB" not in payload:
            payload["totalGB"] = max(0, to_int(client.get("total", client.get("totalGB", 0)), 0))
        if "expiryTime" not in payload:
            payload["expiryTime"] = max(0, to_int(client.get("expiryTime"), 0))
        return payload

    @staticmethod
    def _client_rows_from_response(data: dict[str, Any]) -> list[dict[str, Any]]:
        obj = data.get("obj") or []
        if isinstance(obj, dict):
            items = obj.get("items")
            if isinstance(items, list):
                return items
            if isinstance(obj.get("clients"), list):
                return obj.get("clients")
            if isinstance(obj.get("data"), list):
                return obj.get("data")
            return []
        if isinstance(obj, list):
            return obj
        return []

    async def _collect_unique_client_emails(self, base_email: str) -> list[str]:
        ok, clients = await self.find_clients_full_by_email_safe(base_email)
        if not ok or not clients:
            return []
        emails: list[str] = []
        seen: set[str] = set()
        for c in clients:
            email = str(c.get("email") or "")
            if email and email not in seen:
                seen.add(email)
                emails.append(email)
        return emails

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"{BEARER_PREFIX}{self.token}"
        return headers

    def _invalidate_clients_cache(self) -> None:
        self._clients_cache = None
        self._clients_cache_ts = 0.0

    @staticmethod
    def _is_base_email(email: str, base_email: str) -> bool:
        if not email or not base_email:
            return False
        return email == base_email

    @staticmethod
    def _needs_reauth(status: int, data: dict[str, Any]) -> bool:
        if status in (401, 403):
            return True
        if status == 500:
            return False
        if status >= 400 and data.get("success") is False:
            logger.warning(
                f"Неизвестная ошибка аутентификации: статус={status}, msg={data.get('msg', '')}"
            )
            return True
        return False

    @staticmethod
    def _normalize_client_row(row: dict[str, Any]) -> dict[str, Any]:
        item = dict(row)
        traffic = item.get("traffic") if isinstance(item.get("traffic"), dict) else {}
        item["up"] = to_int(traffic.get("up", item.get("up", 0)), 0)
        item["down"] = to_int(traffic.get("down", item.get("down", 0)), 0)
        item["total"] = to_int(item.get("totalGB", item.get("total", 0)), 0)
        item["expiryTime"] = to_int(item.get("expiryTime", 0), 0)
        item["enable"] = bool(item.get("enable", traffic.get("enable", True)))
        item["clientObj"] = dict(row)
        return item

    @staticmethod
    def _quote_path(value: Any) -> str:
        return quote(str(value or "").strip(), safe="")

    @log_error
    async def _request_json(
        self, method: str, url: str, **kwargs: Any
    ) -> tuple[int, dict[str, Any], str]:
        if not self.session:
            logger.error(f"_request_json: сессия не инициализирована для {url}")
            return 0, {}, ""
        try:
            async with self.session.request(method, url, **kwargs) as resp:
                text = await resp.text()
                try:
                    parsed = json.loads(text) if text else {}
                except json.JSONDecodeError:
                    parsed = {}
                data = parsed if isinstance(parsed, dict) else {"obj": parsed}
                return resp.status, data, text
        except aiohttp.ClientError as e:
            logger.error(f"HTTP ошибка {method} {url}: {type(e).__name__}: {e}")
            return 0, {}, ""
        except Exception as e:  # noqa: BLE001
            logger.error(f"Неожиданная ошибка {method} {url}: {type(e).__name__}: {e}")
            return 0, {}, ""

    @log_error
    async def _request_json_with_reauth(
        self, method: str, url: str, **kwargs: Any
    ) -> tuple[int, dict[str, Any], str]:
        status, data, text = await self._request_json(method, url, **kwargs)
        if self._needs_reauth(status, data):
            logger.warning("Требуется реавторизация")
            await self.login()
            status, data, text = await self._request_json(method, url, **kwargs)
        return status, data, text

    async def add_client_traffic(self, base_email: str, add_gb: int) -> bool:
        if add_gb <= 0:
            return False
        emails = await self._collect_unique_client_emails(base_email)
        if not emails:
            logger.warning(f"add_client_traffic: нет email для начисления трафика {base_email}")
            return False
        add_bytes = int(add_gb * BYTES_IN_GB)
        url = f"{self.apibase}/panel/api/clients/bulkAdjust"
        payload: dict[str, Any] = {"emails": emails, "addBytes": add_bytes}
        status, data, _ = await self._request_json_with_reauth(
            "POST", url, headers=self._headers(), json=payload
        )
        if status in (200, 201) and data.get("success"):
            obj = data.get("obj") or {}
            adjusted = to_int(obj.get("adjusted", 0), 0) if isinstance(obj, dict) else 0
            logger.info(f"add_client_traffic: начислено {add_gb} ГБ для {adjusted} клиентов")
            if adjusted > 0 or data.get("success"):
                self._invalidate_clients_cache()
            return adjusted > 0 or data.get("success")
        logger.error(
            f"add_client_traffic: ошибка bulkAdjust для {emails}: "
            f"status={status}, msg={data.get('msg')}"
        )
        return False

    async def attach_client_to_inbounds(self, email: str, inbound_ids: list[int]) -> bool:
        await self.ensure_auth()
        if not email:
            return False
        clean_ids = [to_int(i, 0) for i in inbound_ids if to_int(i, 0) > 0]
        if not clean_ids:
            return False
        url = f"{self.apibase}/panel/api/clients/{self._quote_path(email)}/attach"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "POST",
                url,
                headers=self._headers(),
                json={"inboundIds": clean_ids},
            )
            if status in (200, 201) and data.get("success"):
                logger.info(f"attach_client: клиент {email} привязан к inbound'ам {clean_ids}")
                self._invalidate_clients_cache()
                return True
            logger.error(
                f"attach_client: ошибка для {email}: status={status}, "
                f"data={data}, msg={data.get('msg')}"
            )
            return False
        except Exception:
            logger.exception(f"attach_client: ошибка для {email}")
            return False

    @log_error
    async def close(self) -> None:
        if self.session:
            try:
                await self.session.close()
                logger.info("PanelAPI сессия закрыта")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Ошибка закрытия PanelAPI: {e}")
            finally:
                self.session = None

    @log_error
    async def create_client(
        self,
        email: str,
        limit_ip: int,
        total_gb: int,
        days: int = 30,
        servers: list[str] | None = None,
        tg_id: int = 0,
        inbound_ids: list[int] | None = None,
        sub_id: str | None = None,
    ) -> dict[str, Any] | None:
        logger.info(
            f"PanelAPI create_client: email={email}, ip={limit_ip}, gb={total_gb}, days={days}, tg_id={tg_id}, sub_id={sub_id}"
        )
        await self.ensure_auth()
        expiry_ms = int((time.time() + days * SECONDS_IN_DAY) * 1000)
        total_bytes = int(total_gb * BYTES_IN_GB)
        client_sub_id = normalize_sub_id(sub_id) or f"user_{uuid.uuid4().hex[:12]}"
        if inbound_ids is None:
            inbound_ids = await self.get_matching_inbound_ids(servers)
            if inbound_ids is None:
                logger.warning(f"PanelAPI create_client: нет matching inbound'ов для email={email}")
                return None
        else:
            inbound_ids = [to_int(i, 0) for i in inbound_ids if to_int(i, 0) > 0]
        if not inbound_ids:
            logger.warning(f"PanelAPI create_client: пустые inbound_ids для email={email}")
            return None
        client: dict[str, Any] = {
            "email": email,
            "enable": True,
            "flow": "",
            "limitIp": max(0, int(limit_ip)),
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "subId": client_sub_id,
            "tgId": max(0, int(tg_id or 0)),
        }
        payload: dict[str, Any] = {"client": client, "inboundIds": inbound_ids}
        url = f"{self.apibase}/panel/api/clients/add"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "POST", url, headers=self._headers(), json=payload
            )
            if status in (200, 201) and data.get("success"):
                client["inboundIds"] = inbound_ids
                self._invalidate_clients_cache()
                logger.info(
                    f"✅ PanelAPI create_client: клиент создан email={email}, sub_id={client_sub_id}"
                )
                returned_sub_id = normalize_sub_id(
                    data.get("client", {}).get("subId") or data.get("subId") or client_sub_id
                )
                client["subId"] = returned_sub_id
                return client
            logger.error(f"Ошибка clients/add для email={email}: {data.get('msg')}")
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка create_client email={email}: {e}")
            return None

    @log_error
    async def create_client_in_inbound(
        self,
        inbound_id: int,
        email: str,
        limit_ip: int,
        total_gb: float,
        expiry_ms: int,
        sub_id: str,
        tg_id: int = 0,
    ) -> bool:
        logger.info(
            f"PanelAPI create_client_in_inbound: email={email}, inbound={inbound_id}, gb={total_gb}"
        )
        await self.ensure_auth()
        inbound = to_int(inbound_id, 0)
        if inbound <= 0 or not email:
            return False
        client: dict[str, Any] = {
            "email": email,
            "enable": True,
            "flow": "",
            "limitIp": max(0, int(limit_ip)),
            "totalGB": int(float(total_gb) * BYTES_IN_GB),
            "expiryTime": max(0, int(expiry_ms)),
            "subId": normalize_sub_id(sub_id) or f"user_{uuid.uuid4().hex[:12]}",
            "tgId": max(0, int(tg_id or 0)),
        }
        payload: dict[str, Any] = {"client": client, "inboundIds": [inbound]}
        url = f"{self.apibase}/panel/api/clients/add"
        status, data, _ = await self._request_json_with_reauth(
            "POST", url, headers=self._headers(), json=payload
        )
        if status in (200, 201) and data.get("success"):
            self._invalidate_clients_cache()
            return True
        logger.error(f"Ошибка добавления клиента в inbound {inbound}: {data.get('msg')}")
        return False

    async def create_or_restore_client_from_backup(self, backup: dict[str, Any]) -> bool:
        await self.ensure_auth()
        email = backup.get("email", "")
        if not email:
            logger.warning("create_or_restore_client_from_backup: пустой email в backup")
            return False

        sub_id = normalize_sub_id(backup.get("subId", "")) or f"restore_{uuid.uuid4().hex[:12]}"
        existing = await self.find_clients_full_by_email_safe(email)
        ok_existing = bool(existing[0] if existing else None)
        if ok_existing:
            return True

        inbound_ids = [
            to_int(i, 0)
            for i in (backup.get("inboundIds") or backup.get("inbound_ids") or [])
            if to_int(i, 0) > 0
        ]
        if not inbound_ids:
            inbound_ids = await self.get_matching_inbound_ids(None)
        if not inbound_ids:
            logger.error(
                f"create_or_restore_client_from_backup: нет matching inbound'ов для email={email}"
            )
            return False

        url = f"{self.apibase}/panel/api/clients/add"
        client: dict[str, Any] = {
            "email": email,
            "enable": bool(backup.get("enable", True)),
            "flow": str(backup.get("flow", "") or ""),
            "limitIp": max(0, int(backup.get("limitIp", 0) or 0)),
            "totalGB": int(backup.get("totalGB", 0) or 0),
            "expiryTime": max(0, int(backup.get("expiryTime", 0) or 0)),
            "subId": sub_id,
            "tgId": max(0, int(backup.get("tgId", 0) or 0)),
        }
        payload: dict[str, Any] = {"client": client, "inboundIds": inbound_ids}
        try:
            status, data, _ = await self._request_json_with_reauth(
                "POST", url, headers=self._headers(), json=payload
            )
            if status in (200, 201) and data.get("success"):
                logger.info(f"✅ create_or_restore_client_from_backup: клиент восстановлен {email}")
                self._invalidate_clients_cache()
                return True
            logger.error(
                f"create_or_restore_client_from_backup: ошибка для {email}: "
                f"status={status}, msg={data.get('msg')}"
            )
            return False
        except Exception as e:  # noqa: BLE001
            logger.error(f"create_or_restore_client_from_backup: исключение для {email}: {e}")
            return False

    @log_error
    async def delete_client(self, base_email: str) -> bool:
        logger.info(f"PanelAPI delete_client: email={base_email}")
        await self.ensure_auth()
        ok, clients = await self.find_clients_full_by_email_safe(base_email)
        if not ok:
            return False
        if not clients:
            direct = await self.get_client_by_email(base_email)
            if direct:
                if not direct.get("email"):
                    direct["email"] = base_email
                clients = [direct]
                logger.info(
                    f"delete_client: клиент найден через прямой lookup: {direct.get('email')}"
                )

        if not clients:
            return True

        success = True
        seen: set[str] = set()
        for client in clients:
            email = str(client.get("email") or "")
            if not email or email in seen:
                continue
            seen.add(email)
            url = f"{self.apibase}/panel/api/clients/del/{self._quote_path(email)}?keepTraffic=0"
            try:
                status, data, _ = await self._request_json_with_reauth(
                    "POST", url, headers=self._headers()
                )
                if status != 200 or not data.get("success"):
                    success = False
                    logger.error(f"Ошибка удаления {email}: {data.get('msg')}")
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка delete_client: {e}")
                success = False
        if success:
            self._invalidate_clients_cache()
        return success

    async def detach_client_from_inbounds(self, email: str, inbound_ids: list[int]) -> bool:
        await self.ensure_auth()
        if not email:
            return False
        clean_ids = [to_int(i, 0) for i in inbound_ids if to_int(i, 0) > 0]
        if not clean_ids:
            return False
        url = f"{self.apibase}/panel/api/clients/{self._quote_path(email)}/detach"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "POST",
                url,
                headers=self._headers(),
                json={"inboundIds": clean_ids},
            )
            if status in (200, 201) and data.get("success"):
                logger.info(f"detach_client: клиент {email} отвязан от inbound'ов {clean_ids}")
                self._invalidate_clients_cache()
                return True
            logger.error(
                f"detach_client: ошибка для {email}: status={status}, "
                f"data={data}, msg={data.get('msg')}"
            )
            return False
        except Exception:
            logger.exception(f"detach_client: ошибка для {email}")
            return False

    @log_error
    async def disconnect_subscription(self, sub_id: str) -> bool:
        logger.info(f"PanelAPI disconnect_subscription: sub_id={sub_id}")
        await self.ensure_auth()
        if not sub_id:
            return False
        clients_ok, clients = await self.find_clients_by_sub_id_safe(sub_id)
        if not clients_ok or not clients:
            logger.warning(f"Клиенты с subId {sub_id} не найдены")
            return False
        success = True
        seen: set[str] = set()
        for c in clients:
            email = str(c.get("email") or "")
            if not email or email in seen:
                continue
            seen.add(email)
            client = await self.get_client_by_email(email) or c.get("clientObj") or c
            if not isinstance(client, dict):
                continue
            client["enable"] = False
            payload = self._client_payload_for_update(client)
            url = f"{self.apibase}/panel/api/clients/update/{self._quote_path(email)}"
            status, data, _ = await self._request_json_with_reauth(
                "POST", url, headers=self._headers(), json=payload
            )
            if status in (200, 201) and data.get("success"):
                logger.info(f"Подписка отключена для {email}")
            else:
                success = False
                logger.error(f"Ошибка отключения {email}: {data.get('msg')}")
        if success:
            self._invalidate_clients_cache()
        return success

    @log_error
    async def ensure_auth(self) -> None:
        if not self.logged_in:
            await self.login()

    async def extend_client_expiry(self, base_email: str, add_days: int) -> bool:
        if add_days <= 0:
            logger.warning(f"extend_client_expiry: некорректное количество дней ({add_days})")
            return False
        emails = await self._collect_unique_client_emails(base_email)
        if not emails:
            logger.warning(f"extend_client_expiry: нет email для продления {base_email}")
            return False
        url = f"{self.apibase}/panel/api/clients/bulkAdjust"
        payload: dict[str, Any] = {"emails": emails, "addDays": add_days}
        status, data, _ = await self._request_json_with_reauth(
            "POST", url, headers=self._headers(), json=payload
        )
        if status in (200, 201) and data.get("success"):
            adjusted = 0
            skipped: list[str] = []
            obj = data.get("obj") or {}
            if isinstance(obj, dict):
                adjusted = to_int(obj.get("adjusted", 0), 0)
                skipped = obj.get("skipped", [])
            logger.info(
                f"extend_client_expiry: успешно продлено {adjusted} клиентов "
                f"на {add_days} дней, пропущено {len(skipped)}: {skipped}"
            )
            if adjusted > 0:
                self._invalidate_clients_cache()
            return adjusted > 0
        else:
            logger.error(
                f"extend_client_expiry: ошибка bulkAdjust для {emails}: "
                f"status={status}, data={data.get('msg')}"
            )
            return False

    async def extend_client_expiry_by_user_id(self, user_id: int, add_days: int) -> bool:
        if add_days <= 0:
            logger.warning(
                f"extend_client_expiry_by_user_id: некорректное кол-во дней ({add_days})"
            )
            return False
        base_email = build_base_email(user_id)
        return await self.extend_client_expiry(base_email, add_days)

    async def find_clients_by_base_email_safe(
        self, base_email: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        clients_data = await self.get_clients()
        if not clients_data or not clients_data.get("success"):
            return False, []
        result: list[dict[str, Any]] = []
        for row in self._client_rows_from_response(clients_data):
            email = str(row.get("email") or "")
            if self._is_base_email(email, base_email):
                result.append(self._normalize_client_row(row))
        return True, result

    async def find_clients_by_sub_id_safe(self, sub_id: str) -> tuple[bool, list[dict[str, Any]]]:
        if not sub_id:
            return False, []
        clients_data = await self.get_clients()
        if not clients_data or not clients_data.get("success"):
            return False, []
        result: list[dict[str, Any]] = []
        for row in self._client_rows_from_response(clients_data):
            client_sub_id = str(row.get("subId", "") or "")
            if client_sub_id == sub_id:
                result.append(self._normalize_client_row(row))
        return True, result

    async def find_clients_full_by_email(self, base_email: str) -> list[dict[str, Any]]:
        ok, clients = await self.find_clients_full_by_email_safe(base_email)
        return clients if ok else []

    async def find_clients_full_by_email_safe(
        self, base_email: str
    ) -> tuple[bool, list[dict[str, Any]]]:
        ok, result = await self.find_clients_by_base_email_safe(base_email)
        if not ok:
            return False, []
        logger.info(f"Найдено {len(result)} клиентов по base_email='{base_email}'")
        return True, result

    async def get_all_clients(self) -> list[dict[str, Any]] | None:
        clients_data = await self.get_clients()
        if not clients_data or not clients_data.get("success"):
            return None
        return self._client_rows_from_response(clients_data)

    @log_error
    async def get_client_by_email(self, email: str) -> dict[str, Any] | None:
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/clients/get/{self._quote_path(email)}"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "GET", url, headers=self._headers()
            )
            if status == 200 and data.get("success"):
                obj = data.get("obj") or {}
                if isinstance(obj, dict) and isinstance(obj.get("client"), dict):
                    client = dict(obj["client"])
                    client["inboundIds"] = obj.get("inboundIds") or client.get("inboundIds", [])
                    return client
                return obj if isinstance(obj, dict) else None
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка get_client_by_email: {e}")
            return None

    async def get_client_stats_safe(self, base_email: str) -> tuple[bool, list[dict[str, Any]]]:
        return await self.find_clients_by_base_email_safe(base_email)

    @log_error
    async def get_clients(self) -> dict[str, Any] | None:
        now = time.monotonic()
        if (
            self._clients_cache is not None
            and (now - self._clients_cache_ts) < self._clients_cache_ttl
        ):
            return self._clients_cache
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/clients/list"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "GET", url, headers=self._headers()
            )
            if status == 200 and data.get("success"):
                self._clients_cache = data
                self._clients_cache_ts = now
                return data
            logger.error(f"Ошибка clients/list: {data.get('msg')}")
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка get_clients: {e}")
            return None

    @log_error
    async def get_inbound_id_by_name(self, tag_name: str) -> int | None:
        inbounds = await self.get_inbounds()
        if not inbounds or not inbounds.get("success"):
            return None
        obj = inbounds.get("obj", [])
        if isinstance(obj, dict):
            obj = obj.get("items") or obj.get("data") or obj.get("inbounds") or []
        for inb in obj:
            inb_tag = str(inb.get("tag") or "")
            if inb_tag == tag_name:
                return to_int(inb.get("id"), 0)
        return None

    @log_error
    async def get_inbounds(self) -> dict[str, Any] | None:
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/inbounds/list"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "GET", url, headers=self._headers()
            )
            if status == 200 and data.get("success"):
                obj = data.get("obj")
                if isinstance(obj, dict):
                    items = obj.get("items") or obj.get("data") or obj.get("inbounds")
                    if isinstance(items, list):
                        data["obj"] = items
                return data
            logger.error(f"Ошибка getInbounds: {data.get('msg')}")
            return None
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка get_inbounds: {e}")
            return None

    async def get_matching_inbound_ids(self, servers: list[str] | None) -> list[int] | None:
        inbounds = await self.get_inbounds()
        if not inbounds or not inbounds.get("success"):
            return None
        obj = inbounds.get("obj", [])
        if isinstance(obj, dict):
            obj = obj.get("items") or obj.get("data") or obj.get("inbounds") or []
        enabled = _filter_inbounds_for_servers_list(obj, servers)
        return [to_int(inb.get("id"), 0) for inb in enabled if to_int(inb.get("id"), 0) > 0]

    @log_error
    async def get_nodes(self, sanitize: bool = True) -> list[dict[str, Any]]:
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/nodes/list"
        status, data, _ = await self._request_json_with_reauth("GET", url, headers=self._headers())
        if status == 200 and data.get("success"):
            obj = data.get("obj", [])
            if isinstance(obj, dict):
                obj = obj.get("nodes") or obj.get("data") or obj.get("list") or []
            if isinstance(obj, list):
                result: list[dict[str, Any]] = []
                for node in obj:
                    if not isinstance(node, dict):
                        continue
                    if sanitize:
                        sanitized_node = {
                            k: v
                            for k, v in node.items()
                            if k
                            not in (
                                "address",
                                "port",
                                "latencyMs",
                                "apiToken",
                                "pinnedCertSha256",
                            )
                        }
                    else:
                        sanitized_node = dict(node)
                    mapped: dict[str, Any] = {}
                    for k, v in sanitized_node.items():
                        if k == "uptimeSecs":
                            mapped["uptime"] = v
                        elif k == "panelVersion":
                            mapped["panel_version"] = v
                        elif k == "xrayVersion":
                            mapped["xray_version"] = v
                        else:
                            mapped[k] = v
                    result.append(mapped)
                return result
        logger.error(
            f"get_nodes: status={status}, success={data.get('success')}, obj_type={type(data.get('obj')).__name__}"
        )
        return []

    @log_error
    async def get_panel_info(self) -> dict[str, Any]:
        server_status = await self.get_server_status()
        xray_obj = server_status.get("xray", {}) if isinstance(server_status, dict) else {}
        xray_version = ""
        if isinstance(xray_obj, dict):
            xray_version = str(xray_obj.get("version") or "")
        elif xray_obj:
            xray_version = str(xray_obj)
        return {
            "panel_version": server_status.get("panelVersion")
            or server_status.get("panel_version")
            or "",
            "xray_version": xray_version,
            "panel_base": self.apibase,
        }

    @log_error
    async def get_server_status(self, sanitize: bool = True) -> dict[str, Any]:
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/server/status"
        status, data, _ = await self._request_json_with_reauth("GET", url, headers=self._headers())
        if status == 200 and data.get("success"):
            obj = data.get("obj", {})
            if isinstance(obj, dict):
                if sanitize:
                    sanitized = {
                        k: v
                        for k, v in obj.items()
                        if k not in ("ip", "port", "latencyMs", "ping", "address")
                    }
                    return sanitized
                return dict(obj)
        return {}

    @log_error
    async def get_version(self) -> str | None:
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/version"
        status, data, _ = await self._request_json_with_reauth("GET", url, headers=self._headers())
        if status == 200 and data.get("success"):
            obj = data.get("obj")
            if isinstance(obj, dict):
                return str(obj.get("version") or obj.get("panel_version") or "")
            return str(obj or "")
        return None

    @log_error
    async def get_xray_version(self) -> str | None:
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/xray/version"
        status, data, _ = await self._request_json_with_reauth("GET", url, headers=self._headers())
        if status == 200 and data.get("success"):
            obj = data.get("obj")
            if isinstance(obj, dict):
                return str(obj.get("version") or obj.get("xray_version") or "")
            return str(obj or "")
        return None

    @log_error
    async def login(self) -> None:
        async with self.lock:
            if not self.session:
                logger.error("login: сессия не инициализирована")
                return
            if self.token:
                self.logged_in = True
                logger.info("Используется PANEL_TOKEN")
                return
            if not self.username or not self.password:
                self.logged_in = False
                logger.warning("login: PANEL_LOGIN или PANEL_PASSWORD не настроены")
                return
            try:
                async with self.session.post(
                    f"{self.apibase}/login",
                    json={"username": self.username, "password": self.password},
                ) as resp:
                    raw_text = await resp.text()
                    try:
                        data = json.loads(raw_text) if raw_text else {}
                    except json.JSONDecodeError:
                        data = {}
                    if resp.status == 200 and data.get("success"):
                        self.logged_in = True
                        logger.info("Авторизация в панели успешна")
                    else:
                        self.logged_in = False
                        logger.error(
                            f"Ошибка авторизации: status={resp.status}, msg={data.get('msg')}, body={raw_text[:500]}"
                        )
            except Exception as e:  # noqa: BLE001
                self.logged_in = False
                logger.error(f"Ошибка авторизации: {type(e).__name__}: {e}")

    async def reset_client_traffic(self, base_email: str) -> bool:
        await self.ensure_auth()
        emails = await self._collect_unique_client_emails(base_email)
        if not emails:
            logger.warning(f"reset_client_traffic: клиенты не найдены для {base_email}")
            return False

        bulk_url = f"{self.apibase}/panel/api/clients/bulkResetTraffic"
        bulk_payload: dict[str, Any] = {"emails": emails}
        status, data, _ = await self._request_json_with_reauth(
            "POST", bulk_url, headers=self._headers(), json=bulk_payload
        )
        if status in (200, 201) and data.get("success"):
            logger.info(f"reset_client_traffic: успешно сброшен трафик для {len(emails)} клиентов")
            self._invalidate_clients_cache()
            return True

        logger.warning(
            f"reset_client_traffic: bulkResetTraffic неуспешен для {emails}: "
            f"status={status}, msg={data.get('msg')}"
        )

        success = True
        for email in emails:
            single_url = f"{self.apibase}/panel/api/clients/resetTraffic/{self._quote_path(email)}"
            st, single_data, _ = await self._request_json_with_reauth(
                "POST", single_url, headers=self._headers()
            )
            if st not in (200, 201) or not single_data.get("success"):
                success = False
                logger.error(
                    f"reset_client_traffic: ошибка resetTraffic для {email}: "
                    f"status={st}, msg={single_data.get('msg')}"
                )
        return success

    @log_error
    async def start(self) -> None:
        try:
            connector = aiohttp.TCPConnector(ssl=self.verifyssl)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=Config.PANEL_HTTP_TIMEOUT_SEC),
                cookie_jar=aiohttp.CookieJar(),
            )
            if not self.token:
                await self.login()
            else:
                logger.info("Используется PANEL_TOKEN")
        except Exception as e:
            logger.critical(f"Ошибка запуска PanelAPI: {e}")
            raise


async def _validate_admin_target_user(uid: int, event: Message, lang: str) -> bool:
    """Проверяет, что пользователь с uid (telegram_id) существует и не является админом."""
    if not uid or uid <= 0:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return False
    if await is_admin_user(uid):
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.cannot_modify_admin"))
        return False
    existing = await db.get_user_by_any_id(uid)
    if not existing:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found"))
        return False
    return True


async def _validate_admin_target_by_user_id(internal_uid: int, event: Message, lang: str) -> bool:
    """Проверяет, что пользователь с user_id (внутренний ID) существует и не является админом."""
    if not internal_uid or internal_uid <= 0:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return False
    existing = await db.get_user_by_any_id(internal_uid)
    if not existing:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found"))
        return False
    tg_id = existing.get("telegram_id", 0)
    if tg_id and await is_admin_user(tg_id):
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.cannot_modify_admin"))
        return False
    return True


async def _resolve_target_user(
    query_str: str, event: Message, lang: str
) -> tuple[int | None, dict[str, Any] | None]:
    """Умный поиск: сначала по user_id, потом по telegram_id. Возвращает (internal_user_id, user_data)."""
    query_str = query_str.strip()
    if not query_str.isdigit():
        try:
            await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ошибка отправки ответа (invalid_user_id): {e}")
        return None, None

    query_int = int(query_str)

    results = await db.smart_lookup(query_int)
    if len(results) == 1:
        u = results[0]
        tg_id = u.get("telegram_id", 0)
        if tg_id and await is_admin_user(tg_id):
            try:
                await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.cannot_modify_admin"))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Ошибка отправки ответа (cannot_modify_admin): {e}")
            return None, None
        return u.get("user_id"), u

    if not results:
        results = await db.search_users(query_str)
        if not results:
            try:
                await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found"))
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Ошибка отправки ответа (user_not_found): {e}")
            return None, None

    if len(results) > 1:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.search_multiple_found", count=len(results))
        for i, u in enumerate(results[:5], 1):
            match_type = u.pop("_match_type", "text") if "_match_type" in u else "text"
            match_label = translate(Config.DEFAULT_LANGUAGE, f"texts.search_match_{match_type}")
            text += f"\n\n{i}. {match_label}\n"
            text += format_user_raw(u)
        try:
            await _send_markdown_answer(event, text)
        except Exception:
            logger.exception("Ошибка отправки результата поиска (resolve)")
        return None, None

    u = results[0]
    tg_id = u.get("telegram_id", 0)
    if tg_id and await is_admin_user(tg_id):
        try:
            await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.cannot_modify_admin"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ошибка отправки ответа (cannot_modify_admin 2): {e}")
        return None, None
    return u.get("user_id"), u


class BanUserState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_ban_reason = State()


class UnbanUserState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_unban_reason = State()


class BroadcastState(StatesGroup):
    waiting_for_broadcast_type = State()
    waiting_for_message = State()


class TrustScoreState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()


class CustomTariffState(StatesGroup):
    waiting_for_gb = State()
    waiting_for_ip = State()
    waiting_for_days = State()
    waiting_for_locations = State()
    waiting_for_confirm = State()


class DeleteSubscriptionState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_confirm = State()


class AddTrafficState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_gb = State()


class ChangeUsernameState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_new_username = State()


class ChangePasswordState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_new_password = State()


class PartnerApplicationState(StatesGroup):
    waiting_for_followers = State()
    waiting_for_social_links = State()
    waiting_for_nickname = State()
    waiting_for_period = State()
    waiting_for_bonus_type = State()
    waiting_for_bonus_value = State()
    waiting_for_pd_consent = State()


class PartnerWithdrawalState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_phone = State()
    waiting_for_fio = State()
    waiting_for_bank = State()


# --- Глобальные объекты ---
_bot_token: str = Config.BOT_TOKEN if is_valid_bot_token_format(Config.BOT_TOKEN) else ""
if not _bot_token:
    logger.critical("BOT_TOKEN не настроен или некорректен. Бот не будет запущен.")
    sys.exit(1)

bot: Bot | None = Bot(
    token=_bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)
dp.callback_query.middleware(CallbackAnswerMiddleware())

db = Database(Config.DATA_FILE)
json_db = JSONStorage(Config.DATA_AWAIT)
panel = PanelAPI()
BOT_USERNAME = ""


def set_bot_username(username: str) -> None:
    global BOT_USERNAME
    BOT_USERNAME = username or ""


# --- Клавиатуры и вспомогательные функции ---
def support_keyboard(include_main: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if Config.SUPPORT_URL:
        rows.append(
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.support"),
                    "url": Config.SUPPORT_URL,
                }
            ]
        )
    if include_main:
        rows.append(
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ]
        )
    if not rows:
        rows = [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ]
        ]
    return kb(rows)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ]
        ]
    )


def cancel_only_keyboard() -> InlineKeyboardMarkup:
    return kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                    "callback_data": "cancel",
                }
            ]
        ]
    )


def _build_social_links(language: str) -> list[dict[str, str]]:
    social = []
    if Config.YOUTUBE_URL:
        social.append({"text": "YouTube", "url": Config.YOUTUBE_URL})
    if Config.TELEGRAM_URL:
        social.append({"text": "Telegram", "url": Config.TELEGRAM_URL})
    if Config.TIKTOK_URL:
        social.append({"text": "TikTok", "url": Config.TIKTOK_URL})
    return social if social else []


def _build_legal_links(language: str) -> list[dict[str, str]]:
    legal = []
    if Config.PUBLIC_OFFER_URL:
        legal.append(
            {
                "text": translate(language, "buttons.public_offer"),
                "url": Config.PUBLIC_OFFER_URL,
            }
        )
    if Config.PRIVACY_POLICY_URL:
        legal.append(
            {
                "text": translate(language, "buttons.privacy_policy"),
                "url": Config.PRIVACY_POLICY_URL,
            }
        )
    return legal if legal else []


def _build_qna_tos_links(language: str) -> list[dict[str, str]]:
    qna_tos = []
    if Config.QNA_URL:
        qna_tos.append({"text": translate(language, "buttons.qna"), "url": Config.QNA_URL})
    if Config.TERMS_OF_SERVICE_URL:
        qna_tos.append(
            {
                "text": translate(language, "buttons.terms_of_service"),
                "url": Config.TERMS_OF_SERVICE_URL,
            }
        )
    return qna_tos if qna_tos else []


def _build_admin_buttons(language: str) -> list[list[dict[str, str]]]:
    return [
        [
            {
                "text": translate(language, "buttons.pending_payments"),
                "callback_data": "pay_await",
            }
        ],
        [
            {
                "text": translate(language, "buttons.partner_operations"),
                "callback_data": "partner_operations",
            }
        ],
        [
            {
                "text": translate(language, "buttons.debug_tools"),
                "callback_data": "debug_menu",
            }
        ],
    ]


def build_main_keyboard(
    is_admin: bool,
    has_active_subscription: bool,
    language: str = Config.DEFAULT_LANGUAGE,
    *,
    is_partner: bool = False,
) -> list[list[dict[str, str]]]:
    rows = []

    if is_admin or not has_active_subscription or is_partner:
        rows.append([{"text": translate(language, "buttons.buy"), "callback_data": "buy"}])

    rows.append(
        [
            {
                "text": translate(language, "buttons.my_subscription"),
                "callback_data": "mysub",
            }
        ]
    )

    if not is_admin and not is_partner:
        rows.append(
            [
                {
                    "text": translate(language, "buttons.become_partner"),
                    "callback_data": "become_partner",
                }
            ]
        )

    if is_partner:
        rows.append(
            [
                {
                    "text": translate(language, "buttons.partner_menu"),
                    "callback_data": "partner_dashboard",
                },
            ]
        )

    if is_admin:
        rows.extend(_build_admin_buttons(language))

    social = _build_social_links(language)
    if social:
        rows.append(social)

    legal = _build_legal_links(language)
    if legal:
        rows.append(legal)

    qna_tos = _build_qna_tos_links(language)
    if qna_tos:
        rows.append(qna_tos)

    if Config.SITE_URL:
        rows.append([{"text": translate(language, "buttons.site"), "url": Config.SITE_URL}])
    if Config.SUPPORT_URL:
        rows.append(
            [
                {
                    "text": translate(language, "buttons.support"),
                    "url": Config.SUPPORT_URL,
                }
            ]
        )

    lang_name = get_language_display_name(language)
    rows.append([{"text": lang_name, "callback_data": "change_language"}])
    return rows


def active_subscription_keyboard() -> InlineKeyboardMarkup:
    return kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.my_subscription"),
                    "callback_data": "mysub",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ],
        ]
    )


def inactive_subscription_actions_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.buy"),
                "callback_data": "buy",
            }
        ]
    ]
    if Config.SUPPORT_URL:
        rows.append(
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.support"),
                    "url": Config.SUPPORT_URL,
                }
            ]
        )
    rows.append(
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                "callback_data": "start",
            }
        ]
    )
    return kb(rows)


def build_language_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [{"text": get_language_display_name(code), "callback_data": f"lang:{code}"}]
        for code in get_available_languages()
    ]
    rows.append(
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "start",
            }
        ]
    )
    return kb(rows)


def build_setup_keyboard(
    language: str = Config.DEFAULT_LANGUAGE,
) -> InlineKeyboardMarkup:
    return kb(
        [
            [
                {
                    "text": translate(language, "buttons.client_app_setup"),
                    "callback_data": "client_setup",
                }
            ],
            [
                {
                    "text": translate(language, "buttons.main"),
                    "callback_data": "start",
                }
            ],
        ]
    )


def _build_price_line(plan: dict[str, Any], lang: str) -> str:
    price = plan.get("price_rub", 0)
    duration = int(plan.get("duration_days", 30))
    if price == 0:
        return translate(lang, "texts.price_free_for_days", days=format_duration(duration, lang))
    if duration == 30:
        return translate(lang, "texts.price_monthly", price=price)
    return translate(lang, "texts.price_fixed_days", price=price, duration=duration)


def build_tariffs_text(
    plans: list[dict[str, Any]] | None = None, lang: str = Config.DEFAULT_LANGUAGE
) -> str:
    plans = plans if plans is not None else get_all_active()
    if not plans:
        text = translate(lang, "texts.tariffs_unavailable")
        if custom_tariff_enabled():
            text += "\n\n" + build_custom_tariff_info_block(lang)
        return text
    text = translate(lang, "texts.tariffs_title")
    for idx, plan in enumerate(plans, 1):
        price_line = _build_price_line(plan, lang)
        text += translate(
            lang,
            "texts.plan_block",
            idx=idx,
            name=plan.get("name", plan.get("id")),
            price_line=price_line,
            ip_limit=plan.get("ip_limit", 0),
            traffic=format_traffic(plan.get("traffic_gb", 0), lang),
        )
        servers = get_plan_servers(plan)
        if servers:
            text += translate(
                lang,
                "texts.plan_block_servers",
                servers=format_servers(servers),
            )
        text += "\n"
    if custom_tariff_enabled():
        text += build_custom_tariff_info_block(lang) + "\n\n"
    text += translate(lang, "texts.tariffs_footer")
    return text


def build_fixed_tariffs_text(
    plans: list[dict[str, Any]] | None = None, lang: str = Config.DEFAULT_LANGUAGE
) -> str:
    plans = plans if plans is not None else get_all_active()
    if not plans:
        return translate(lang, "texts.tariffs_unavailable")
    text = translate(lang, "texts.buy_fixed_title")
    for idx, plan in enumerate(plans, 1):
        price_line = _build_price_line(plan, lang)
        text += translate(
            lang,
            "texts.plan_block",
            idx=idx,
            name=plan.get("name", plan.get("id")),
            price_line=price_line,
            ip_limit=plan.get("ip_limit", 0),
            traffic=format_traffic(plan.get("traffic_gb", 0), lang),
        )
        servers = get_plan_servers(plan)
        if servers:
            text += translate(
                lang,
                "texts.plan_block_servers",
                servers=format_servers(servers),
            )
        text += "\n"
    text += translate(lang, "texts.tariffs_footer")
    return text


def build_buy_text(
    plans: list[dict[str, Any]] | None = None,
    *,
    for_admin: bool = False,
    lang: str = Config.DEFAULT_LANGUAGE,
) -> str:
    plans = plans if plans is not None else get_all_active()
    if not plans:
        text = translate(lang, "texts.buy_unavailable")
        if custom_tariff_enabled():
            text += translate(lang, "texts.buy_custom_button_hint")
        return text
    text = translate(lang, "texts.buy_title")
    for idx, plan in enumerate(plans, 1):
        price_line = _build_price_line(plan, lang)
        servers = get_plan_servers(plan)
        servers_text = f" - {format_servers(servers)}" if servers else ""
        text += translate(
            lang,
            "texts.buy_plan_option",
            idx=idx,
            name=plan.get("name", plan.get("id")),
            price_line=price_line,
            servers_text=servers_text,
        )
    if custom_tariff_enabled():
        text += translate(lang, "texts.buy_custom_button_hint")
    if for_admin:
        text += translate(lang, "texts.buy_admin_custom_hint")
    else:
        text += translate(lang, "texts.buy_user_payment_hint")
    return text


def build_pending_payment_text(payment: dict[str, Any], tg_id: int = 0) -> str:
    pid = payment.get("payment_id", "")
    uid = payment.get("user_id", 0)
    plan_id = payment.get("plan_id", "")
    amount = payment.get("amount", 0)
    plan_type = str(payment.get("plan_type", "catalog"))
    plan_name = str(payment.get("plan_name") or "").strip()
    method = (
        "ЮMoney"
        if str(payment.get("payment_method", "p2p")).lower() == "yoomoney"
        else "P2P на карту"
    )
    details = ""
    if plan_type == "custom":
        plan, _ = build_custom_plan_from_payment(payment)
        if plan:
            plan_name = plan_name or plan.get(
                "name",
                translate(Config.DEFAULT_LANGUAGE, "texts.custom_plan_short_name"),
            )
            details = translate(
                Config.DEFAULT_LANGUAGE,
                "texts.pending_payment_custom_details",
                traffic=format_traffic(plan.get("traffic_gb", 0)),
                ip_limit=plan.get("ip_limit", 0),
                duration=format_duration(int(plan.get("duration_days", 0))),
                servers=format_servers(plan.get("servers")),
            )
        else:
            plan_name = plan_name or translate(
                Config.DEFAULT_LANGUAGE, "texts.custom_plan_short_name"
            )
    else:
        plan, _ = get_purchasable_catalog_plan(str(plan_id))
        if plan:
            plan_name = plan_name or plan.get("name", plan_id)
            details = translate(
                Config.DEFAULT_LANGUAGE,
                "texts.pending_payment_catalog_locations",
                servers=format_servers(plan.get("servers")),
            )
        elif not plan_name:
            plan_name = str(plan_id)
    tg_id_str = f" (TG: {tg_id})" if tg_id > 0 else ""
    return translate(
        Config.DEFAULT_LANGUAGE,
        "texts.pending_payment_text",
        payment_id=pid,
        user_id=uid,
        tg_id=tg_id_str,
        plan_name=plan_name,
        details=details,
        payment_method=method,
        amount=amount,
        timestamp=format_payment_time(payment.get("timestamp")),
    )


def build_pending_payment_keyboard(payment_id: str) -> InlineKeyboardMarkup:
    return kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.confirm_payment"),
                    "callback_data": f"pay_await_accept:{payment_id}",
                },
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.reject_payment"),
                    "callback_data": f"pay_await_reject:{payment_id}",
                },
            ]
        ]
    )


def build_subscription_cleanup_message(
    reason: str,
    trust_before: int | None = None,
    trust_after: int | None = None,
    trust_delta: int = 0,
    lang: str = Config.DEFAULT_LANGUAGE,
) -> str:
    if trust_before is not None and trust_after is not None:
        trust_line = build_trust_change_line(trust_delta, trust_before, trust_after)
    elif reason == "traffic_exhausted":
        trust_line = translate(
            lang,
            "texts.trust_penalty_applied",
            penalty=TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED,
        )
    else:
        trust_line = translate(lang, "texts.trust_change_short_none")
    if reason == "traffic_exhausted":
        return translate(
            lang,
            "texts.subscription_cleanup_traffic_exhausted",
            trust_line=trust_line,
        )
    if reason == "expired":
        return translate(
            lang,
            "texts.subscription_cleanup_expired",
            trust_line=trust_line,
        )
    return translate(lang, "texts.subscription_cleanup_inactive", trust_line=trust_line)


def custom_locations_keyboard(selected_servers: Any) -> InlineKeyboardMarkup:
    selected = set(normalize_servers(selected_servers))
    rows = []
    for loc in get_custom_locations():
        code = str(loc.get("code") or "")
        if not code:
            continue
        mark = "✓" if code in selected else "□"
        price = format_number(parse_float_value(loc.get("price_per_day_rub"), 0.0))
        rows.append(
            [
                {
                    "text": translate(
                        Config.DEFAULT_LANGUAGE,
                        "buttons.custom_location_option",
                        mark=mark,
                        label=loc.get("label", code),
                        price=price,
                    ),
                    "callback_data": f"custom:loc:{code}",
                }
            ]
        )
    rows.append(
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.done"),
                "callback_data": "custom:locations_done",
            }
        ]
    )
    rows.append(
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ]
    )
    return kb(rows)


def build_custom_locations_text(selected_servers: Any) -> str:
    selected = normalize_servers(selected_servers)
    selected_text = (
        format_servers(selected)
        if selected
        else translate(Config.DEFAULT_LANGUAGE, "texts.not_selected")
    )
    return translate(
        Config.DEFAULT_LANGUAGE,
        "texts.custom_tariff_locations_text",
        selected_text=selected_text,
    )


# --- Вспомогательные асинхронные функции ---
async def notify_admins(text: str, reply_markup: InlineKeyboardMarkup | None = None):
    for admin_id in Config.ADMIN_USER_IDS:
        await safe_send_message(bot, admin_id, text, reply_markup)


async def notify_user(
    user_id: int, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> bool:
    return await safe_send_message(bot, user_id, text, reply_markup)


def get_event_user_id(event: Any) -> int | None:
    user = getattr(event, "from_user", None)
    return getattr(user, "id", None)


async def get_user_language(user_id: int) -> str:
    if await is_admin_user(user_id):
        return Config.DEFAULT_LANGUAGE
    user = await db.get_user_by_any_id(user_id)
    lang = str(user.get("language", "") if user else "").strip().lower()
    return lang if lang in LANGUAGES else Config.DEFAULT_LANGUAGE


async def get_lang(event: Any) -> str:
    user_id = get_event_user_id(event)
    if not user_id:
        return Config.DEFAULT_LANGUAGE
    return await get_user_language(user_id)


async def prompt_language_selection(event: Message | CallbackQuery) -> None:
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.language_prompt"),
        reply_markup=build_language_keyboard(),
        delete_origin=True,
    )


async def deny_admin_only(event: Message | CallbackQuery) -> None:
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.admin_only_command"),
        reply_markup=main_menu_keyboard(),
        delete_origin=True,
    )


async def ensure_admin_access(event: Any, *, silent: bool = False) -> bool:
    user_id = get_event_user_id(event) or 0
    if await is_admin_user(user_id):
        return True
    if not silent:
        await deny_admin_only(event)
    return False


async def ensure_custom_tariff_access(
    event: Message | CallbackQuery, state: FSMContext | None = None
) -> bool:
    if custom_tariff_enabled():
        return True
    if state:
        await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_unavailable"),
            show_alert=True,
        )
    elif isinstance(event, Message):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_unavailable"),
            reply_markup=main_menu_keyboard(),
        )
    return False


async def show_custom_locations_picker(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    selected = normalize_servers(data.get("custom_servers"))
    text = build_custom_locations_text(selected)
    markup = custom_locations_keyboard(selected)
    if isinstance(event, CallbackQuery) and event.message:
        try:
            await event.message.edit_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
            await event.answer()
            return
        except Exception:  # noqa: BLE001, S110
            pass
    await smart_answer(event, text, reply_markup=markup, delete_origin=True)


async def show_custom_summary(event: Message | CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    traffic = to_int(data.get("custom_traffic_gb"), 0)
    ip = to_int(data.get("custom_ip_limit"), 0)
    days = to_int(data.get("custom_duration_days"), 0)
    servers = normalize_servers(data.get("custom_servers"))
    if not is_valid_custom_limits(traffic, ip, days) or not is_valid_custom_servers(servers):
        await state.clear()
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_build_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    base_total = int(round(calculate_custom_tariff_total(traffic, ip, days, servers)))  # noqa: RUF046
    trust = await db.get_trust_score(get_event_user_id(event) or 0)
    final_price, disc = apply_trust_discount(float(base_total), trust)
    final_price_int = max(0, int(round(final_price)))  # noqa: RUF046
    plan_name = build_custom_plan_name(traffic, ip, days, servers)
    loc_total = sum(get_location_price_per_day(s) for s in servers)
    await state.update_data(
        custom_base_amount=base_total,
        custom_final_amount=final_price_int,
        custom_discount_percent=disc,
        custom_plan_name=plan_name,
    )
    await state.set_state(CustomTariffState.waiting_for_confirm)

    ip_part = "IP × D"
    if abs(Config.CUSTOM_TARIFF_IP_DAY_COEF - 1.0) > 1e-9:
        ip_part = f"IP × D × {format_number(Config.CUSTOM_TARIFF_IP_DAY_COEF)}"
    formula = f"total = {format_number(Config.CUSTOM_TARIFF_BASE_PRICE)} + GB × {format_number(Config.CUSTOM_TARIFF_GB_COEF)} + {ip_part} + LOC × D"
    if disc > 0:
        price_line = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.custom_tariff_summary_discount",
            discount_percent=disc,
            final_price=final_price_int,
        )
    else:
        price_line = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.custom_tariff_summary_total",
            final_price=final_price_int,
        )

    uid = get_event_user_id(event) or 0
    next_step = translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_user_payment_hint")
    markup = kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.continue"),
                    "callback_data": f"custom:show_offer:{uid}",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                    "callback_data": "cancel",
                }
            ],
        ]
    )

    text = translate(
        Config.DEFAULT_LANGUAGE,
        "texts.custom_tariff_summary",
        traffic_gb=traffic,
        ip_limit=ip,
        duration=format_duration(days),
        servers=format_servers(servers),
        location_daily_total=format_number(loc_total),
        formula=formula,
        base_total=base_total,
        price_line=price_line,
        next_step_text=next_step,
    )
    await smart_answer(event, text, reply_markup=markup, delete_origin=True)


async def show_offer_agreement(
    event: CallbackQuery,
    *,
    continue_callback_data: str,
    lang: str = Config.DEFAULT_LANGUAGE,
) -> None:
    user_id = get_event_user_id(event) or 0
    if not await is_admin_user(user_id):  # noqa: SIM102
        if await block_if_pending_payment(event, user_id):
            return
    text = translate(lang, "texts.offer_agreement")
    keyboard = []
    if Config.PUBLIC_OFFER_URL:
        keyboard.append(
            [
                {
                    "text": translate(lang, "buttons.public_offer"),
                    "url": Config.PUBLIC_OFFER_URL,
                }
            ]
        )
    target = continue_callback_data.replace("show_payment:", "choose_payment_method:").replace(
        "custom:show_payment:", "custom:choose_payment_method:"
    )
    keyboard.append(
        [
            {
                "text": translate(lang, "buttons.cancel"),
                "callback_data": "cancel",
            },
            {
                "text": translate(lang, "buttons.i_agree"),
                "callback_data": target,
            },
        ]
    )
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


async def get_subscription_state(user_id: int) -> dict[str, Any]:
    user = await db.get_user_by_any_id(user_id)
    if not user:
        return {"status": "no_user", "panel_available": True}
    internal_uid = user.get("user_id", user_id)
    sub_id = normalize_sub_id(user.get("vpn_url"))
    if not sub_id:
        return {"status": "no_subscription", "panel_available": True}
    base_email = get_user_panel_email(internal_uid, user)
    panel_ok, clients = await panel.get_client_stats_safe(base_email)
    if not panel_ok:
        return {
            "status": "panel_unavailable",
            "panel_available": False,
            "sub_id": sub_id,
        }
    if not clients:
        return {"status": "missing_on_panel", "panel_available": True, "sub_id": sub_id}
    now_ms = int(time.time() * 1000)
    expiry_times = [to_int(c.get("expiryTime"), 0) for c in clients]
    positive = [x for x in expiry_times if x > 0]
    max_expiry = max(positive) if positive else 0

    if max_expiry <= 0:
        expiry_str = str(user.get("expiry_sub_datatime") or "").strip()
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
                max_expiry = int(expiry_dt.timestamp() * 1000)
            except Exception:  # noqa: BLE001, S110
                pass

    used_bytes = sum(
        max(0, to_int(c.get("up"), 0)) + max(0, to_int(c.get("down"), 0)) for c in clients
    )
    traffic_gb = max(0.0, to_float(user.get("traffic_gb"), 0.0))
    extra_gb = max(0, to_int(user.get("extra_sub_gb"), 0))
    total_traffic_gb = traffic_gb + extra_gb
    traffic_bytes = int(total_traffic_gb * BYTES_IN_GB)
    traffic_exhausted = traffic_bytes > 0 and used_bytes >= traffic_bytes
    expired = bool(max_expiry and max_expiry <= now_ms)
    status = "expired" if expired else ("traffic_exhausted" if traffic_exhausted else "active")
    return {
        "status": status,
        "panel_available": True,
        "sub_id": sub_id,
        "clients": clients,
        "max_expiry": max_expiry,
        "used_bytes": used_bytes,
        "used_gb": used_bytes / BYTES_IN_GB,
        "traffic_gb": total_traffic_gb,
        "traffic_bytes": traffic_bytes,
    }


async def cleanup_subscription(
    user_id: int,
    reason: str,
    *,
    notify_user_about_cleanup: bool,
    lang: str = Config.DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    result = {
        "success": False,
        "trust_before": None,
        "trust_after": None,
        "trust_delta": 0,
    }

    if not validate_user_id(user_id):
        logger.warning(f"cleanup_subscription: некорректный user_id {user_id}")
        return result

    user_data = await db.get_user_by_any_id(user_id)
    if not user_data:
        logger.warning(f"cleanup_subscription: пользователь не найден user_id={user_id}")
        return result

    tg_id = to_int(user_data.get("telegram_id"), user_id)
    internal_uid = user_data.get("user_id", user_id)

    trust_before: int | None = None
    trust_after: int | None = None
    trust_delta = 0

    if not await is_admin_user(tg_id) and reason == "traffic_exhausted":
        trust_before = await db.get_trust_score(internal_uid)
        changed, before, after, delta = await apply_trust_score_delta(  # noqa: RUF059
            internal_uid, -TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED
        )
        if changed:
            trust_after = after
            trust_delta = delta

    base_email = get_user_panel_email(internal_uid, user_data)
    deleted = False
    try:
        deleted = await panel.delete_client(base_email)
        if deleted:
            logger.info(f"🗑 Клиент {user_id} удалён с панели (reason={reason})")
        else:
            logger.warning(f"⚠️ Не удалось удалить клиента {user_id} с панели (reason={reason})")
    except Exception as e:  # noqa: BLE001
        logger.error(f"cleanup_subscription: ошибка удаления с панели {user_id}: {e}")

    if deleted:
        await db.remove_subscription(internal_uid)
        logger.info(f"🗑 Подписка {user_id} очищена из БД (reason={reason})")
        result["success"] = True
    else:
        logger.warning(
            f"⚠️ Подписка {user_id} не удалена из БД, т.к. клиент не удалён с панели (reason={reason})"
        )

    if notify_user_about_cleanup and not await is_admin_user(tg_id):
        try:
            user_lang = await db.get_user_language_by_user_id(internal_uid) or lang
            cleanup_text = build_subscription_cleanup_message(
                reason,
                trust_before=trust_before,
                trust_after=trust_after,
                trust_delta=trust_delta,
                lang=user_lang,
            )
            await notify_user(tg_id, cleanup_text, reply_markup=support_keyboard(include_main=True))
        except Exception as e:  # noqa: BLE001
            logger.error(f"cleanup_subscription: ошибка уведомления {user_id}: {e}")

    result["success"] = True
    result["trust_before"] = trust_before
    result["trust_after"] = trust_after
    result["trust_delta"] = trust_delta
    return result


async def ensure_subscription_state(
    user_id: int,
    *,
    notify_user_about_cleanup: bool = False,
    lang: str = Config.DEFAULT_LANGUAGE,
) -> dict[str, Any]:
    state = await get_subscription_state(user_id)
    status = state.get("status")
    if status in ("expired", "traffic_exhausted"):
        cleanup_result = await cleanup_subscription(
            user_id,
            status,
            notify_user_about_cleanup=notify_user_about_cleanup,
            lang=lang,
        )
        state["cleanup_success"] = cleanup_result.get("success", False)
        state["cleanup_trust_before"] = cleanup_result.get("trust_before")
        state["cleanup_trust_after"] = cleanup_result.get("trust_after")
        state["cleanup_trust_delta"] = cleanup_result.get("trust_delta", 0)
    else:
        state["cleanup_success"] = False
    return state


async def cleanup_admin_test_subscriptions() -> dict[str, int]:
    result = {"removed": 0, "errors": 0}
    cutoff_time = int(time.time() * 1000) - (24 * 60 * 60 * 1000)

    for admin_id in ADMIN_USER_ID_SET:
        try:
            user_data = await db.get_user_by_any_id(admin_id)
            if not user_data:
                continue

            plan_text = str(user_data.get("plan_text", "") or "")
            if not any(suffix in plan_text.lower() for suffix in [" (тест)", " (test)"]):
                continue

            vpn_url = user_data.get("vpn_url", "")
            if not vpn_url:
                continue

            internal_uid = user_data.get("user_id", admin_id)
            base_email = build_base_email(internal_uid)
            clients = await panel.find_clients_full_by_email(base_email)

            if not clients:
                await db.remove_subscription(internal_uid)
                result["removed"] += 1
                logger.info(
                    f"Удалена тестовая подписка админа {admin_id} (клиент не найден на панели)"
                )
                continue

            for c in clients:
                expiry_time = to_int(c.get("expiryTime"), 0)
                if expiry_time <= cutoff_time:
                    deleted = await panel.delete_client(base_email)
                    if deleted:
                        await db.remove_subscription(internal_uid)
                        result["removed"] += 1
                        logger.info(f"Удалена тестовая подписка админа {admin_id} (истекла 24ч)")
                    else:
                        result["errors"] += 1
                        logger.warning(f"Не удалось удалить тестовую подписку админа {admin_id}")
                    break
        except Exception as e:  # noqa: BLE001
            result["errors"] += 1
            logger.error(f"Ошибка при очистке тестовой подписки админа {admin_id}: {e}")

    return result


async def ensure_startup_admin_accounts() -> None:
    global _admin_startup_completed
    for admin_tg_id in Config.ADMIN_USER_IDS:
        try:
            await db.add_user(admin_tg_id, force=True)
            user_data = await db.get_user_by_any_id(admin_tg_id)
            if user_data:
                await _ensure_admin_subscription(user_data["user_id"])
        except Exception as e:  # noqa: BLE001
            logger.warning(f"ensure_startup_admin_accounts {admin_tg_id}: {e}")
    _admin_startup_completed = True


async def _ensure_admin_subscription(admin_id: int) -> bool:
    try:
        user_data = await db.get_user_by_any_id(admin_id)
        if not user_data:
            return False
        telegram_id = to_int(user_data.get("telegram_id"), 0) or admin_id
        admin_email = f"admin@{Config.VPN_NAME.lower()}.com"
        admin_sub_id = "Admin"
        days = Config.ADMIN_AUTO_SUBSCRIBE_DAYS
        traffic_gb = 0
        ip_limit = 0
        servers: list[str] = []
        inbound_ids = await panel.get_matching_inbound_ids(servers) or []
        if not inbound_ids:
            logger.error(
                f"_ensure_admin_subscription {admin_id}: нет доступных inbound'ов на панели"
            )
            return False

        # Ищем уже существующего канонического Admin-клиента: сначала по subId
        # (он единый для всех админов), затем по каноническому email.
        existing = None
        existing_email = admin_email
        ok, sub_clients = await panel.find_clients_by_sub_id_safe(admin_sub_id)
        if ok and sub_clients:
            c0 = sub_clients[0]
            existing_email = str(c0.get("email") or admin_email)
            existing = await panel.get_client_by_email(existing_email) or c0
        if not existing:
            existing = await panel.get_client_by_email(admin_email)
            if existing:
                existing_email = admin_email

        if existing:
            # Уже есть канонический клиент Admin - обновляем его
            # (безлимит + привязка ко всем inbound'ам), не создавая дубля.
            client = dict(existing)
            client["email"] = existing_email
            client["enable"] = True
            client["limitIp"] = ip_limit
            client["totalGB"] = 0
            client["subId"] = admin_sub_id
            client["tgId"] = max(0, int(telegram_id))
            client["inboundIds"] = inbound_ids
            payload = panel._client_payload_for_update(client)
            url = f"{panel.apibase}/panel/api/clients/update/{panel._quote_path(existing_email)}"
            status, data, _ = await panel._request_json_with_reauth(
                "POST", url, headers=panel._headers(), json=payload
            )
            if not (status in (200, 201) and data.get("success")):
                logger.error(
                    f"_ensure_admin_subscription: не удалось обновить Admin клиент: "
                    f"{data.get('msg')}"
                )
            await panel.attach_client_to_inbounds(existing_email, inbound_ids)
            logger.info(
                f"Admin {telegram_id}: обновлён клиент '{admin_sub_id}' "
                f"(привязка ко всем inbound'ам)"
            )
        else:
            client = await panel.create_client(
                email=admin_email,
                limit_ip=ip_limit,
                total_gb=traffic_gb,
                days=days,
                servers=servers,
                tg_id=telegram_id,
                sub_id=admin_sub_id,
            )
            if not client:
                # subId уже занят другим клиентом - обновляем существующий.
                logger.warning(
                    f"_ensure_admin_subscription {admin_id}: subId '{admin_sub_id}' "
                    f"уже занят, обновляем существующего клиента"
                )
                ok2, sub_clients2 = await panel.find_clients_by_sub_id_safe(admin_sub_id)
                if ok2 and sub_clients2:
                    c1 = sub_clients2[0]
                    existing_email = str(c1.get("email") or admin_email)
                    existing = await panel.get_client_by_email(existing_email) or c1
                    client = dict(existing)
                    client["email"] = existing_email
                    client["enable"] = True
                    client["limitIp"] = ip_limit
                    client["totalGB"] = 0
                    client["subId"] = admin_sub_id
                    client["tgId"] = max(0, int(telegram_id))
                    client["inboundIds"] = inbound_ids
                    payload = panel._client_payload_for_update(client)
                    url = (
                        f"{panel.apibase}/panel/api/clients/update/"
                        f"{panel._quote_path(existing_email)}"
                    )
                    status, data, _ = await panel._request_json_with_reauth(
                        "POST", url, headers=panel._headers(), json=payload
                    )
                    if not (status in (200, 201) and data.get("success")):
                        logger.error(
                            f"_ensure_admin_subscription: не удалось обновить Admin клиент "
                            f"по subId: {data.get('msg')}"
                        )
                        return False
                    await panel.attach_client_to_inbounds(existing_email, inbound_ids)
                    logger.info(
                        f"Admin {telegram_id}: обновлён существующий клиент '{admin_sub_id}'"
                    )
                else:
                    logger.error(
                        f"_ensure_admin_subscription {admin_id}: не удалось создать Admin клиент"
                    )
                    return False
            else:
                logger.info(
                    f"Admin {telegram_id}: создан клиент '{admin_sub_id}' (все inbound'ы, безлимит)"
                )

        # Удаляем устаревший user_* клиент этого админа (мусор от старой логики),
        # но не тот, который мы только что сделали каноническим Admin-клиентом.
        stale_email = build_base_email(telegram_id)
        if stale_email and stale_email != admin_email and stale_email != existing_email:
            try:
                await panel.delete_client(stale_email)
                logger.info(f"Admin {telegram_id}: удалён устаревший клиент {stale_email}")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Admin {telegram_id}: не удалось удалить {stale_email}: {e}")

        expiry_dt = datetime.now(timezone.utc) + timedelta(days=days)
        expiry_sub_datatime = expiry_dt.isoformat()
        await db.set_subscription(
            admin_id,
            plan_text=admin_sub_id,
            ip_limit=ip_limit,
            vpn_url=admin_sub_id,
            traffic_gb=traffic_gb,
            plan_servers=servers,
            subscription_id=admin_sub_id,
            expiry_sub_datatime=expiry_sub_datatime,
        )
        logger.info(
            f"Admin {telegram_id}: подписка синхронизирована с '{admin_sub_id}' "
            f"({days} дней, {traffic_gb} GB)"
        )
        return True
    except Exception as e:  # noqa: BLE001
        logger.error(f"_ensure_admin_subscription {admin_id}: {e}")
        return False


async def _notify_subscription_creation_failed(
    user_id: int, plan_name: str, error: str = ""
) -> None:
    try:
        user = await db.get_user_by_any_id(user_id)
        tg_id = to_int(user.get("telegram_id"), user_id) if user else user_id
        user_lang = await get_user_language(tg_id)
        await notify_user(
            tg_id,
            translate(
                user_lang,
                "texts.subscription_creation_failed",
                plan_name=plan_name,
                error=error,
            ),
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"_notify_subscription_creation_failed {user_id}: {e}")


async def create_subscription(
    user_id: int,
    plan: dict[str, Any],
    *,
    extra_days: int = 0,
    days_override: int | None = None,
    plan_suffix: str | None = None,
    earn_trust: bool = True,
    paid_amount: float | None = None,
) -> str | None:
    async with get_subscription_lock(user_id):
        return await _create_subscription_unlocked(
            user_id,
            plan,
            extra_days=extra_days,
            days_override=days_override,
            plan_suffix=plan_suffix,
            earn_trust=earn_trust,
            paid_amount=paid_amount,
        )


async def _create_subscription_unlocked(
    user_id: int,
    plan: dict[str, Any],
    *,
    extra_days: int = 0,
    days_override: int | None = None,
    plan_suffix: str | None = None,
    earn_trust: bool = True,
    paid_amount: float | None = None,
) -> str | None:
    if not plan:
        logger.error(f"create_subscription: план не указан для user {user_id}")
        return None
    if not validate_user_id(user_id):
        logger.error(f"create_subscription: некорректный user_id {user_id}")
        return None
    await db.add_user(user_id)

    db_user = await db.get_user_by_any_id(user_id)
    internal_user_id = db_user["user_id"] if db_user else user_id

    pending = await db.get_bonus_days_pending(user_id)
    days = (
        (days_override if days_override is not None else int(plan.get("duration_days", 30)))
        + extra_days
        + pending
    )
    if days <= 0:
        days = 1

    plan_servers = get_plan_servers(plan)
    inbound_ids = await panel.get_matching_inbound_ids(plan_servers)
    if not inbound_ids:
        logger.error(f"create_subscription: нет matching inbound'ов для user {user_id}")
        return None

    base_email = build_base_email(internal_user_id)
    plan_name = plan.get("name", plan.get("id", ""))
    if plan_suffix:
        plan_name = f"{plan_name}{plan_suffix}"
    old_client_backup: dict[str, Any] | None = None
    client = None
    try:
        old_client = await panel.get_client_by_email(base_email)
        if old_client and isinstance(old_client, dict):
            old_client_backup = dict(old_client)
        try:
            await panel.delete_client(base_email)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                f"create_subscription: ошибка удаления старого клиента для user {user_id}: {e}"
            )

        client = await panel.create_client(
            email=base_email,
            limit_ip=int(plan.get("ip_limit", 0)),
            total_gb=int(plan.get("traffic_gb", 0)),
            days=days,
            servers=plan_servers,
            tg_id=user_id,
            inbound_ids=inbound_ids,
        )
    except Exception as e:  # noqa: BLE001
        logger.error(f"create_subscription: ошибка при создании клиента для user {user_id}: {e}")
        if old_client_backup:
            try:
                await panel.create_or_restore_client_from_backup(old_client_backup)
                logger.info(
                    f"create_subscription: попытка восстановления старого клиента для user {user_id}"
                )
            except Exception as restore_err:  # noqa: BLE001
                logger.error(
                    f"create_subscription: не удалось восстановить старого клиента для user {user_id}: "
                    f"{restore_err}"
                )
        await _notify_subscription_creation_failed(user_id, plan_name, error=str(e))
        return None

    if not client:
        logger.warning(
            f"create_subscription: повторная попытка для user {user_id} (Duplicate email?)"
        )
        try:
            direct = await panel.get_client_by_email(base_email)
            if direct:
                direct_email = direct.get("email") or base_email
                del_url = (
                    f"{panel.apibase}/panel/api/clients/del/"
                    f"{panel._quote_path(direct_email)}?keepTraffic=0"
                )
                try:
                    await panel._request_json_with_reauth("POST", del_url, headers=panel._headers())
                    logger.info(f"create_subscription: принудительно удалён {direct_email}")
                except Exception as e:  # noqa: BLE001
                    logger.error(f"create_subscription: ошибка принудительного удаления: {e}")
            await asyncio.sleep(1)
            client = await panel.create_client(
                email=base_email,
                limit_ip=int(plan.get("ip_limit", 0)),
                total_gb=int(plan.get("traffic_gb", 0)),
                days=days,
                servers=plan_servers,
                tg_id=user_id,
                inbound_ids=inbound_ids,
            )
        except Exception as e:  # noqa: BLE001
            logger.error(
                f"create_subscription: ошибка при повторном создании клиента для user {user_id}: {e}"
            )
            if old_client_backup:
                try:
                    await panel.create_or_restore_client_from_backup(old_client_backup)
                    logger.info(
                        f"create_subscription: попытка восстановления старого клиента для user {user_id}"
                    )
                except Exception as restore_err:  # noqa: BLE001
                    logger.error(
                        f"create_subscription: не удалось восстановить старого клиента для user {user_id}: "
                        f"{restore_err}"
                    )
            await _notify_subscription_creation_failed(user_id, plan_name, error=str(e))
            return None

    if not client:
        logger.error(f"create_subscription: не удалось создать клиента для user {user_id}")
        await _notify_subscription_creation_failed(
            user_id, plan_name, error="panel_creation_failed"
        )
        return None

    sub_id = normalize_sub_id(client.get("subId", f"user_{user_id}")) or f"user_{user_id}"
    plan_id_for_db = plan.get("id", "")
    expiry_dt = datetime.now(timezone.utc) + timedelta(days=days)
    expiry_sub_datatime = expiry_dt.isoformat()

    await db.set_subscription(
        internal_user_id,
        plan_text=plan_name,
        ip_limit=int(plan.get("ip_limit", 0)),
        traffic_gb=int(plan.get("traffic_gb", 0)),
        vpn_url=sub_id,
        plan_servers=plan_servers,
        subscription_id=plan_id_for_db,
        expiry_sub_datatime=expiry_sub_datatime,
    )

    if pending > 0:
        await db.clear_bonus_days_pending(user_id)

    if earn_trust:
        accrual_base = (
            to_float(paid_amount, 0.0)
            if paid_amount is not None
            else to_float(plan.get("price_rub", 0), 0.0)
        )
        earned = int((accrual_base * TRUST_SCORE_EARN_PERCENT) / 100)
        if earned > 0:
            await db.add_trust_score(user_id, earned)

    logger.info(f"✅ Подписка создана для user {user_id}")
    return build_subscription_url(sub_id)


async def renew_subscription(
    user_id: int,
    plan: dict[str, Any],
    *,
    extra_days: int = 0,
    earn_trust: bool = True,
    paid_amount: float | None = None,
) -> str | None:
    if not plan:
        return None
    await db.add_user(user_id)

    db_user = await db.get_user_by_any_id(user_id)
    internal_user_id = db_user["user_id"] if db_user else user_id

    state = await get_subscription_state(user_id)
    if state.get("status") != "active":
        return await create_subscription(
            user_id,
            plan,
            extra_days=extra_days,
            earn_trust=earn_trust,
            paid_amount=paid_amount,
        )
    max_expiry = to_int(state.get("max_expiry"), 0)
    now_ms = int(time.time() * 1000)
    if max_expiry <= now_ms:
        return await create_subscription(
            user_id,
            plan,
            extra_days=extra_days,
            earn_trust=earn_trust,
            paid_amount=paid_amount,
        )
    pending = await db.get_bonus_days_pending(user_id)
    days = int(plan.get("duration_days", 30)) + extra_days + pending
    if days <= 0:
        days = 1
    plan_servers = get_plan_servers(plan)
    inbound_ids = await panel.get_matching_inbound_ids(plan_servers)
    if not inbound_ids:
        return None
    user_data = await db.get_user_by_any_id(user_id)
    if not user_data:
        return None
    internal_uid = user_data.get("user_id", user_id)
    base_email = build_base_email(internal_uid)
    clients = await panel.find_clients_full_by_email(base_email)
    if not clients:
        return None

    emails: list[str] = []
    seen: set[str] = set()
    for c in clients:
        email = str(c.get("email") or "")
        if email and email not in seen:
            seen.add(email)
            emails.append(email)

    if not emails:
        return None

    add_bytes = int(plan.get("traffic_gb", 0) * BYTES_IN_GB)
    bulk_payload = {"emails": emails, "addDays": days}
    if add_bytes > 0:
        bulk_payload["addBytes"] = add_bytes

    url = f"{panel.apibase}/panel/api/clients/bulkAdjust"
    status, data, _ = await panel._request_json_with_reauth(
        "POST", url, headers=panel._headers(), json=bulk_payload
    )
    bulk_ok = False
    if status in (200, 201) and data.get("success"):
        obj = data.get("obj") or {}
        if isinstance(obj, dict):
            adjusted = to_int(obj.get("adjusted", 0), 0)
            skipped = obj.get("skipped", [])
            if adjusted > 0:
                bulk_ok = True
                logger.info(
                    f"renew_subscription: bulkAdjust OK - продлено {adjusted}, "
                    f"пропущено {len(skipped)}: {skipped}"
                )
            else:
                logger.warning(f"renew_subscription: bulkAdjust adjusted=0, skipped={skipped}")
        else:
            bulk_ok = True
    else:
        logger.error(
            f"renew_subscription: bulkAdjust ошибка: status={status}, data={data.get('msg')}"
        )

    if not bulk_ok:
        return None

    traffic_reset_ok = await panel.reset_client_traffic(base_email)
    if not traffic_reset_ok:
        logger.warning(
            f"renew_subscription: не удалось полностью сбросить трафик для user {user_id}"
        )

    for c in clients:
        email = str(c.get("email") or "")
        if not email:
            continue
        client = await panel.get_client_by_email(email) or c.get("clientObj") or c
        if not isinstance(client, dict):
            continue
        client["limitIp"] = int(plan.get("ip_limit", 0))
        client["enable"] = True
        payload = panel._client_payload_for_update(client)
        upd_url = f"{panel.apibase}/panel/api/clients/update/{panel._quote_path(email)}"
        status, upd_data, _ = await panel._request_json_with_reauth(
            "POST", upd_url, headers=panel._headers(), json=payload
        )
        if status not in (200, 201) or not upd_data.get("success"):
            logger.error(
                f"renew_subscription: update limitIp ошибка для {email}: {upd_data.get('msg')}"
            )
        existing = [to_int(i, 0) for i in (client.get("inboundIds") or []) if to_int(i, 0) > 0]
        target_inbounds = sorted({*existing, *inbound_ids})
        to_attach = sorted(set(target_inbounds) - set(existing))
        to_detach = sorted(set(existing) - set(target_inbounds))
        if to_detach:
            await panel.detach_client_from_inbounds(email, to_detach)
        if to_attach:
            await panel.attach_client_to_inbounds(email, to_attach)
    plan_name = plan.get("name", plan.get("id", ""))
    vpn_url = str(user_data.get("vpn_url") or "")
    plan_id_for_db = plan.get("id", "")
    max_expiry_dt = (
        datetime.fromtimestamp(max_expiry / 1000, tz=timezone.utc)
        if max_expiry > 0
        else datetime.now(timezone.utc),
    )
    expiry_sub_datatime = (max_expiry_dt + timedelta(days=days)).isoformat()

    await db.set_subscription(
        internal_user_id,
        plan_text=plan_name,
        ip_limit=int(plan.get("ip_limit", 0)),
        traffic_gb=int(plan.get("traffic_gb", 0)),
        vpn_url=vpn_url,
        plan_servers=plan_servers,
        subscription_id=plan_id_for_db,
        expiry_sub_datatime=expiry_sub_datatime,
    )
    if pending > 0:
        await db.clear_bonus_days_pending(user_id)
    if earn_trust:
        accrual_base = (
            to_float(paid_amount, 0.0)
            if paid_amount is not None
            else to_float(plan.get("price_rub", 0), 0.0)
        )
        earned = int((accrual_base * TRUST_SCORE_EARN_PERCENT) / 100)
        if earned > 0:
            await db.add_trust_score(user_id, earned)
    logger.info(f"✅ Подписка продлена для user {user_id}")
    return build_subscription_url(vpn_url) if vpn_url else None


async def is_active_subscription(user_id: int, *, notify_user_about_cleanup: bool = False) -> bool:
    state = await ensure_subscription_state(
        user_id, notify_user_about_cleanup=notify_user_about_cleanup
    )
    return state.get("status") == "active" or (
        state.get("status") == "panel_unavailable" and state.get("sub_id")
    )


async def notify_expiring_subscription(
    user_id: int, state: dict[str, Any], days: int | None = None
) -> bool:
    if days is None:
        days = Config.EXPIRY_ALERT_DAYS

    user_data = await db.get_user_by_any_id(user_id)
    if not user_data:
        return False
    max_expiry = to_int(state.get("max_expiry"), 0)
    if max_expiry <= 0:
        expiry_str = str(user_data.get("expiry_sub_datatime") or "").strip()
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
                max_expiry = int(expiry_dt.timestamp() * 1000)
            except Exception:  # noqa: BLE001, S110
                pass
    if max_expiry <= 0:
        return False

    if state.get("status") != "active" or not is_expiring_soon({"max_expiry": max_expiry}, days):
        return False

    if not await should_send_expiry_alert(user_id):
        return False

    lang = await get_user_language(user_id)
    days_left = max(1, math.ceil((max_expiry - int(time.time() * 1000)) / (SECONDS_IN_DAY * 1000)))
    text = translate(
        lang,
        "texts.subscription_expiring_soon",
        plan_text=user_data.get("plan_text", translate(lang, "texts.current_plan_fallback")),
        days_left=format_duration(days_left),
    )
    keyboard = kb(
        [
            [
                {
                    "text": translate(lang, "buttons.renew_subscription"),
                    "callback_data": "buy",
                }
            ],
            [
                {
                    "text": translate(lang, "buttons.my_subscription"),
                    "callback_data": "mysub",
                }
            ],
        ]
    )
    try:
        if await notify_user(user_id, text, reply_markup=keyboard):
            await db.set_expiry_notification_sent(user_id, True)
            return True
        return False
    except Exception as e:  # noqa: BLE001
        logger.error(f"notify_expiring {user_id}: {e}")
        return False


async def reward_referrer(referrer_id: int, bonus_days: int) -> None:
    user = await db.get_user_by_any_id(referrer_id)
    if not user:
        return
    tg_id = to_int(user.get("telegram_id"), referrer_id)
    lang = await get_user_language(tg_id)
    pending = await db.get_bonus_days_pending(referrer_id)
    total = bonus_days + pending
    internal_uid = user.get("user_id", referrer_id)
    base_email = build_base_email(internal_uid)
    has_active = await is_active_subscription(referrer_id)
    if has_active:
        if await panel.extend_client_expiry(base_email, total):
            if pending > 0:
                await db.clear_bonus_days_pending(referrer_id)
            await notify_user(
                tg_id,
                translate(
                    lang,
                    "texts.referral_bonus_days_added",
                    bonus_days=format_duration(total),
                ),
            )
            return
        await db.add_bonus_days_pending(referrer_id, bonus_days)
        await notify_admins(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.referral_bonus_extend_failed_admin",
                referrer_id=referrer_id,
                bonus_days=format_duration(bonus_days),
            )
        )
        return
    min_plan = get_minimal_by_price()
    if not min_plan:
        await db.add_bonus_days_pending(referrer_id, bonus_days)
        await notify_admins(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.referral_bonus_no_plan_admin",
                referrer_id=referrer_id,
            )
        )
        return
    vpn_url = await create_subscription(
        referrer_id,
        min_plan,
        days_override=bonus_days,
        plan_suffix=translate(lang, "texts.referral_bonus_plan_suffix"),
        earn_trust=False,
    )
    if vpn_url:
        await notify_user(
            tg_id,
            translate(
                lang,
                "texts.referral_bonus_subscription_created",
                bonus_days=format_duration(total),
                vpn_url=vpn_url,
            ),
        )
    else:
        await db.add_bonus_days_pending(referrer_id, bonus_days)
        await notify_admins(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.referral_bonus_create_failed_admin",
                referrer_id=referrer_id,
            )
        )


async def claim_pending_payment_or_alert(
    event: CallbackQuery, payment_id: str, action: str
) -> dict[str, Any] | None:
    moderator_id = get_event_user_id(event) or 0
    payment = await json_db.claim_pending_payment(payment_id, moderator_id, action)
    if not payment:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_claim_unavailable"),
            show_alert=True,
        )
        return None
    return payment


async def finalize_claimed_payment_or_alert(
    event: CallbackQuery, payment_id: str, action: str, final_status: str
) -> bool:
    moderator_id = get_event_user_id(event) or 0
    success = await json_db.finalize_claimed_payment(payment_id, moderator_id, action, final_status)
    if not success:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_finalize_changed"),
            show_alert=True,
        )
        return False
    return True


async def rollback_claimed_payment(
    event: CallbackQuery, payment_id: str, action: str, error_message: str
) -> None:
    moderator_id = get_event_user_id(event) or 0
    await json_db.rollback_claimed_payment(
        payment_id, moderator_id, action, error_message=error_message
    )


async def verify_payment_final_status(payment_id: str, expected_status: str) -> bool:
    payment = await json_db.find_by_id(payment_id)
    if not payment:
        return False
    return payment.get("status") == expected_status


@dataclasses.dataclass
class ResolvedUser:
    user_data: dict[str, Any]
    telegram_id: int
    internal_user_id: int


async def resolve_user_from_payment(payment: dict[str, Any]) -> ResolvedUser | None:
    raw_uid = to_int(payment.get("user_id"), 0)
    if raw_uid <= 0:
        return None

    tg_id = to_int(payment.get("tg_id"), 0)
    if tg_id > 0:
        user_data = await db.get_user_by_any_id(tg_id)
        if user_data:
            return ResolvedUser(
                user_data=user_data,
                telegram_id=tg_id,
                internal_user_id=user_data["user_id"],
            )

    user_data = await db.get_user_by_any_id(raw_uid)
    if user_data:
        return ResolvedUser(
            user_data=user_data,
            telegram_id=raw_uid,
            internal_user_id=user_data["user_id"],
        )

    user_data = await db.get_user_by_any_id(raw_uid)
    if user_data:
        real_tg_id = to_int(user_data.get("telegram_id"), 0)
        return ResolvedUser(
            user_data=user_data,
            telegram_id=real_tg_id,
            internal_user_id=user_data["user_id"],
        )

    return None


async def resolve_tg_id(raw_id: int) -> int:
    """Универсальный resolver: принимает telegram_id или internal user_id, возвращает telegram_id."""
    if raw_id <= 0:
        return 0
    user = await db.get_user_by_any_id(raw_id)
    if user:
        return to_int(user.get("telegram_id"), raw_id)
    return raw_id


async def resolve_user_by_any_id(raw_id: int) -> dict[str, Any] | None:
    """Ищет пользователя по telegram_id или internal user_id."""
    if raw_id <= 0:
        return None
    return await db.get_user_by_any_id(raw_id)


async def append_payment_decision_label(message: Message | None, status_label: str) -> None:
    if not message:
        return
    current = message.text or ""
    new_text = f"{current}\n\n{status_label}" if current else status_label
    try:
        await message.edit_text(new_text, parse_mode="HTML")
    except Exception:  # noqa: BLE001, S110
        pass


async def show_active_subscription_guard(event: Message | CallbackQuery) -> None:
    lang = await get_lang(event)
    user_id = get_event_user_id(event) or 0
    user = await db.get_user_by_any_id(user_id)
    if user and user.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.active_partner_subscription_guard"),
            reply_markup=active_subscription_keyboard(),
            delete_origin=True,
        )
        return
    await smart_answer(
        event,
        translate(lang, "texts.active_subscription_guard"),
        reply_markup=active_subscription_keyboard(),
        delete_origin=True,
    )


async def block_if_pending_payment(event: Message | CallbackQuery, user_id: int) -> bool:
    if await is_admin_user(user_id):
        return False
    if await json_db.has_pending_payment_for_user(user_id):
        lang = await get_user_language(user_id)
        text = translate(lang, "texts.payment_pending_block")
        markup = kb([[{"text": translate(lang, "buttons.main"), "callback_data": "start"}]])
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            if event.message:
                await event.message.answer(text, reply_markup=markup)
            await event.answer(
                translate(lang, "texts.payment_pending_block_alert"),
                show_alert=True,
            )
        return True
    return False


async def block_if_pending_partner_application(
    event: Message | CallbackQuery, user_id: int
) -> bool:
    if await is_admin_user(user_id):
        return False
    try:
        ops = await get_pending_partner_operations()
        pending = [
            o
            for o in ops
            if to_int(o.get("user_id"), 0) == user_id and o.get("op_type") == "partner_new"
        ]
    except Exception:  # noqa: BLE001
        pending = []
    if pending:
        lang = await get_user_language(user_id)
        text = translate(lang, "texts.partner_application_pending_block")
        markup = kb([[{"text": translate(lang, "buttons.main"), "callback_data": "start"}]])
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            if event.message:
                await event.message.answer(text, reply_markup=markup)
            await event.answer(
                translate(lang, "texts.partner_application_pending_block_alert"),
                show_alert=True,
            )
        return True
    return False


async def get_visible_plans(user_id: int, *, for_admin: bool) -> list[dict[str, Any]]:
    plans = get_all_active()
    if for_admin:
        return [p for p in plans if not is_trial_plan(p)]
    user = await db.get_user_by_any_id(user_id)
    trial_used = bool(user.get("trial_used")) if user else False
    has_sub = bool(user.get("has_subscription")) if user else False
    visible = []
    for p in plans:
        if is_trial_plan(p) and (trial_used or has_sub):
            continue
        visible.append(p)
    return visible


async def ban_middleware(handler: Callable, event: Any, data: dict[str, Any]) -> Any:
    user_id = get_event_user_id(event) or 0
    try:
        lang = data.get("language", Config.DEFAULT_LANGUAGE)
        user = await db.get_user_by_any_id(user_id)
        if user and user.get("banned"):
            reason = user.get("ban_reason", translate(lang, "texts.not_specified"))
            text = translate(lang, "texts.account_banned_message", reason=reason)
            markup = support_keyboard(include_main=True)
            try:
                if isinstance(event, Message):
                    await event.answer(text, reply_markup=markup)
                elif isinstance(event, CallbackQuery):
                    if event.message:
                        await event.message.answer(text, reply_markup=markup)
                    await event.answer(
                        translate(lang, "texts.account_banned_alert"),
                        show_alert=True,
                    )
            except TelegramBadRequest:
                try:
                    if isinstance(event, Message):
                        await event.answer(text, reply_markup=markup, parse_mode=None)
                    elif isinstance(event, CallbackQuery) and event.message:
                        await event.message.answer(text, reply_markup=markup, parse_mode=None)
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"Ошибка fallback-отправки в ban_middleware: {e}")
            return None
        return await handler(event, data)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка в ban_middleware для {user_id}: {e}")
        return await handler(event, data)


async def language_middleware(handler: Callable, event: Any, data: dict[str, Any]) -> Any:
    user_id = get_event_user_id(event) or 0
    try:
        lang = await db.get_user_language(user_id)
        if lang and lang in LANGUAGES:
            data["language"] = lang
        else:
            data["language"] = Config.DEFAULT_LANGUAGE
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка в language_middleware для {user_id}: {e}")
        data["language"] = Config.DEFAULT_LANGUAGE
    return await handler(event, data)


async def rate_limit_middleware(handler: Callable, event: Any, data: dict[str, Any]) -> Any:
    user = getattr(event, "from_user", None)
    if not user:
        return await handler(event, data)

    user_id = user.id
    if await is_admin_user(user_id):
        return await handler(event, data)

    now = time.time()
    last_request = _user_request_times.get(user_id, 0)
    elapsed = now - last_request

    if elapsed < Config.RATE_LIMIT_COOLDOWN:
        remaining = Config.RATE_LIMIT_COOLDOWN - elapsed
        lang = data.get("language", Config.DEFAULT_LANGUAGE)
        try:
            if isinstance(event, Message):
                await event.answer(
                    translate(
                        lang,
                        "texts.rate_limit",
                        remaining=f"{remaining:.1f}",
                    ),
                    reply_markup=main_menu_keyboard(),
                )
            elif isinstance(event, CallbackQuery):
                await event.answer(
                    translate(
                        lang,
                        "texts.rate_limit",
                        remaining=f"{remaining:.1f}",
                    ),
                    show_alert=True,
                )
        except Exception:  # noqa: BLE001, S110
            pass
        return None

    _user_request_times[user_id] = now
    if len(_user_request_times) > 10000:
        _user_request_times.clear()
    return await handler(event, data)


async def tech_work_middleware(handler: Callable, event: Any, data: dict[str, Any]) -> Any:
    user_id = get_event_user_id(event) or 0

    if not tech_work_service.is_enabled():
        return await handler(event, data)

    if await is_admin_user(user_id):
        return await handler(event, data)

    lang = data.get("language", Config.DEFAULT_LANGUAGE)
    text = translate(lang, "texts.tech_work_in_progress")
    markup = support_keyboard(include_main=False)

    try:
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            if event.message:
                await event.message.answer(text, reply_markup=markup)
            await event.answer(text, show_alert=True)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка при tech work: {e}")

    return None


router.message.outer_middleware(ban_middleware)
router.callback_query.outer_middleware(ban_middleware)
router.message.outer_middleware(language_middleware)
router.callback_query.outer_middleware(language_middleware)
router.message.outer_middleware(rate_limit_middleware)
router.callback_query.outer_middleware(rate_limit_middleware)
router.message.outer_middleware(tech_work_middleware)
router.callback_query.outer_middleware(tech_work_middleware)


# --- Универсальный обработчик ошибок ---
@router.errors()
async def error_handler(event: Any, *args: Any, **kwargs: Any) -> bool:
    error = kwargs.get("error")
    if not error and args:
        error = args[0]
    if not error:
        return False

    if isinstance(error, TelegramBadRequest):
        error_msg = str(error).lower()
        if (
            "blocked" in error_msg
            or "bot was blocked" in error_msg
            or "chat not found" in error_msg
        ):
            return True
        if "message not modified" in error_msg or "message to edit not found" in error_msg:
            return True
        if "message is not modified" in error_msg:
            return True
        logger.warning(f"TelegramBadRequest: {error}")
        return True

    if isinstance(error, ValidationError):
        return True

    if isinstance(error, (ConfigError, DatabaseError, PanelError)):
        logger.error(f"Ошибка системы: {error}")
        return True

    if isinstance(error, asyncio.CancelledError):
        return True

    logger.error(f"Необработанная ошибка: {type(error).__name__}: {error}")
    return False


# --- Обработчики команд ---
@router.message(Command("start"))
@router.callback_query(F.data == "start")
@log_error
async def cmd_start(event: Message | CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    await state.clear()
    user = getattr(event, "from_user", None)
    if not user:
        logger.warning("cmd_start: событие без from_user")
        return
    user_id: int = user.id

    if not validate_user_id(user_id):
        logger.error(f"cmd_start: некорректный user_id {user_id}")
        return

    try:
        ref_code: str = ""
        bot_auth_action: str | None = None
        bot_auth_state_data: dict[str, Any] | None = None
        lang = Config.DEFAULT_LANGUAGE

        if isinstance(event, Message) and event.text:
            parts = event.text.strip().split(maxsplit=1)
            if len(parts) > 1:
                arg = parts[1]
                if arg.startswith("web_login_"):
                    state = arg[len("web_login_") :]
                    bot_auth_state_data = await get_bot_auth_state(state)
                    if (
                        bot_auth_state_data
                        and not bot_auth_state_data.get("completed")
                        and bot_auth_state_data.get("state_type") == "web_login"
                    ):
                        bot_auth_action = "login"
                    else:
                        bot_auth_action = None
                        ref_code = ""
                elif arg.startswith("web_link_"):
                    state = arg[len("web_link_") :]
                    bot_auth_state_data = await get_bot_auth_state(state)
                    if (
                        bot_auth_state_data
                        and not bot_auth_state_data.get("completed")
                        and bot_auth_state_data.get("state_type") == "link"
                    ):
                        bot_auth_action = "link"
                    else:
                        bot_auth_action = None
                        ref_code = ""
                else:
                    ref_code = arg

        if not await is_admin_user(user_id) and bot_auth_action not in (
            "login",
            "link",
        ):
            try:
                await db.add_user(user_id)
                await db.ensure_ref_code(user_id)
                lang = await db.get_user_language(user_id) or Config.DEFAULT_LANGUAGE
            except Exception:  # noqa: BLE001
                lang = Config.DEFAULT_LANGUAGE
        elif await is_admin_user(user_id):
            try:
                if not _admin_startup_completed:
                    await db.add_user(user_id, force=True)
            except Exception:  # noqa: BLE001, S110
                pass
        else:
            lang = await db.get_user_language(user_id) or Config.DEFAULT_LANGUAGE

        if bot_auth_action == "login":
            tg_user = await db.get_user_by_any_id(user_id)
            await db.reconcile_telegram_account(user_id)
            tg_user = await db.get_user_by_any_id(user_id)

            if not tg_user and await is_admin_user(user_id):
                web_acct = await db.get_unlinked_web_account()
                if web_acct:
                    await db.update_web_auth(
                        web_acct["user_id"],
                        telegram_id=user_id,
                    )
                    tg_user = await db.get_user_by_any_id(web_acct["user_id"])
                elif not _admin_startup_completed:
                    await db.add_user(user_id, force=True)
                    tg_user = await db.get_user_by_any_id(user_id)

            if tg_user and tg_user.get("web_id") and to_int(tg_user.get("telegram_id"), 0) > 0:
                web_user = tg_user
            elif await is_admin_user(user_id):
                web_user = tg_user
                if web_user:
                    await db.update_web_auth(
                        web_user["user_id"],
                        telegram_id=user_id,
                    )
                unlinked_web = await db.get_unlinked_web_account()
                if unlinked_web and (
                    not web_user or unlinked_web["user_id"] != web_user["user_id"]
                ):
                    await db.update_web_auth(
                        unlinked_web["user_id"],
                        telegram_id=user_id,
                    )
                    await db.reconcile_telegram_account(user_id)
                    web_user = await db.get_user_by_any_id(user_id)
                if web_user and (not web_user.get("web_id") or web_user.get("web_id") == 0):
                    await db.update_web_auth(
                        web_user["user_id"],
                        web_id=web_user["user_id"],
                        web_registered_at=datetime.now(timezone.utc).isoformat(),
                    )
                    web_user = await db.get_user_by_any_id(user_id)
            else:
                await smart_answer(
                    event,
                    translate(
                        lang or Config.DEFAULT_LANGUAGE,
                        "texts.telegram_login_not_linked",
                    ),
                    delete_origin=True,
                )
                return
            if web_user:
                token = secrets.token_urlsafe(32)
                expires = (
                    datetime.now(timezone.utc) + timedelta(seconds=Config.SESSION_MAX_AGE)
                ).isoformat()
                await db.update_web_auth(
                    web_user["user_id"],
                    session_token=token,
                    session_expires_at=expires,
                    session_created_at=datetime.now(timezone.utc).isoformat(),
                    web_last_login=datetime.now(timezone.utc).isoformat(),
                    web_auth_method="telegram",
                )
                await store_telegram_verification(state, user_id)
                await complete_bot_auth_state(state, token)
                if await is_admin_user(user_id):
                    await _ensure_admin_subscription(web_user["user_id"])
                return_link = f"{Config.SITE_URL}"
                await smart_answer(
                    event,
                    translate(
                        lang or Config.DEFAULT_LANGUAGE,
                        "texts.telegram_login_success",
                        return_link=return_link,
                    ),
                    delete_origin=True,
                )
                return
            await smart_answer(
                event,
                translate(lang or Config.DEFAULT_LANGUAGE, "texts.telegram_login_failed"),
                delete_origin=True,
            )
            return

        if bot_auth_action == "link":
            session_token_hash = (
                bot_auth_state_data.get("session_token", "") if bot_auth_state_data else ""
            )
            session_user = await db.get_user_by_session_token_hash(session_token_hash)
            if not session_user:
                await smart_answer(
                    event,
                    translate(lang or Config.DEFAULT_LANGUAGE, "texts.telegram_link_failed"),
                    delete_origin=True,
                )
                return
            if session_user.get("telegram_id", 0) and session_user["telegram_id"] != user_id:
                await smart_answer(
                    event,
                    translate(
                        lang or Config.DEFAULT_LANGUAGE,
                        "texts.telegram_link_failed",
                    ),
                    delete_origin=True,
                )
                return
            existing = await db.get_user_by_any_id(user_id)
            if existing and existing.get("web_id") and existing["web_id"] == session_user["web_id"]:
                await complete_bot_auth_state(state, "")
                await smart_answer(
                    event,
                    translate(
                        lang or Config.DEFAULT_LANGUAGE,
                        "texts.telegram_link_success",
                        return_link=Config.SITE_URL,
                    ),
                    delete_origin=True,
                )
                return
            await db.reconcile_telegram_account(user_id)
            session_user = await db.get_user_by_session_token_hash(session_token_hash)
            existing = await db.get_user_by_any_id(user_id)
            if existing and existing["user_id"] != session_user["user_id"]:
                if existing.get("web_id") and existing["web_id"] != session_user["web_id"]:
                    await db.merge_accounts(session_user["user_id"], existing["user_id"])
                else:
                    await db.update_web_auth(existing["user_id"], telegram_id=0)
                    await db.delete_phantom_account(existing["user_id"])
                await db.update_web_auth(session_user["user_id"], telegram_id=user_id)
                await db.cleanup_telegram_phantoms(user_id, session_user["user_id"])
                await complete_bot_auth_state(state, "")
                return_link = Config.SITE_URL
                await smart_answer(
                    event,
                    translate(
                        lang or Config.DEFAULT_LANGUAGE,
                        "texts.telegram_link_success",
                        return_link=return_link,
                    ),
                    delete_origin=True,
                )
                return
            await db.update_web_auth(session_user["user_id"], telegram_id=user_id)
            await db.cleanup_telegram_phantoms(user_id, session_user["user_id"])
            await complete_bot_auth_state(state, "")
            return_link = Config.SITE_URL
            await smart_answer(
                event,
                translate(
                    lang or Config.DEFAULT_LANGUAGE,
                    "texts.telegram_link_success",
                    return_link=return_link,
                ),
                delete_origin=True,
            )
            return

        if not await is_admin_user(user_id):
            try:
                if ref_code:
                    ref_user = await db.get_user_by_ref_code(ref_code)
                    if ref_user and ref_user.get("user_id") != user_id:
                        await db.set_ref_by(user_id, ref_user.get("user_id"))
                        logger.info(
                            f"Пользователь {user_id} приглашен рефералом {ref_user.get('user_id')}"
                        )

                if not lang:
                    await prompt_language_selection(event)
                    return
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка инициализации пользователя {user_id}: {e}")
                try:
                    await event.answer(
                        translate(lang or Config.DEFAULT_LANGUAGE, "texts.init_error")
                    )
                except Exception:  # noqa: BLE001, S110
                    pass
                return
        else:
            lang = Config.DEFAULT_LANGUAGE

        total = await db.get_total_users()
        banned = await db.get_banned_users_count()
        active = len(await db.get_subscribed_user_ids())
        has_sub = False
        if not await is_admin_user(user_id):
            try:
                has_sub = await is_active_subscription(user_id, notify_user_about_cleanup=True)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка проверки подписки {user_id}: {e}")

        if await is_admin_user(user_id):
            text = translate(
                Config.DEFAULT_LANGUAGE,
                "texts.admin_welcome",
                total_users=total,
                active_vpns=active,
                banned_users=banned,
            )
            keyboard = build_main_keyboard(True, False, Config.DEFAULT_LANGUAGE)
        else:
            user_data = await db.get_user_by_any_id(user_id)
            is_partner = bool(user_data.get("is_mate")) if user_data else False
            text = translate(lang, "texts.welcome", total_users=total, active_vpns=active)
            keyboard = build_main_keyboard(False, has_sub, lang, is_partner=is_partner)

        await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)
    except Exception:
        logger.exception("Ошибка в cmd_start")
        try:
            await event.answer(translate(lang or Config.DEFAULT_LANGUAGE, "texts.unexpected_error"))
        except Exception:  # noqa: BLE001, S110
            pass


@router.callback_query(F.data == "cancel")
async def cmd_cancel(event: CallbackQuery, state: FSMContext, **kwargs: Any) -> None:
    await state.clear()
    await cmd_start(event, state)


@router.callback_query(F.data == "change_language")
async def cmd_change_language(event: CallbackQuery, state: FSMContext, **kwargs):
    await prompt_language_selection(event)


@router.callback_query(F.data.startswith("lang:"))
async def cmd_set_language(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = event.data.split(":", 1)[1]
    if lang not in LANGUAGES:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.language_not_supported"),
            show_alert=True,
        )
        return
    if not _admin_startup_completed:
        await db.add_user(user_id, force=True)
    await db.set_user_language(user_id, lang, force=True)
    await event.answer(
        translate(lang, "texts.language_selected", language=get_language_display_name(lang)),
        show_alert=True,
    )
    await cmd_start(event, state)


@router.callback_query(F.data == "buy")
async def cmd_buy(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    is_admin = await is_admin_user(user_id)
    if not is_admin:
        if await block_if_pending_payment(event, user_id):
            return
        await db.add_user(user_id)
        user_data = await db.get_user_by_any_id(user_id)
        is_partner = bool(user_data.get("is_mate")) if user_data else False
        if not is_partner:
            state = await ensure_subscription_state(
                user_id, notify_user_about_cleanup=True, lang=lang
            )
            if state.get("status") == "active" and not is_expiring_soon(
                state, Config.EXPIRY_ALERT_DAYS
            ):
                await show_active_subscription_guard(event)
                return

    all_plans = get_all_active()
    purchasable_plans = [p for p in all_plans if not is_trial_plan(p)]
    has_fixed_plans = len(purchasable_plans) > 0
    has_custom = custom_tariff_enabled()

    if has_custom and has_fixed_plans:
        text = translate(lang, "texts.buy_choose_title")
        keyboard = [
            [
                {
                    "text": translate(lang, "buttons.buy_choose_custom"),
                    "callback_data": "buy:choose_custom",
                }
            ],
            [
                {
                    "text": translate(lang, "buttons.buy_choose_fixed"),
                    "callback_data": "buy:choose_fixed",
                }
            ],
            [
                {
                    "text": translate(lang, "buttons.main"),
                    "callback_data": "start",
                }
            ],
        ]
        await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)
        return

    if has_custom and not has_fixed_plans:
        await cmd_buy_choose_custom(event, **kwargs)
        return

    if has_fixed_plans and not has_custom:
        plans = await get_visible_plans(user_id, for_admin=is_admin)
        text = build_fixed_tariffs_text(plans, lang=lang)
        text += "\n\n" + translate(lang, "texts.buy_fixed_hint")
        if is_admin:
            text += translate(lang, "texts.buy_admin_custom_hint")
        keyboard = []
        if is_admin:
            keyboard.append(
                [
                    {
                        "text": translate(Config.DEFAULT_LANGUAGE, "buttons.pay_await"),
                        "callback_data": "pay_await",
                    }
                ]
            )
            for p in plans:
                keyboard.append(
                    [
                        {
                            "text": translate(
                                Config.DEFAULT_LANGUAGE,
                                "buttons.test_plan",
                                plan_name=p.get("name", p.get("id")),
                            ),
                            "callback_data": f"test:{p.get('id')}",
                        }
                    ]
                )
        else:
            for p in plans:
                if is_trial_plan(p):
                    keyboard.append(
                        [
                            {
                                "text": p.get("name", p.get("id")),
                                "callback_data": "trial:trial",
                            }
                        ]
                    )
                else:
                    keyboard.append(
                        [
                            {
                                "text": p.get("name", p.get("id")),
                                "callback_data": f"buy:{p.get('id')}",
                            }
                        ]
                    )
        keyboard.append(
            [
                {
                    "text": translate(lang, "buttons.main"),
                    "callback_data": "start",
                }
            ]
        )
        await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)
        return

    text = translate(lang, "texts.buy_unavailable") + "\n\n" + translate(lang, "buttons.support")
    keyboard = [
        [
            (
                {
                    "text": translate(lang, "buttons.support"),
                    "url": Config.SUPPORT_URL if Config.SUPPORT_URL else None,
                }
                if Config.SUPPORT_URL
                else {
                    "text": translate(lang, "buttons.support"),
                    "callback_data": "support",
                }
            ),
        ],
        [
            {
                "text": translate(lang, "buttons.main"),
                "callback_data": "start",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)
    return


@router.callback_query(F.data == "buy:choose_custom")
async def cmd_buy_choose_custom(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    if not await is_admin_user(user_id):  # noqa: SIM102
        if await block_if_pending_payment(event, user_id):
            return
    await event.answer()
    await cmd_custom_start(event, **kwargs)


@router.callback_query(F.data == "buy:choose_fixed")
async def cmd_buy_choose_fixed(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    is_admin = await is_admin_user(user_id)
    if not is_admin:
        if await block_if_pending_payment(event, user_id):
            return
        await db.add_user(user_id)
        user_data = await db.get_user_by_any_id(user_id)
        is_partner = bool(user_data.get("is_mate")) if user_data else False
        if not is_partner:
            state = await ensure_subscription_state(
                user_id, notify_user_about_cleanup=True, lang=lang
            )
            if state.get("status") == "active" and not is_expiring_soon(
                state, Config.EXPIRY_ALERT_DAYS
            ):
                await show_active_subscription_guard(event)
                return
    plans = await get_visible_plans(user_id, for_admin=is_admin)
    text = build_fixed_tariffs_text(plans, lang=lang)
    text += "\n\n" + translate(lang, "texts.buy_fixed_hint")
    if is_admin:
        text += translate(lang, "texts.buy_admin_custom_hint")
    keyboard = []
    if is_admin:
        keyboard.append(
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.pay_await"),
                    "callback_data": "pay_await",
                }
            ]
        )
        for p in plans:
            keyboard.append(
                [
                    {
                        "text": translate(
                            Config.DEFAULT_LANGUAGE,
                            "buttons.test_plan",
                            plan_name=p.get("name", p.get("id")),
                        ),
                        "callback_data": f"test:{p.get('id')}",
                    }
                ]
            )
    else:
        for p in plans:
            if is_trial_plan(p):
                keyboard.append(
                    [
                        {
                            "text": p.get("name", p.get("id")),
                            "callback_data": "trial:trial",
                        }
                    ]
                )
            else:
                keyboard.append(
                    [
                        {
                            "text": p.get("name", p.get("id")),
                            "callback_data": f"buy:{p.get('id')}",
                        }
                    ]
                )
    keyboard.append(
        [
            {
                "text": translate(lang, "buttons.main"),
                "callback_data": "start",
            }
        ]
    )
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(F.data == "custom:start")
async def cmd_custom_start(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    is_admin = await is_admin_user(user_id)
    if not is_admin:
        if await block_if_pending_partner_application(event, user_id):
            return
        if await block_if_pending_payment(event, user_id):
            return
        await db.add_user(user_id)
        state = await ensure_subscription_state(user_id, notify_user_about_cleanup=True, lang=lang)
        if state.get("status") == "active" and not is_expiring_soon(
            state, Config.EXPIRY_ALERT_DAYS
        ):
            await show_active_subscription_guard(event)
            return

    text = translate(lang, "texts.buy_custom_title")
    text += translate(lang, "texts.buy_custom_hint") + "\n\n"
    text += build_custom_tariff_info_block(lang)

    keyboard = []
    if is_admin:
        keyboard.append(
            [
                {
                    "text": translate(lang, "buttons.pay_await"),
                    "callback_data": "pay_await",
                }
            ]
        )
    keyboard.append(
        [
            {
                "text": translate(lang, "buttons.collect_subscription"),
                "callback_data": "custom:collect",
            }
        ]
    )
    keyboard.append(
        [
            {
                "text": translate(lang, "buttons.main"),
                "callback_data": "start",
            }
        ]
    )

    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(F.data == "custom:collect")
async def cmd_custom_collect(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    await state.clear()
    await state.set_state(CustomTariffState.waiting_for_gb)
    lang = await get_lang(event)
    min_gb, max_gb = custom_gb_bounds()
    await event.answer()
    await smart_answer(
        event,
        translate(lang, "texts.custom_tariff_step_gb", min_gb=min_gb, max_gb=max_gb),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.message(CustomTariffState.waiting_for_gb)
async def process_custom_gb(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    if not await ensure_custom_tariff_access(event, state):
        return
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(
            translate(lang, "texts.custom_tariff_invalid_gb"),
            reply_markup=cancel_only_keyboard(),
        )
        return
    gb = int(val)
    min_gb, max_gb = custom_gb_bounds()
    if not (min_gb <= gb <= max_gb):
        await event.answer(
            translate(
                lang,
                "texts.custom_tariff_invalid_gb_range",
                min_gb=min_gb,
                max_gb=max_gb,
            ),
            reply_markup=cancel_only_keyboard(),
        )
        return
    await state.update_data(custom_traffic_gb=gb)
    await state.set_state(CustomTariffState.waiting_for_ip)
    min_ip, max_ip = custom_ip_bounds()
    await event.answer(
        translate(
            lang,
            "texts.custom_tariff_step_ip",
            min_ip=min_ip,
            max_ip=max_ip,
        ),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(CustomTariffState.waiting_for_ip)
async def process_custom_ip(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    if not await ensure_custom_tariff_access(event, state):
        return
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(
            translate(lang, "texts.custom_tariff_invalid_ip"),
            reply_markup=cancel_only_keyboard(),
        )
        return
    ip = int(val)
    min_ip, max_ip = custom_ip_bounds()
    if not (min_ip <= ip <= max_ip):
        await event.answer(
            translate(
                lang,
                "texts.custom_tariff_invalid_ip_range",
                min_ip=min_ip,
                max_ip=max_ip,
            ),
            reply_markup=cancel_only_keyboard(),
        )
        return
    await state.update_data(custom_ip_limit=ip)
    await state.set_state(CustomTariffState.waiting_for_days)
    min_days, max_days = custom_days_bounds()
    await event.answer(
        translate(
            lang,
            "texts.custom_tariff_step_days",
            min_days=min_days,
            max_days=max_days,
        ),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(CustomTariffState.waiting_for_days)
async def process_custom_days(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    if not await ensure_custom_tariff_access(event, state):
        return
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(
            translate(lang, "texts.custom_tariff_invalid_duration"),
            reply_markup=cancel_only_keyboard(),
        )
        return
    days = int(val)
    min_days, max_days = custom_days_bounds()
    if not (min_days <= days <= max_days):
        await event.answer(
            translate(
                lang,
                "texts.custom_tariff_invalid_duration_range",
                min_days=min_days,
                max_days=max_days,
            ),
            reply_markup=cancel_only_keyboard(),
        )
        return
    data = await state.get_data()
    gb = to_int(data.get("custom_traffic_gb"), 0)
    ip = to_int(data.get("custom_ip_limit"), 0)
    if not is_valid_custom_limits(gb, ip, days):
        await state.clear()
        await event.answer(
            translate(lang, "texts.custom_tariff_invalid_limits"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await state.update_data(custom_duration_days=days, custom_servers=[])
    await state.set_state(CustomTariffState.waiting_for_locations)
    await show_custom_locations_picker(event, state)


@router.message(CustomTariffState.waiting_for_locations)
async def process_custom_locations_text(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    if not await ensure_custom_tariff_access(event, state):
        return
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    await event.answer(
        translate(lang, "texts.custom_tariff_select_locations"),
        reply_markup=cancel_only_keyboard(),
    )


@router.callback_query(CustomTariffState.waiting_for_locations, F.data.startswith("custom:loc:"))
async def cmd_custom_toggle_location(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    code = normalize_server_code(event.data.rsplit(":", 1)[-1])
    if not get_location_by_code(code):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_location_unavailable"),
            show_alert=True,
        )
        return
    data = await state.get_data()
    selected = normalize_servers(data.get("custom_servers"))
    if code in selected:
        selected = [s for s in selected if s != code]
    else:
        selected.append(code)
    await state.update_data(custom_servers=selected)
    await show_custom_locations_picker(event, state)


@router.callback_query(CustomTariffState.waiting_for_locations, F.data == "custom:locations_done")
async def cmd_custom_locations_done(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    data = await state.get_data()
    selected = normalize_servers(data.get("custom_servers"))
    if not selected:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_choose_location_count"),
            show_alert=True,
        )
        return
    await show_custom_summary(event, state)


@router.message(CustomTariffState.waiting_for_confirm)
async def process_custom_confirm_text(event: Message, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    await event.answer(
        translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_use_buttons_or_cancel"),
        reply_markup=cancel_only_keyboard(),
    )


@router.callback_query(
    CustomTariffState.waiting_for_confirm, F.data.startswith("custom:show_offer:")
)
async def cmd_custom_show_offer(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return
    await show_offer_agreement(event, continue_callback_data=f"custom:choose_payment_method:{uid}")


@router.callback_query(
    CustomTariffState.waiting_for_confirm,
    F.data.startswith("custom:choose_payment_method:"),
)
async def cmd_custom_choose_payment_method(event: CallbackQuery, state: FSMContext, **kwargs):
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return

    if await is_admin_user(uid):
        keyboard = [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.payment_method_test"),
                    "callback_data": f"custom:confirm_payment:test:{uid}",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                    "callback_data": "cancel",
                }
            ],
        ]
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.choose_payment_method"),
            reply_markup=kb(keyboard),
            delete_origin=True,
        )
        return

    methods = []
    if Config.YOOMONEY_WALLET:
        methods.append(
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.payment_method_yoomoney"),
                "callback_data": f"custom:pay_yoomoney:{uid}",
            }
        )
    if Config.PAYMENT_CARD_NUMBER:
        methods.append(
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.payment_method_p2p"),
                "callback_data": f"custom:pay_p2p:{uid}",
            }
        )

    if not methods:
        await state.clear()
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.buy_unavailable"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return

    if len(methods) == 1:
        method = methods[0]["callback_data"]
        event.data = method
        if method.startswith("custom:pay_yoomoney:"):
            await cmd_custom_show_yoomoney(event, state, **kwargs)
        elif method.startswith("custom:pay_p2p:"):
            await cmd_custom_show_p2p(event, state, **kwargs)
        return

    keyboard = [methods] + [
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ]
    ]
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.choose_payment_method"),
        reply_markup=kb(keyboard),
        delete_origin=True,
    )


async def _build_yoomoney_payment(
    event: CallbackQuery,
    uid: int,
    amount: int,
    plan_name: str,
    confirm_callback: str,
    lang: str,
    *,
    targets_suffix: str = "#",
) -> None:
    order_id = f"{uid}_{uuid.uuid4().hex[:8]}"
    params = {
        "receiver": Config.YOOMONEY_WALLET,
        "quickpay-form": "shop",
        "targets": f"{Config.VPN_NAME} {targets_suffix}{order_id}",
        "paymentType": "AC",
        "sum": amount,
        "label": order_id,
    }
    pay_url = "https://yoomoney.ru/quickpay/confirm?" + urlencode(params)
    text = translate(
        lang,
        "texts.yoomoney_payment_details",
        plan_name=plan_name,
        amount=amount,
    )
    keyboard = [
        [
            {
                "text": f"🔗 {translate(lang, 'buttons.payment_method_yoomoney')}",
                "url": pay_url,
            }
        ],
        [
            {
                "text": translate(lang, "buttons.confirm_payment"),
                "callback_data": confirm_callback,
            }
        ],
        [
            {
                "text": translate(lang, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(
    CustomTariffState.waiting_for_confirm, F.data.startswith("custom:pay_yoomoney:")
)
async def cmd_custom_show_yoomoney(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return
    data = await state.get_data()
    amount = to_int(data.get("custom_final_amount"), -1)
    plan_name = str(data.get("custom_plan_name") or " ").strip()
    if amount < 0:
        await state.clear()
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await _build_yoomoney_payment(
        event=event,
        uid=uid,
        amount=amount,
        plan_name=plan_name,
        confirm_callback=f"custom:confirm_payment:yoomoney:{uid}",
        lang=Config.DEFAULT_LANGUAGE,
        targets_suffix="Custom #",
    )


@router.callback_query(F.data.startswith("custom:confirm_payment:test:"))
async def cmd_custom_confirm_test(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")
    if len(parts) < 4:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        user_id = int(parts[3])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if user_id != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return
    if not await is_admin_user(user_id):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.admin_only_feature"),
            show_alert=True,
        )
        return
    data = await state.get_data()
    traffic = to_int(data.get("custom_traffic_gb"), 0)
    ip = to_int(data.get("custom_ip_limit"), 0)
    days = to_int(data.get("custom_duration_days"), 0)
    servers = normalize_servers(data.get("custom_servers"))
    plan_name = str(data.get("custom_plan_name") or " ").strip()
    if not is_valid_custom_limits(traffic, ip, days) or not is_valid_custom_servers(servers):
        await state.clear()
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    if not plan_name:
        plan_name = build_custom_plan_name(traffic, ip, days, servers)
    custom_plan = build_custom_plan(traffic, ip, days, servers=servers, plan_name=plan_name)
    vpn_url = await create_subscription(
        user_id,
        custom_plan,
        plan_suffix=translate(Config.DEFAULT_LANGUAGE, "texts.test_plan_suffix"),
        earn_trust=False,
    )
    await state.clear()
    if vpn_url:
        user_lang = await get_user_language(user_id)
        text = translate(
            user_lang,
            "texts.custom_test_subscription_created",
            plan_name=plan_name,
            ip_limit=ip,
            traffic=format_traffic(traffic, user_lang),
            servers=format_servers(servers),
            duration=format_duration(days, user_lang),
            vpn_url=vpn_url,
        )
        setup_keyboard = build_setup_keyboard(user_lang)
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.test_subscription_failed")
        setup_keyboard = main_menu_keyboard()
    await smart_answer(event, text, reply_markup=setup_keyboard, delete_origin=True)


@router.callback_query(
    CustomTariffState.waiting_for_confirm, F.data.startswith("custom:confirm_payment:")
)
async def cmd_custom_confirm_payment(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")
    if len(parts) < 4:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    method = parts[2]
    try:
        uid = int(parts[3])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if not await is_admin_user(uid):
        st = await ensure_subscription_state(uid, notify_user_about_cleanup=True)
        if st.get("status") == "active" and not is_expiring_soon(st, Config.EXPIRY_ALERT_DAYS):
            await state.clear()
            await show_active_subscription_guard(event)
            return
    data = await state.get_data()
    traffic = to_int(data.get("custom_traffic_gb"), 0)
    ip = to_int(data.get("custom_ip_limit"), 0)
    days = to_int(data.get("custom_duration_days"), 0)
    servers = normalize_servers(data.get("custom_servers"))
    amount = to_int(data.get("custom_final_amount"), -1)
    base_amount = to_int(data.get("custom_base_amount"), -1)
    plan_name = str(data.get("custom_plan_name") or " ").strip()
    if (
        amount < 0
        or base_amount < 0
        or not is_valid_custom_limits(traffic, ip, days)
        or not is_valid_custom_servers(servers)
    ):
        await state.clear()
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    if not plan_name:
        plan_name = build_custom_plan_name(traffic, ip, days, servers)

    if await is_admin_user(uid):
        custom_plan = build_custom_plan(traffic, ip, days, servers=servers, plan_name=plan_name)
        vpn_url = await create_subscription(
            uid,
            custom_plan,
            plan_suffix=translate(Config.DEFAULT_LANGUAGE, "texts.test_plan_suffix"),
            earn_trust=False,
        )
        await state.clear()
        if vpn_url:
            user_lang = await get_user_language(uid)
            text = translate(
                user_lang,
                "texts.custom_test_subscription_created",
                plan_name=plan_name,
                ip_limit=ip,
                traffic=format_traffic(traffic, user_lang),
                servers=format_servers(servers),
                duration=format_duration(days, user_lang),
                vpn_url=vpn_url,
            )
            setup_keyboard = build_setup_keyboard(user_lang)
        else:
            text = translate(Config.DEFAULT_LANGUAGE, "texts.test_subscription_failed")
            setup_keyboard = main_menu_keyboard()
        await smart_answer(event, text, reply_markup=setup_keyboard, delete_origin=True)
        return

    payment_id = f"pay_{uid}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    payment_data = {
        "payment_id": payment_id,
        "user_id": uid,
        "plan_id": "custom",
        "plan_type": "custom",
        "plan_name": plan_name,
        "amount": amount,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "payment_method": method,
        "custom_plan": {
            "traffic_gb": traffic,
            "ip_limit": ip,
            "duration_days": days,
            "servers": servers,
            "price_rub": base_amount,
            "plan_name": plan_name,
        },
    }
    added = await json_db.add_pending_for_user(uid, payment_data)
    await state.clear()
    if not added:
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_request_already_exists"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.custom_payment_request_received"),
        reply_markup=main_menu_keyboard(),
        delete_origin=True,
    )


@router.callback_query(F.data.startswith("custom:"))
async def cmd_custom_unknown(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    known_prefixes = [
        "custom:show_offer:",
        "custom:choose_payment_method:",
        "custom:pay_yoomoney:",
        "custom:pay_p2p:",
        "custom:confirm_payment:test:",
        "custom:confirm_payment:yoomoney:",
        "custom:confirm_payment:p2p:",
        "custom:loc:",
    ]
    if any(event.data.startswith(prefix) for prefix in known_prefixes):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    await event.answer(
        translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_unknown_command"),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("buy:"))
async def cmd_buy_plan(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    if not await is_admin_user(user_id):
        if await block_if_pending_partner_application(event, user_id):
            return
        st = await ensure_subscription_state(user_id, notify_user_about_cleanup=True)
        if st.get("status") == "active" and not is_expiring_soon(st, Config.EXPIRY_ALERT_DAYS):
            await show_active_subscription_guard(event)
            return
    plan_id = event.data.split(":", 1)[1]
    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    await show_offer_agreement(
        event,
        continue_callback_data=f"show_payment:{plan.get('id')}:{user_id}",
        lang=lang,
    )


@router.callback_query(F.data.startswith("show_payment:"))
async def cmd_show_payment_details(event: CallbackQuery):
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return

    lang = await get_user_language(uid)

    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    price = to_float(plan.get("price_rub", 0), 0.0)
    duration = int(plan.get("duration_days", 30))
    trust = await db.get_trust_score(uid)
    final_price, disc = apply_trust_discount(price, trust)
    final_price_int = int(round(final_price))  # noqa: RUF046
    servers = get_plan_servers(plan)
    loc_line = (
        translate(
            lang,
            "texts.catalog_payment_locations_line",
            servers=format_servers(servers),
        )
        if servers
        else ""
    )
    if disc > 0:
        total_line = translate(
            lang,
            "texts.payment_total_with_discount",
            original_price=int(price) if price.is_integer() else price,
            final_price=final_price_int,
            discount_percent=disc,
        )
    else:
        total_line = translate(
            lang,
            "texts.payment_total",
            final_price=int(price) if price.is_integer() else price,
        )
    text = translate(
        lang,
        "texts.catalog_payment_details",
        plan_name=plan.get("name", plan_id),
        price_line=translate(
            lang,
            "texts.price_monthly" if duration == 30 else "texts.price_fixed_days",
            price=price,
            duration=duration,
        ),
        locations_line=loc_line,
        total_line=total_line,
        amount=final_price_int,
        payment_card=Config.PAYMENT_CARD_NUMBER,
    )
    keyboard = [
        [
            {
                "text": translate(lang, "buttons.confirm_payment"),
                "callback_data": f"confirm_payment:p2p:{plan_id}:{uid}",
            }
        ],
        [
            {
                "text": translate(lang, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(F.data.startswith("test:"))
async def cmd_test_plan(event: CallbackQuery, **kwargs: Any) -> None:
    user_id = get_event_user_id(event) or 0
    if not await is_admin_user(user_id):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.admin_only_feature"),
            show_alert=True,
        )
        return
    plan_id = event.data.split(":", 1)[1]
    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    vpn_url = await create_subscription(
        user_id,
        plan,
        plan_suffix=translate(Config.DEFAULT_LANGUAGE, "texts.test_plan_suffix"),
        earn_trust=False,
    )
    if vpn_url:
        user_lang = await get_user_language(user_id)
        text = translate(
            user_lang,
            "texts.test_subscription_created",
            plan_name=plan.get("name", plan_id),
            ip_limit=plan.get("ip_limit", 0),
            traffic=format_traffic(plan.get("traffic_gb", 0), user_lang),
            servers=format_servers(plan.get("servers")),
            duration=format_duration(int(plan.get("duration_days", 30)), user_lang),
            vpn_url=vpn_url,
        )
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.test_subscription_failed")
        user_lang = Config.DEFAULT_LANGUAGE
    setup_keyboard = build_setup_keyboard(user_lang)
    await smart_answer(event, text, reply_markup=setup_keyboard, delete_origin=True)


@router.callback_query(F.data.startswith("trial:"))
async def cmd_trial_plan(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    plan_id = event.data.split(":", 1)[1] if ":" in event.data else "trial"
    plan = get_by_id(plan_id)
    if not plan or not plan.get("active", True) or not is_trial_plan(plan):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.trial_plan_not_found"),
            show_alert=True,
        )
        return

    is_admin = await is_admin_user(user_id)

    if not is_admin:
        if await is_active_subscription(user_id, notify_user_about_cleanup=True):
            await show_active_subscription_guard(event)
            return
        await db.add_user(user_id)
        user = await db.get_user_by_any_id(user_id)
        if user.get("trial_used") or user.get("has_subscription"):
            text = translate(Config.DEFAULT_LANGUAGE, "texts.trial_used_or_has_subscription")
            keyboard = kb(
                [
                    [
                        {
                            "text": translate(Config.DEFAULT_LANGUAGE, "buttons.my_subscription"),
                            "callback_data": "mysub",
                        }
                    ],
                    [
                        {
                            "text": translate(Config.DEFAULT_LANGUAGE, "buttons.search_user"),
                            "callback_data": "debug_search_user",
                        }
                    ],
                    [
                        {
                            "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                            "callback_data": "start",
                        }
                    ],
                ]
            )
            await smart_answer(event, text, reply_markup=keyboard, delete_origin=True)
            return

    vpn_url = await create_subscription(
        user_id,
        plan,
        plan_suffix=translate(Config.DEFAULT_LANGUAGE, "texts.trial_plan_suffix"),
        earn_trust=False,
    )
    if vpn_url:
        if not is_admin:
            await db.mark_trial_used(user_id)
        user_lang = await get_user_language(user_id)
        text = translate(
            user_lang,
            "texts.trial_subscription_created",
            plan_name=plan.get("name", plan_id),
            ip_limit=plan.get("ip_limit", 0),
            traffic=format_traffic(plan.get("traffic_gb", 0), user_lang),
            servers=format_servers(plan.get("servers")),
            duration=format_duration(int(plan.get("duration_days", 30)), user_lang),
            vpn_url=vpn_url,
        )
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.trial_subscription_failed")
        user_lang = Config.DEFAULT_LANGUAGE
    setup_keyboard = build_setup_keyboard(user_lang)
    await smart_answer(event, text, reply_markup=setup_keyboard, delete_origin=True)


@router.callback_query(F.data.startswith("choose_payment_method:"))
async def cmd_choose_payment_method(event: CallbackQuery, **kwargs):
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return

    lang = await get_user_language(uid)

    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return

    methods = []
    if Config.YOOMONEY_WALLET:
        methods.append(
            {
                "text": translate(lang, "buttons.payment_method_yoomoney"),
                "callback_data": f"pay_yoomoney:{plan_id}:{uid}",
            }
        )
    if Config.PAYMENT_CARD_NUMBER:
        methods.append(
            {
                "text": translate(lang, "buttons.payment_method_p2p"),
                "callback_data": f"pay_p2p:{plan_id}:{uid}",
            }
        )

    if not methods:
        await event.answer(translate(lang, "texts.buy_unavailable"), show_alert=True)
        return

    if len(methods) == 1:
        method = methods[0]["callback_data"]
        event.data = method
        if method.startswith("pay_yoomoney:"):
            await cmd_show_yoomoney_payment(event, **kwargs)
        elif method.startswith("pay_p2p:"):
            await cmd_show_p2p_payment(event, **kwargs)
        return

    keyboard = [methods] + [
        [
            {
                "text": translate(lang, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ]
    ]
    await smart_answer(
        event,
        translate(lang, "texts.choose_payment_method"),
        reply_markup=kb(keyboard),
        delete_origin=True,
    )


@router.callback_query(F.data.startswith("pay_yoomoney:"))
async def cmd_show_yoomoney_payment(event: CallbackQuery, **kwargs):
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return

    lang = await get_user_language(uid)

    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    price = to_float(plan.get("price_rub", 0), 0.0)
    trust = await db.get_trust_score(uid)
    final_price, _ = apply_trust_discount(price, trust)
    final_price_int = int(round(final_price))  # noqa: RUF046
    await _build_yoomoney_payment(
        event=event,
        uid=uid,
        amount=final_price_int,
        plan_name=plan.get("name", plan_id),
        confirm_callback=f"confirm_payment:yoomoney:{plan_id}:{uid}",
        lang=lang,
    )


@router.callback_query(F.data.startswith("pay_p2p:"))
async def cmd_show_p2p_payment(event: CallbackQuery, **kwargs):
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return

    lang = await get_user_language(uid)

    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    price = to_float(plan.get("price_rub", 0), 0.0)
    trust = await db.get_trust_score(uid)
    final_price, _ = apply_trust_discount(price, trust)
    final_price_int = int(round(final_price))  # noqa: RUF046

    text = translate(
        lang,
        "texts.p2p_payment_details",
        plan_name=plan.get("name", plan_id),
        amount=final_price_int,
        payment_card=Config.PAYMENT_CARD_NUMBER,
    )
    keyboard = [
        [
            {
                "text": translate(lang, "buttons.confirm_payment"),
                "callback_data": f"confirm_payment:p2p:{plan_id}:{uid}",
            }
        ],
        [
            {
                "text": translate(lang, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(CustomTariffState.waiting_for_confirm, F.data.startswith("custom:pay_p2p:"))
async def cmd_custom_show_p2p(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")
    if len(parts) < 3:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.wrong_user_error"),
            show_alert=True,
        )
        return

    data = await state.get_data()
    amount = to_int(data.get("custom_final_amount"), -1)
    plan_name = str(data.get("custom_plan_name") or " ").strip()
    if amount < 0:
        await state.clear()
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    text = translate(
        Config.DEFAULT_LANGUAGE,
        "texts.p2p_payment_details",
        plan_name=plan_name,
        amount=amount,
        payment_card=Config.PAYMENT_CARD_NUMBER,
    )
    keyboard = [
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.confirm_payment"),
                "callback_data": f"custom:confirm_payment:p2p:{uid}",
            }
        ],
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(F.data.startswith("confirm_payment:"))
async def cmd_confirm_payment(event: CallbackQuery, **kwargs: Any) -> None:
    parts = event.data.split(":")
    if len(parts) == 3:
        method = "p2p"
        plan_id = parts[1]
        raw_uid = parts[2]
    elif len(parts) >= 4:
        method = parts[1]
        plan_id = parts[2]
        raw_uid = parts[3]
    else:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(raw_uid)
    except ValueError:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_processing_error"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_processing_error"),
            show_alert=True,
        )
        return

    lang = await get_user_language(uid)

    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    st = await ensure_subscription_state(uid, notify_user_about_cleanup=True)
    if st.get("status") == "active" and not is_expiring_soon(st, Config.EXPIRY_ALERT_DAYS):
        await show_active_subscription_guard(event)
        return
    price = to_float(plan.get("price_rub", 0), 0.0)
    trust = await db.get_trust_score(uid)
    amount = max(0, int(round(apply_trust_discount(price, trust)[0])))  # noqa: RUF046
    payment_id = f"pay_{uid}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    payment_data = {
        "payment_id": payment_id,
        "user_id": uid,
        "plan_id": plan_id,
        "plan_type": "catalog",
        "plan_name": plan.get("name", plan_id),
        "amount": amount,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "payment_method": method,
    }
    added = await json_db.add_pending_for_user(uid, payment_data)
    if not added:
        await smart_answer(
            event,
            translate(lang, "texts.payment_request_already_exists"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await smart_answer(
        event,
        translate(lang, "texts.payment_request_received"),
        reply_markup=main_menu_keyboard(),
        delete_origin=True,
    )


@router.callback_query(F.data == "mysub")
async def cmd_mysub(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    panel_types = Features.available_panel_types()

    if await is_admin_user(user_id):
        user_data = await db.get_user_by_any_id(user_id)
        if not user_data:
            await db.add_user(user_id, force=True)
            user_data = await db.get_user_by_any_id(user_id)
        if user_data:
            internal_id = user_data.get("user_id", 0)
            if not user_data.get("has_subscription") or not user_data.get("vpn_url"):
                await _ensure_admin_subscription(internal_id)
                user_data = await db.get_user_by_any_id(user_id)
        admin_vpn_url = str(user_data.get("vpn_url", "") or "") if user_data else ""
        admin_sub_url = (
            build_subscription_url(admin_vpn_url) if panel_types["main"] and admin_vpn_url else ""
        )
        admin_json_url = (
            build_json_subscription_url(admin_vpn_url)
            if panel_types["json"] and admin_vpn_url
            else ""
        )
        if not admin_sub_url and not admin_json_url:
            await event.answer(
                translate(lang, "texts.buy_unavailable"),
                show_alert=True,
            )
            return
        text = translate(
            lang,
            "texts.admin_subscription_info",
            url=admin_sub_url,
            json_url=admin_json_url,
        )
        keyboard = kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.referral_system"),
                        "callback_data": "ref",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.client_setup"),
                        "callback_data": "client_setup",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.main"),
                        "callback_data": "start",
                    }
                ],
            ]
        )
        await smart_answer(event, text, reply_markup=keyboard, delete_origin=True)
        return

    user_data = await db.get_user_by_any_id(user_id)
    if user_data and user_data.get("is_mate"):
        mate_expiry = user_data.get("mate_expiry", "")
        mate_nickname = user_data.get("mate_nickname", "")
        mate_sub_id = user_data.get("mate_subscription_id", "")
        mate_url = (
            build_subscription_url(mate_sub_id) if mate_sub_id and panel_types["main"] else ""
        )
        mate_json_url = (
            build_json_subscription_url(mate_sub_id) if mate_sub_id and panel_types["json"] else ""
        )
        if not mate_url and not mate_json_url:
            await event.answer(
                translate(lang, "texts.buy_unavailable"),
                show_alert=True,
            )
            return
        mate_text = translate(
            lang,
            "texts.partner_sub_info",
            nickname=mate_nickname,
            plan_name=translate(lang, "texts.partner_plan_name"),
            expiry=mate_expiry or translate(lang, "texts.not_specified"),
            url=mate_url or translate(lang, "texts.not_specified"),
            json_url=mate_json_url or translate(lang, "texts.not_specified"),
        )
        keyboard = kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.partner_menu"),
                        "callback_data": "partner_dashboard",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.client_setup"),
                        "callback_data": "client_setup",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.main"),
                        "callback_data": "start",
                    }
                ],
            ]
        )
        await smart_answer(event, mate_text, reply_markup=keyboard, delete_origin=True)
        return

    state = await ensure_subscription_state(user_id, notify_user_about_cleanup=False)
    status = state.get("status")
    user_data = await db.get_user_by_any_id(user_id)

    if status in ("expired", "traffic_exhausted", "missing_on_panel") and state.get(
        "cleanup_success"
    ):
        await smart_answer(
            event,
            build_subscription_cleanup_message(
                status,
                trust_before=to_int(state.get("cleanup_trust_before"), 0),
                trust_after=to_int(state.get("cleanup_trust_after"), 0),
                trust_delta=to_int(state.get("cleanup_trust_delta"), 0),
                lang=lang,
            ),
            reply_markup=inactive_subscription_actions_keyboard(),
            delete_origin=True,
        )
        return

    if not user_data or not normalize_sub_id(user_data.get("vpn_url")):
        text = translate(lang, "texts.no_active_subscription")
        keyboard = kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.buy"),
                        "callback_data": "buy",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.main"),
                        "callback_data": "start",
                    }
                ],
            ]
        )
        await smart_answer(event, text, reply_markup=keyboard, delete_origin=True)
        return

    plan_text = user_data.get("plan_text", translate(lang, "texts.unknown_plan"))
    servers = get_user_plan_servers(user_data)
    ip_limit = to_int(user_data.get("ip_limit"), 0)
    traffic_gb = max(0.0, to_float(user_data.get("traffic_gb"), 0.0))
    extra_gb = max(0, to_int(user_data.get("extra_sub_gb"), 0))
    total_traffic_gb = traffic_gb + extra_gb
    sub_url = build_subscription_url(user_data.get("vpn_url")) if panel_types["main"] else ""
    json_sub_url = (
        build_json_subscription_url(user_data.get("vpn_url")) if panel_types["json"] else ""
    )
    trust = to_int(user_data.get("trust_score"), 0)
    disc = calculate_discount_percent(trust)

    if not sub_url and not json_sub_url:
        await event.answer(
            translate(lang, "texts.buy_unavailable"),
            show_alert=True,
        )
        return

    if status == "active":
        used_gb = to_float(state.get("used_gb"), 0.0)
        max_expiry = to_int(state.get("max_expiry"), 0)
        if max_expiry <= 0:
            expiry_str = str(user_data.get("expiry_sub_datatime") or "").strip()
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str)
                    max_expiry = int(expiry_dt.timestamp() * 1000)
                except Exception:  # noqa: BLE001, S110
                    pass
        if total_traffic_gb > 0:
            remaining = max(0.0, total_traffic_gb - used_gb)
            traffic_line = translate(
                lang,
                "texts.subscription_traffic_remaining",
                remaining_gb=f"{remaining:.1f}",
                total_gb=f"{total_traffic_gb:.0f}",
            )
        else:
            traffic_line = translate(lang, "texts.subscription_traffic_unlimited")
        expiry_date = (
            datetime.fromtimestamp(max_expiry / 1000, tz=timezone.utc).strftime("%d.%m.%Y %H:%M")
            if max_expiry > 0
            else translate(lang, "texts.not_specified")
        )
        text = translate(
            lang,
            "texts.subscription_active_details",
            plan_text=plan_text,
            traffic_line=traffic_line,
            ip_limit=ip_limit,
            servers=format_servers(servers),
            expiry_date=expiry_date,
            trust_score=trust,
            discount_percent=disc,
            sub_url=sub_url,
        )
        if json_sub_url:
            text += f"\n\n🔗 <b>JSON URL:</b>\n<code>{html.escape(json_sub_url)}</code>"
    else:
        text = translate(
            lang,
            "texts.subscription_inactive_details",
            plan_text=plan_text,
            ip_limit=ip_limit,
            traffic=format_traffic(total_traffic_gb, lang),
            servers=format_servers(servers),
            trust_score=trust,
            discount_percent=disc,
            sub_url=sub_url,
        )
        if json_sub_url:
            text += f"\n\n🔗 <b>JSON URL:</b>\n<code>{html.escape(json_sub_url)}</code>"

    rows: list[list[dict[str, str]]] = [
        [
            {
                "text": translate(lang, "buttons.referral_system"),
                "callback_data": "ref",
            }
        ],
        [
            {
                "text": translate(lang, "buttons.client_app_setup"),
                "callback_data": "client_setup",
            }
        ],
    ]
    if status == "active" and is_expiring_soon(state, Config.EXPIRY_ALERT_DAYS):
        rows.insert(
            0,
            [
                {
                    "text": translate(lang, "buttons.renew_subscription"),
                    "callback_data": "buy",
                }
            ],
        )
    rows.append(
        [
            {
                "text": translate(lang, "buttons.main"),
                "callback_data": "start",
            }
        ]
    )
    await smart_answer(event, text, reply_markup=kb(rows), delete_origin=True)


@router.callback_query(F.data == "client_setup")
async def cmd_client_setup(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    await db.add_user(user_id)
    lang = await get_user_language(user_id)
    setup_url = Config.SETUP_GUIDE_URL or "https://t.me/your_support_bot"
    app_url = Config.CLIENT_APP_URL or "https://t.me/your_support_bot"
    text = translate(
        lang,
        "texts.client_setup_guide",
        setup_guide_url=setup_url,
        client_app_url=app_url,
    )
    keyboard = [
        [
            {
                "text": translate(lang, "buttons.my_subscription"),
                "callback_data": "mysub",
            }
        ],
        [{"text": translate(lang, "buttons.main"), "callback_data": "start"}],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(F.data == "ref")
async def cmd_ref(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    if await is_admin_user(user_id):
        await event.answer(translate(lang, "texts.admin_ref_notice"), show_alert=True)
        return
    await db.add_user(user_id)
    ref_code = await db.ensure_ref_code(user_id)
    if not ref_code:
        await smart_answer(
            event,
            translate(lang, "texts.no_ref_code"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    user_data = await db.get_user_by_any_id(user_id)
    db_uid = user_data.get("user_id", 0) if user_data else 0
    total = await db.count_referrals(db_uid)
    paid = await db.count_referrals_paid(db_uid)
    link = get_ref_link(ref_code)
    text = translate(
        lang,
        "texts.referral_info",
        link=link,
        total_refs=total,
        paid_refs=paid,
        bonus_days=Config.REF_BONUS_DAYS,
    )
    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


@router.callback_query(F.data == "become_partner")
async def cmd_become_partner(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    await db.add_user(user_id)
    user_data = await db.get_user_by_any_id(user_id)
    if user_data and user_data.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.partner_already"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    if not await is_admin_user(user_id):  # noqa: SIM102
        if await block_if_pending_partner_application(event, user_id):
            return
    if not Config.PARTNER_ENABLED:
        await smart_answer(
            event,
            translate(lang, "texts.partner_disabled"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    text = translate(
        lang,
        "texts.partner_requirements_detailed",
        min_followers=Config.PARTNER_MIN_FOLLOWERS,
        min_avg_reach=Config.PARTNER_MIN_AVG_REACH,
        required_socials=", ".join(Config.required_socials_list()),
        terms_url=Config.PARTNER_TERMS_URL,
    )
    await smart_answer(
        event,
        text,
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.i_agree"),
                        "callback_data": "partner_terms",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.main"),
                        "callback_data": "start",
                    }
                ],
            ]
        ),
        delete_origin=True,
    )


@router.callback_query(F.data == "partner_terms")
async def cmd_partner_terms(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    if not await is_admin_user(user_id):  # noqa: SIM102
        if await block_if_pending_payment(event, user_id):
            return
    await db.add_user(user_id)
    user_data = await db.get_user_by_any_id(user_id)
    if user_data and user_data.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.partner_already"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    terms_url = Config.PARTNER_TERMS_URL
    text = translate(
        lang,
        "texts.partner_terms_page",
        terms_url=terms_url,
    )
    await state.clear()
    await smart_answer(
        event,
        text,
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.i_agree"),
                        "callback_data": "partner_start_application",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "start",
                    }
                ],
            ]
        ),
        delete_origin=True,
    )


@router.callback_query(F.data == "partner_start_application")
async def cmd_partner_start_application(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    await db.add_user(user_id)
    user_data = await db.get_user_by_any_id(user_id)
    if user_data and user_data.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.partner_already"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    if await block_if_pending_partner_application(event, user_id):
        return
    await state.set_state(PartnerApplicationState.waiting_for_followers)
    await smart_answer(
        event,
        translate(lang, "texts.partner_apply_followers_prompt"),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "cancel",
                    }
                ]
            ]
        ),
        delete_origin=True,
    )


@router.message(PartnerApplicationState.waiting_for_followers)
async def process_partner_followers_msg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    text = (message.text or "").strip()

    if is_cancel_text(text, lang):
        await state.clear()
        await smart_answer(
            message,
            translate(lang, "texts.partner_cancelled"),
            reply_markup=main_menu_keyboard(),
        )
        return

    try:
        followers = int(text)
    except (ValueError, TypeError):
        await message.answer(
            translate(lang, "texts.partner_invalid_followers"),
        )
        return

    if followers <= 0:
        await message.answer(
            translate(lang, "texts.partner_followers_too_low", min_followers=1),
        )
        return

    if followers < Config.PARTNER_MIN_FOLLOWERS:
        await message.answer(
            translate(
                lang,
                "texts.partner_followers_too_low",
                min_followers=Config.PARTNER_MIN_FOLLOWERS,
            ),
        )
        return

    await state.update_data(followers=followers)
    await state.set_state(PartnerApplicationState.waiting_for_social_links)
    await message.answer(
        translate(lang, "texts.partner_apply_social_links_prompt"),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "cancel",
                    }
                ]
            ]
        ),
    )


def _detect_socials_in_text(text: str) -> list[str]:
    lower = text.lower()
    found = []

    if "t.me" in lower or "telegram.me" in lower or "@" in lower:
        found.append("telegram")

    if "youtube.com" in lower or "youtu.be" in lower:
        found.append("youtube")

    if "tiktok.com" in lower:
        found.append("tiktok")

    return found


@router.message(PartnerApplicationState.waiting_for_social_links)
async def process_partner_social_links_msg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    text = (message.text or "").strip()

    if is_cancel_text(text, lang):
        await state.clear()
        await smart_answer(
            message,
            translate(lang, "texts.partner_cancelled"),
            reply_markup=main_menu_keyboard(),
        )
        return

    if not text or len(text) < 5:
        await message.answer(
            translate(lang, "texts.partner_empty_socials"),
        )
        return

    detected = _detect_socials_in_text(text)
    required = Config.required_socials_list()

    if not detected:
        await message.answer(
            translate(
                lang,
                "texts.partner_no_socials_found",
                required_socials=", ".join(required),
            ),
        )
        return

    has_any = any(social in detected for social in required)
    if not has_any:
        await message.answer(
            translate(
                lang,
                "texts.partner_missing_socials",
                missing=(", ".join(required)),
                detected=(", ".join(detected)),
            ),
        )
        return

    await state.update_data(social_links=text)
    await state.set_state(PartnerApplicationState.waiting_for_nickname)
    await message.answer(
        translate(lang, "texts.partner_apply_nickname_prompt"),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "cancel",
                    }
                ]
            ]
        ),
    )


@router.message(PartnerApplicationState.waiting_for_nickname)
async def process_partner_nickname_msg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    text = (message.text or "").strip()

    if is_cancel_text(text, lang):
        await state.clear()
        await smart_answer(
            message,
            translate(lang, "texts.partner_cancelled"),
            reply_markup=main_menu_keyboard(),
        )
        return

    nickname = text
    if not nickname:
        await message.answer(
            translate(lang, "texts.partner_nickname_empty"),
        )
        return
    if len(nickname) > 30:
        await message.answer(
            translate(lang, "texts.partner_nickname_invalid"),
        )
        return
    if not re.match(r"^[a-zA-Z0-9_]+$", nickname):
        await message.answer(
            translate(lang, "texts.partner_nickname_invalid_format"),
        )
        return

    await state.update_data(nickname=nickname)
    await state.set_state(PartnerApplicationState.waiting_for_period)
    await message.answer(
        translate(
            lang,
            "texts.partner_apply_period_prompt",
            min_months=Config.PARTNER_MIN_PERIOD_MONTHS,
            max_months=Config.PARTNER_MAX_PERIOD_MONTHS,
        ),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "cancel",
                    }
                ]
            ]
        ),
    )


@router.message(PartnerApplicationState.waiting_for_period)
async def process_partner_period_msg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    text = (message.text or "").strip()

    if is_cancel_text(text, lang):
        await state.clear()
        await smart_answer(
            message,
            translate(lang, "texts.partner_cancelled"),
            reply_markup=main_menu_keyboard(),
        )
        return

    try:
        period = int(text)
    except (ValueError, TypeError):
        await message.answer(
            translate(lang, "texts.partner_invalid_period"),
        )
        return

    if period < Config.PARTNER_MIN_PERIOD_MONTHS or period > Config.PARTNER_MAX_PERIOD_MONTHS:
        await message.answer(
            translate(
                lang,
                "texts.partner_period_out_of_range",
                min_months=Config.PARTNER_MIN_PERIOD_MONTHS,
                max_months=Config.PARTNER_MAX_PERIOD_MONTHS,
            ),
        )
        return

    await state.update_data(period_months=period)
    await state.set_state(PartnerApplicationState.waiting_for_bonus_type)
    await message.answer(
        translate(lang, "texts.partner_apply_bonus_type_prompt"),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "texts.partner_bonus_days"),
                        "callback_data": "partner_bonus:days",
                    }
                ],
                [
                    {
                        "text": translate(lang, "texts.partner_bonus_trust"),
                        "callback_data": "partner_bonus:trust",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "cancel",
                    }
                ],
            ]
        ),
    )


@router.callback_query(F.data.startswith("partner_bonus:"))
async def cmd_partner_bonus_type(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    bonus_type = (event.data or "").split(":", 1)[1]
    if bonus_type not in ("days", "trust"):
        await event.answer(
            translate(lang, "texts.partner_invalid_bonus_type"),
            show_alert=True,
        )
        return
    await state.update_data(bonus_type=bonus_type)
    if bonus_type == "days":
        await state.set_state(PartnerApplicationState.waiting_for_bonus_value)
        await smart_answer(
            event,
            translate(
                lang,
                "texts.partner_apply_bonus_value_days_prompt",
                min_days=Config.PARTNER_BONUS_DAYS_MIN,
                max_days=Config.PARTNER_BONUS_DAYS_MAX,
            ),
            reply_markup=kb(
                [
                    [
                        {
                            "text": translate(lang, "buttons.cancel"),
                            "callback_data": "cancel",
                        }
                    ]
                ]
            ),
            delete_origin=True,
        )
    else:
        await state.set_state(PartnerApplicationState.waiting_for_bonus_value)
        await smart_answer(
            event,
            translate(
                lang,
                "texts.partner_apply_bonus_value_trust_prompt",
                min_points=Config.PARTNER_TRUST_POINTS_MIN,
                max_points=Config.PARTNER_TRUST_POINTS_MAX,
            ),
            reply_markup=kb(
                [
                    [
                        {
                            "text": translate(lang, "buttons.cancel"),
                            "callback_data": "cancel",
                        }
                    ]
                ]
            ),
            delete_origin=True,
        )


@router.message(PartnerApplicationState.waiting_for_bonus_value)
async def process_partner_bonus_value_msg(message: Message, state: FSMContext):
    user_id = message.from_user.id
    lang = await get_user_language(user_id)
    text = (message.text or "").strip()

    if is_cancel_text(text, lang):
        await state.clear()
        await smart_answer(
            message,
            translate(lang, "texts.partner_cancelled"),
            reply_markup=main_menu_keyboard(),
        )
        return

    try:
        bonus_value = int(text)
    except (ValueError, TypeError):
        await message.answer(
            translate(lang, "texts.partner_invalid_bonus_value"),
        )
        return

    data = await state.get_data()
    bonus_type = data.get("bonus_type", "")
    if bonus_type == "days":
        if (
            bonus_value < Config.PARTNER_BONUS_DAYS_MIN
            or bonus_value > Config.PARTNER_BONUS_DAYS_MAX
        ):
            await message.answer(
                translate(
                    lang,
                    "texts.partner_bonus_days_out_of_range",
                    min_days=Config.PARTNER_BONUS_DAYS_MIN,
                    max_days=Config.PARTNER_BONUS_DAYS_MAX,
                ),
            )
            return
    elif bonus_type == "trust":  # noqa: SIM102
        if (
            bonus_value < Config.PARTNER_TRUST_POINTS_MIN
            or bonus_value > Config.PARTNER_TRUST_POINTS_MAX
        ):
            await message.answer(
                translate(
                    lang,
                    "texts.partner_bonus_trust_out_of_range",
                    min_points=Config.PARTNER_TRUST_POINTS_MIN,
                    max_points=Config.PARTNER_TRUST_POINTS_MAX,
                ),
            )
            return

    await state.update_data(bonus_value=bonus_value)
    await state.set_state(PartnerApplicationState.waiting_for_pd_consent)
    await message.answer(
        translate(lang, "texts.partner_apply_pd_consent_prompt"),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.i_agree"),
                        "callback_data": "partner_pd_yes",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "cancel",
                    }
                ],
            ]
        ),
    )


@router.callback_query(PartnerApplicationState.waiting_for_pd_consent, F.data == "partner_pd_yes")
async def cmd_partner_pd_yes(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    data = await state.get_data()
    followers = data.get("followers", 0)
    social_links = data.get("social_links", "")
    nickname = data.get("nickname", "")
    period_months = data.get("period_months", 1)
    bonus_type = data.get("bonus_type", "")
    bonus_value = data.get("bonus_value", 0)
    operation_id = await add_partner_operation(
        user_id,
        "partner_new",
        {
            "followers": followers,
            "social_links": social_links,
            "nickname": nickname,
            "period_months": period_months,
            "bonus_type": bonus_type,
            "bonus_value": bonus_value,
            "pd_consent": 1,
        },
    )
    if operation_id:
        await state.clear()
        await smart_answer(
            event,
            translate(lang, "texts.partner_application_submitted"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
    else:
        await state.clear()
        await smart_answer(
            event,
            translate(lang, "texts.partner_application_error"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )


@router.callback_query(PartnerApplicationState.waiting_for_pd_consent, F.data == "partner_pd_no")
async def cmd_partner_pd_no(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    await state.clear()
    await smart_answer(
        event,
        translate(lang, "texts.partner_pd_declined"),
        reply_markup=main_menu_keyboard(),
        delete_origin=True,
    )


@router.callback_query(F.data == "partner_dashboard")
async def cmd_partner_dashboard(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    user_data = await db.get_user_by_any_id(user_id)
    if not user_data or not user_data.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.not_a_partner"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    total_refs = await db.count_partner_referrals(user_id)
    paid_refs = await db.count_partner_referrals_paid(user_id)
    balance = user_data.get("mate_balance", 0.0)
    commission_total = user_data.get("mate_commission_total", 0.0)
    expiry = user_data.get("mate_expiry", "")
    nickname = user_data.get("mate_nickname", "")
    ref_link = ""
    ref_code = user_data.get("mate_ref_link_code", "")
    if ref_code and BOT_USERNAME:
        ref_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    conversion_rate = round((paid_refs / total_refs * 100) if total_refs > 0 else 0, 2)
    avg_commission_per_paid = round(commission_total / paid_refs if paid_refs > 0 else 0, 2)
    text = translate(
        lang,
        "texts.partner_dashboard_stats",
        nickname=nickname,
        total_refs=total_refs,
        paid_refs=paid_refs,
        conversion_rate=conversion_rate,
        balance=balance,
        commission_total=commission_total,
        avg_commission_per_paid=avg_commission_per_paid,
        expiry=expiry or translate(lang, "texts.not_specified"),
        ref_link=ref_link,
        commission_percent=Config.PARTNER_COMMISSION_PERCENT,
    )
    rows = [
        [
            {
                "text": translate(lang, "buttons.partner_renew"),
                "callback_data": "partner_renew",
            }
        ],
        [
            {
                "text": translate(lang, "buttons.withdraw"),
                "callback_data": "partner_withdraw",
            }
        ],
        [
            {
                "text": translate(lang, "buttons.main"),
                "callback_data": "start",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(rows), delete_origin=True)


@router.callback_query(F.data == "partner_renew")
async def partner_renew(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    if not await is_admin_user(user_id):  # noqa: SIM102
        if await block_if_pending_payment(event, user_id):
            return
    user_data = await db.get_user_by_any_id(user_id)
    if not user_data or not user_data.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.not_a_partner"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    period_months = user_data.get("mate_period_months", 1)
    price = period_months * 1000
    text = translate(
        lang,
        "texts.partner_renew_prompt",
        months=period_months,
        price=price,
    )
    await smart_answer(
        event,
        text,
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.i_agree"),
                        "callback_data": f"partner_renew_confirm:{period_months}",
                    }
                ],
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "partner_dashboard",
                    }
                ],
            ]
        ),
        delete_origin=True,
    )


@router.callback_query(F.data.startswith("partner_renew_confirm:"))
async def partner_renew_confirm(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    if not await is_admin_user(user_id):  # noqa: SIM102
        if await block_if_pending_payment(event, user_id):
            return
    try:
        months = int((event.data or "").split(":", 1)[1])
    except (ValueError, TypeError):
        await event.answer(translate(lang, "texts.invalid_period"), show_alert=True)
        return
    user_data = await db.get_user_by_any_id(user_id)
    if not user_data or not user_data.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.not_a_partner"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    price = months * 1000
    operation_id = await add_partner_operation(
        user_id,
        "partner_renewal",
        {
            "months": months,
            "period_months": months,
            "amount": price,
        },
    )
    if not operation_id:
        await smart_answer(
            event,
            translate(lang, "texts.payment_request_already_exists"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    payment_data = {
        "payment_id": operation_id,
        "user_id": user_id,
        "plan_id": "partner_renewal",
        "plan_type": "partner_renewal",
        "plan_name": f"Partner Renewal {months}mo",
        "amount": price,
        "currency": "RUB",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
        "payment_method": "partner_renewal",
        "partner_data": {
            "months": months,
            "period_months": months,
            "amount": price,
        },
    }
    await json_db.add_pending_for_user(user_id, payment_data)
    await smart_answer(
        event,
        translate(lang, "texts.partner_renew_payment_received", price=price),
        reply_markup=main_menu_keyboard(),
        delete_origin=True,
    )


@router.callback_query(F.data == "partner_withdraw")
async def cmd_partner_withdraw(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    if not await is_admin_user(user_id):  # noqa: SIM102
        if await block_if_pending_payment(event, user_id):
            return
    user_data = await db.get_user_by_any_id(user_id)
    if not user_data or not user_data.get("is_mate"):
        await smart_answer(
            event,
            translate(lang, "texts.not_a_partner"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    balance = user_data.get("mate_balance", 0.0)
    if balance <= 0:
        await smart_answer(
            event,
            translate(lang, "texts.partner_no_balance"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await state.set_state(PartnerWithdrawalState.waiting_for_amount)
    await smart_answer(
        event,
        translate(lang, "texts.partner_withdraw_prompt", balance=balance),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "partner_dashboard",
                    }
                ]
            ]
        ),
        delete_origin=True,
    )


@router.callback_query(PartnerWithdrawalState.waiting_for_amount)
async def process_partner_withdrawal_amount(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    try:
        amount = float(event.data or "0")
    except (ValueError, TypeError):
        await event.answer(
            translate(lang, "texts.partner_invalid_amount"),
            show_alert=True,
        )
        return
    user_data = await db.get_user_by_any_id(user_id)
    balance = user_data.get("mate_balance", 0.0) if user_data else 0.0
    if amount <= 0:
        await event.answer(
            translate(lang, "texts.partner_amount_positive"),
            show_alert=True,
        )
        return
    if amount > balance:
        await event.answer(
            translate(lang, "texts.partner_insufficient_balance"),
            show_alert=True,
        )
        return
    await state.update_data(withdraw_amount=amount)
    await state.set_state(PartnerWithdrawalState.waiting_for_phone)
    await smart_answer(
        event,
        translate(lang, "texts.partner_withdraw_phone_prompt"),
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(lang, "buttons.cancel"),
                        "callback_data": "partner_dashboard",
                    }
                ]
            ]
        ),
        delete_origin=True,
    )


@router.message(PartnerWithdrawalState.waiting_for_phone)
async def process_partner_withdrawal_phone(event: Message, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    phone = (event.text or "").strip()
    if is_cancel_text(phone, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not phone:
        await event.answer(
            translate(lang, "texts.partner_withdraw_phone_empty"),
        )
        return
    await state.update_data(withdraw_phone=phone)
    await state.set_state(PartnerWithdrawalState.waiting_for_fio)
    await event.answer(
        translate(lang, "texts.partner_withdraw_fio_prompt"),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(PartnerWithdrawalState.waiting_for_fio)
async def process_partner_withdrawal_fio(event: Message, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    fio = (event.text or "").strip()
    if is_cancel_text(fio, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not fio:
        await event.answer(
            translate(lang, "texts.partner_withdraw_fio_empty"),
        )
        return
    await state.update_data(withdraw_fio=fio)
    await state.set_state(PartnerWithdrawalState.waiting_for_bank)
    await event.answer(
        translate(lang, "texts.partner_withdraw_bank_prompt"),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(PartnerWithdrawalState.waiting_for_bank)
async def process_partner_withdrawal_bank(event: Message, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    bank = (event.text or "").strip()
    if is_cancel_text(bank, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not bank:
        await event.answer(
            translate(lang, "texts.partner_withdraw_bank_empty"),
        )
        return
    data = await state.get_data()
    amount = data.get("withdraw_amount", 0)
    phone = data.get("withdraw_phone", "")
    fio = data.get("withdraw_fio", "")
    operation_id = await add_partner_operation(
        user_id,
        "partner_withdrawal",
        {
            "amount": amount,
            "phone": phone,
            "fio": fio,
            "bank": bank,
        },
    )
    await state.clear()
    if operation_id:
        payment_data = {
            "payment_id": operation_id,
            "user_id": user_id,
            "plan_id": "partner_withdrawal",
            "plan_type": "withdrawal",
            "plan_name": f"Partner Withdrawal #{operation_id[:12]}",
            "amount": amount,
            "currency": "RUB",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "payment_method": "partner_balance",
            "partner_data": {
                "amount": amount,
                "phone": phone,
                "fio": fio,
                "bank": bank,
            },
        }
        await json_db.add_pending_for_user(user_id, payment_data)
        await event.answer(
            translate(lang, "texts.partner_withdraw_submitted", amount=amount),
            reply_markup=main_menu_keyboard(),
        )
    else:
        await event.answer(
            translate(lang, "texts.partner_withdraw_error"),
            reply_markup=main_menu_keyboard(),
        )


def build_partner_op_text(
    op: dict[str, Any], lang: str = Config.DEFAULT_LANGUAGE, tg_id: int = 0
) -> str:
    op_id = op.get("operation_id", "")
    short_op_id = op_id[:12]
    op_type = op.get("op_type", "")
    uid = op.get("user_id", 0)
    partner_name = str(op.get("partner_name", uid))
    tg_id_str = f" (TG: {tg_id})" if tg_id > 0 else ""
    if op_type == "partner_new":
        bonus_type_raw = str(op.get("bonus_type", ""))
        if bonus_type_raw == "days":
            bonus_type_label = translate(lang, "texts.partner_bonus_days_label")
        elif bonus_type_raw == "trust":
            bonus_type_label = translate(lang, "texts.partner_bonus_trust_label")
        else:
            bonus_type_label = bonus_type_raw
        return translate(
            lang,
            "texts.partner_op_item_new",
            operation_id=short_op_id,
            user_id=uid,
            tg_id=tg_id_str,
            nickname=op.get("nickname", ""),
            followers=op.get("followers", 0),
            social_links=op.get("social_links", ""),
            period_months=op.get("period_months", 0),
            bonus_type=bonus_type_label,
            bonus_value=op.get("bonus_value", 0),
            partner_name=partner_name,
        )
    if op_type == "partner_renewal":
        return translate(
            lang,
            "texts.partner_op_item_renewal",
            operation_id=short_op_id,
            user_id=uid,
            tg_id=tg_id_str,
            partner_name=partner_name,
            months=op.get("months", 0),
            price=op.get("amount", 0),
        )
    if op_type == "partner_withdrawal":
        return translate(
            lang,
            "texts.partner_op_item_withdrawal",
            operation_id=short_op_id,
            user_id=uid,
            tg_id=tg_id_str,
            partner_name=partner_name,
            amount=op.get("amount", 0),
            phone=op.get("phone", ""),
            fio=op.get("fio", ""),
            bank=op.get("bank", ""),
            balance=op.get("balance", 0.0),
            total_refs=op.get("total_refs", 0),
            paid_refs=op.get("paid_refs", 0),
            commission_total=op.get("commission_total", 0.0),
            web_registered_at=op.get("web_registered_at", "N/A"),
            web_last_login=op.get("web_last_login", "N/A"),
            mate_period_months=op.get("mate_period_months", 0),
            ref_code=op.get("ref_code", "N/A"),
        )
    return ""


def build_partner_op_keyboard(
    op_id: str, op_type: str, lang: str = Config.DEFAULT_LANGUAGE
) -> InlineKeyboardMarkup:
    if op_type == "partner_withdrawal":
        accept_text = translate(lang, "buttons.partner_withdraw_accept_btn")
        reject_text = translate(lang, "buttons.partner_withdraw_reject_btn")
    else:
        accept_text = translate(lang, "buttons.partner_accept_btn")
        reject_text = translate(lang, "buttons.partner_reject_btn")
    return kb(
        [
            [
                {
                    "text": accept_text,
                    "callback_data": f"partner_accept_op:{op_id}",
                },
                {
                    "text": reject_text,
                    "callback_data": f"partner_reject_op:{op_id}",
                },
            ]
        ]
    )


@router.callback_query(F.data == "partner_operations")
async def cmd_partner_operations(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    operations = await get_pending_partner_operations()
    if not operations:
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.partner_operations_empty"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    lang = Config.DEFAULT_LANGUAGE
    type_order = {"partner_new": 0, "partner_renewal": 1, "partner_withdrawal": 2}
    operations.sort(key=lambda o: type_order.get(o.get("op_type", ""), 99))
    await smart_answer(
        event,
        translate(lang, "texts.partner_operations_title"),
        delete_origin=True,
    )
    partner_uids = [to_int(op.get("user_id"), 0) for op in operations]
    users_by_tgid: dict[int, dict[str, Any]] = {}
    if partner_uids:
        users = await db.get_users_by_telegram_ids(partner_uids)
        users_by_tgid = {u["telegram_id"]: u for u in users}
    withdrawal_uids = [
        to_int(op.get("user_id"), 0)
        for op in operations
        if op.get("op_type") == "partner_withdrawal"
    ]
    refs_counts = await db.count_referrals_batch(
        [users_by_tgid.get(uid, {}).get("user_id", uid) for uid in withdrawal_uids]
    )
    refs_paid_counts = await db.count_referrals_paid_batch(
        [users_by_tgid.get(uid, {}).get("user_id", uid) for uid in withdrawal_uids]
    )
    for op in operations:
        op_id = op.get("operation_id", "")
        op_type = op.get("op_type", "")
        uid = to_int(op.get("user_id"), 0)
        user_data = users_by_tgid.get(uid)
        partner_name = user_data.get("mate_nickname", str(uid)) if user_data else str(uid)
        enriched_op = {
            **op,
            "partner_name": partner_name,
        }
        internal_uid = user_data.get("user_id", uid) if user_data else uid
        if op_type == "partner_withdrawal":
            enriched_op["balance"] = user_data.get("mate_balance", 0.0) if user_data else 0.0
            enriched_op["total_refs"] = refs_counts.get(internal_uid, 0)
            enriched_op["paid_refs"] = refs_paid_counts.get(internal_uid, 0)
            enriched_op["commission_total"] = (
                user_data.get("mate_commission_total", 0.0) if user_data else 0.0
            )
            enriched_op["web_registered_at"] = (
                user_data.get("web_registered_at", "") if user_data else ""
            )
            enriched_op["web_last_login"] = user_data.get("web_last_login", "") if user_data else ""
            enriched_op["mate_period_months"] = (
                user_data.get("mate_period_months", 0) if user_data else 0
            )
            enriched_op["ref_code"] = user_data.get("ref_code", "") if user_data else ""
        text = build_partner_op_text(
            enriched_op, lang, tg_id=user_data.get("telegram_id", 0) if user_data else 0
        )
        markup = build_partner_op_keyboard(op_id, op_type, lang)
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery) and event.message:
            await event.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("partner_accept_op:"))
async def cmd_partner_accept_op(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    op_id = (event.data or "").split(":", 1)[1]
    op = await claim_partner_operation_or_alert(event, op_id, "accept")
    if not op:
        return
    uid = to_int(op.get("user_id"), 0)
    op_type = str(op.get("op_type", ""))
    if op_type == "partner_new":
        await _handle_partner_new_accept(event, op, uid)
    elif op_type == "partner_renewal":
        await _handle_partner_renewal_accept(event, op, uid)
    else:
        await _handle_partner_withdrawal_accept(event, op, uid)


@router.callback_query(F.data.startswith("partner_reject_op:"))
async def cmd_partner_reject_op(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    op_id = (event.data or "").split(":", 1)[1]
    op = await claim_partner_operation_or_alert(event, op_id, "reject")
    if not op:
        return
    uid = to_int(op.get("user_id"), 0)
    op_type = str(op.get("op_type", ""))
    if op_type == "partner_new":
        await _handle_partner_new_reject(event, op, uid)
    elif op_type == "partner_renewal":
        await _handle_partner_renewal_reject(event, op, uid)
    else:
        await _handle_partner_withdrawal_reject(event, op, uid)


async def _handle_partner_new_accept(event: CallbackQuery, op: dict[str, Any], uid: int) -> None:
    lang = Config.DEFAULT_LANGUAGE
    logger.info(f"Партнёрская заявка accept: uid={uid}, op_id={op.get('operation_id')}")
    nickname = str(op.get("nickname", ""))
    social_links = str(op.get("social_links", ""))
    followers = to_int(op.get("followers", 0))
    period_months = to_int(op.get("period_months", 1))
    bonus_type = str(op.get("bonus_type", ""))
    bonus_value = to_int(op.get("bonus_value", 0))
    sanitized = re.sub(r"[^a-z0-9_-]", "", nickname.lower().replace(" ", "_"))
    ref_code = f"mate_{sanitized}"
    existing = await db.get_user_by_any_id(uid)
    if (
        existing
        and existing.get("mate_ref_link_code")
        and existing.get("mate_ref_link_code") != ref_code
    ):
        ref_code = f"mate_{sanitized}_{uid}"
    success = await db.set_user_as_partner(
        uid,
        nickname=nickname,
        social_links=social_links,
        followers=followers,
        avg_reach=0,
        period_months=period_months,
        bonus_type=bonus_type,
        bonus_value=bonus_value,
        ref_link_code=ref_code,
    )
    if success:
        expiry_dt = datetime.now(timezone.utc) + timedelta(days=period_months * 30)
        expiry_display = expiry_dt.strftime("%d.%m.%Y")
        expiry_sub_datatime = expiry_dt.strftime("%Y-%m-%d %H:%M:%S")
        try:
            base_email = f"mate_{uid}_{sanitized}@{Config.VPN_NAME.lower()}.com"
            partner_sub_id = existing.get("mate_subscription_id", "") if existing else ""
            if not partner_sub_id:
                partner_sub_id = nickname
            inbound_ids = await panel.get_matching_inbound_ids(None)
            if inbound_ids:
                existing_client = await panel.get_client_by_email(base_email)
                if existing_client:
                    await panel.delete_client(base_email)
                client_data = await panel.create_client(
                    email=base_email,
                    limit_ip=0,
                    total_gb=0,
                    days=period_months * 30,
                    tg_id=uid,
                    inbound_ids=inbound_ids,
                    sub_id=partner_sub_id,
                )
                if not client_data and partner_sub_id == nickname:
                    partner_sub_id = f"{nickname}_{uid}"
                    client_data = await panel.create_client(
                        email=base_email,
                        limit_ip=0,
                        total_gb=0,
                        days=period_months * 30,
                        tg_id=uid,
                        inbound_ids=inbound_ids,
                        sub_id=partner_sub_id,
                    )
                if client_data:
                    sub_id = normalize_sub_id(client_data.get("subId", "")) or partner_sub_id
                    await db.update_partner_subscription(
                        uid, subscription_id=sub_id or "", expiry=expiry_display
                    )
                    await db.set_subscription(
                        uid,
                        plan_text=translate(Config.DEFAULT_LANGUAGE, "texts.partner_plan_name"),
                        ip_limit=0,
                        vpn_url=sub_id or "",
                        traffic_gb=0,
                        subscription_id=sub_id or "",
                        expiry_sub_datatime=expiry_sub_datatime,
                    )
                    logger.info(f"✅ VPN-подписка создана для партнёра {uid}: {sub_id}")
                else:
                    logger.warning(f"Не удалось создать VPN-клиента для партнёра {uid}")
            else:
                logger.warning(f"Нет inbound'ов для создания VPN партнёра {uid}")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка создания VPN для партнёра {uid}: {e}")
        finalized = await finalize_partner_operation(
            op.get("operation_id", ""),
            get_event_user_id(event) or 0,
            "accept",
            "accepted",
        )
        if not finalized:
            logger.warning(f"Не удалось финализировать операцию {op.get('operation_id')}")
        await event.answer(translate(lang, "texts.partner_accepted"), show_alert=True)
        await append_payment_decision_label(
            event.message,
            translate(lang, "texts.partner_decision_accepted"),
        )
        try:
            await safe_send_message(
                bot,
                uid,
                translate(
                    lang,
                    "texts.partner_accepted_notification",
                    nickname=nickname,
                ),
            )
        except Exception:  # noqa: BLE001, S110
            pass
    else:
        await event.answer(translate(lang, "texts.partner_accept_error"), show_alert=True)


async def _handle_partner_new_reject(event: CallbackQuery, op: dict[str, Any], uid: int) -> None:
    lang = Config.DEFAULT_LANGUAGE
    finalized = await finalize_partner_operation(
        op.get("operation_id", ""),
        get_event_user_id(event) or 0,
        "reject",
        "rejected",
    )
    if not finalized:
        logger.warning(f"Не удалось финализировать операцию {op.get('operation_id')}")
    await event.answer(translate(lang, "texts.partner_rejected"), show_alert=True)
    await append_payment_decision_label(
        event.message,
        translate(lang, "texts.partner_decision_rejected"),
    )
    try:
        await safe_send_message(
            bot,
            uid,
            translate(lang, "texts.partner_rejected_notification"),
        )
    except Exception:  # noqa: BLE001, S110
        pass


async def _handle_partner_renewal_accept(
    event: CallbackQuery, op: dict[str, Any], uid: int
) -> None:
    lang = Config.DEFAULT_LANGUAGE
    months = to_int(op.get("period_months", 0)) or to_int(op.get("months", 0))
    if months <= 0:
        months = 1
    user_data = await db.get_user_by_any_id(uid)
    if not user_data or not user_data.get("is_mate"):
        await finalize_partner_operation(
            op.get("operation_id", ""),
            get_event_user_id(event) or 0,
            "accept",
            "rejected",
        )
        await event.answer(translate(lang, "texts.not_a_partner_alert"), show_alert=True)
        return
    current_expiry_str = user_data.get("mate_expiry", "")
    if current_expiry_str:
        try:
            current_expiry = datetime.strptime(current_expiry_str, "%d.%m.%Y")  # noqa: DTZ007
        except Exception:  # noqa: BLE001
            current_expiry = datetime.now(timezone.utc)
    else:
        current_expiry = datetime.now(timezone.utc)
    if current_expiry <= datetime.now(timezone.utc):  # noqa: PLR1730
        current_expiry = datetime.now(timezone.utc)
    new_expiry = current_expiry + timedelta(days=months * 30)
    await db.update_user_by_telegram_id(
        uid,
        force=True,
        mate_expiry=new_expiry.strftime("%d.%m.%Y"),
    )
    finalized = await finalize_partner_operation(
        op.get("operation_id", ""),
        get_event_user_id(event) or 0,
        "accept",
        "accepted",
    )
    if not finalized:
        logger.warning(f"Не удалось финализировать операцию {op.get('operation_id')}")
    try:
        await safe_send_message(
            bot,
            uid,
            translate(
                lang,
                "texts.partner_renewal_accepted",
                months=months,
                new_expiry=new_expiry.strftime("%d.%m.%Y"),
            ),
        )
    except Exception:  # noqa: BLE001, S110
        pass
    await event.answer(
        translate(lang, "texts.payment_accept_alert", payment_id=op.get("operation_id", "")),
        show_alert=True,
    )
    await append_payment_decision_label(
        event.message,
        translate(lang, "texts.payment_decision_accepted"),
    )


async def _handle_partner_renewal_reject(
    event: CallbackQuery, op: dict[str, Any], uid: int
) -> None:
    lang = Config.DEFAULT_LANGUAGE
    finalized = await finalize_partner_operation(
        op.get("operation_id", ""),
        get_event_user_id(event) or 0,
        "reject",
        "rejected",
    )
    if not finalized:
        logger.warning(f"Не удалось финализировать операцию {op.get('operation_id')}")
    await event.answer(translate(lang, "texts.partner_rejected"), show_alert=True)
    await append_payment_decision_label(
        event.message,
        translate(lang, "texts.partner_decision_rejected"),
    )


async def _handle_partner_withdrawal_accept(
    event: CallbackQuery, op: dict[str, Any], uid: int
) -> None:
    lang = Config.DEFAULT_LANGUAGE
    amount = to_float(op.get("amount", 0))
    finalized = await finalize_partner_operation(
        op.get("operation_id", ""),
        get_event_user_id(event) or 0,
        "accept",
        "accepted",
    )
    if not finalized:
        logger.warning(f"Не удалось финализировать операцию {op.get('operation_id')}")
    await db.update_partner_balance(uid, -amount)
    await event.answer(translate(lang, "texts.partner_withdraw_accepted"), show_alert=True)
    await append_payment_decision_label(
        event.message,
        translate(lang, "texts.partner_decision_accepted"),
    )
    try:
        await safe_send_message(
            bot,
            uid,
            translate(
                lang,
                "texts.partner_withdraw_accepted_notification",
                amount=amount,
            ),
        )
    except Exception:  # noqa: BLE001, S110
        pass


async def _handle_partner_withdrawal_reject(
    event: CallbackQuery, op: dict[str, Any], uid: int
) -> None:
    lang = Config.DEFAULT_LANGUAGE
    amount = to_float(op.get("amount", 0))
    finalized = await finalize_partner_operation(
        op.get("operation_id", ""),
        get_event_user_id(event) or 0,
        "reject",
        "rejected",
    )
    if not finalized:
        logger.warning(f"Не удалось финализировать операцию {op.get('operation_id')}")
    await event.answer(translate(lang, "texts.partner_withdraw_rejected"), show_alert=True)
    await append_payment_decision_label(
        event.message,
        translate(lang, "texts.partner_decision_rejected"),
    )
    try:
        await safe_send_message(
            bot,
            uid,
            translate(
                lang,
                "texts.partner_withdraw_rejected_notification",
                amount=amount,
            ),
        )
    except Exception:  # noqa: BLE001, S110
        pass


async def claim_partner_operation_or_alert(
    event: CallbackQuery, operation_id: str, action: str
) -> dict[str, Any] | None:
    admin_id = get_event_user_id(event) or 0
    claimed = await claim_partner_operation(operation_id, admin_id, action)
    if not claimed:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.partner_operation_claim_error"),
            show_alert=True,
        )
        return None
    return claimed


async def check_partner_expiry_notifications() -> None:
    while True:
        try:
            partner_ids = await db.get_mate_user_ids()
            for uid in partner_ids:
                user_data = await db.get_user_by_any_id(uid)
                if not user_data:
                    continue
                expiry = user_data.get("mate_expiry", "")
                if not expiry:
                    continue
                try:
                    expiry_dt = datetime.strptime(expiry, "%d.%m.%Y")  # noqa: DTZ007
                except Exception:  # noqa: BLE001, S112
                    continue
                now = datetime.now(timezone.utc)
                grace_days = Config.PARTNER_EXPIRY_GRACE_DAYS
                if expiry_dt > now and (expiry_dt - now).days <= grace_days:
                    try:
                        await safe_send_message(
                            bot,
                            uid,
                            translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.partner_expiry_soon",
                                expiry_date=expiry_dt.strftime("%d.%m.%Y"),
                                grace_days=grace_days,
                            ),
                        )
                    except Exception:  # noqa: BLE001, S110
                        pass
                elif expiry_dt <= now:
                    try:
                        await _deactivate_partner(uid)
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"Ошибка деактивации партнёра {uid}: {e}")
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.error(f"check_partner_expiry_notifications: {e}")
        await asyncio.sleep(SECONDS_IN_DAY)


async def _deactivate_partner(uid: int) -> None:
    logger.info(f"Деактивация партнёрства для user {uid}")
    user_data = await db.get_user_by_any_id(uid)
    if not user_data:
        return
    db_uid = user_data.get("user_id", 0)
    try:
        await safe_send_message(
            bot,
            uid,
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.partner_expiry_expired",
            ),
        )
    except Exception:  # noqa: BLE001, S110
        pass
    vpn_url = user_data.get("vpn_url", "")
    if vpn_url and normalize_sub_id(vpn_url):
        try:
            await panel.delete_client(get_user_panel_email(db_uid, user_data))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Не удалось удалить VPN для деактивированного партнёра {uid}: {e}")
    await db.remove_subscription(db_uid)
    await db.update_user_by_telegram_id(
        uid,
        force=True,
        is_mate=0,
        mate_nickname="",
        mate_social_links="",
        mate_followers=0,
        mate_avg_reach=0,
        mate_period_months=0,
        mate_bonus_type="",
        mate_bonus_value=0,
        mate_ref_link_code="",
        mate_subscription_id="",
        mate_expiry="",
        mate_balance=0.0,
        mate_commission_total=0.0,
        mate_withdrawal_requests="[]",
        mate_status="",
    )
    logger.info(f"✅ Партнёрство деактивировано для user {uid}")


@router.callback_query(F.data == "pay_await")
async def cmd_pay_await(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    payments = await json_db.read_all()
    pending = [p for p in payments if p.get("status") == "pending"]
    if not pending:
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.pay_await_empty"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.pay_await_title"),
        delete_origin=True,
    )
    user_ids = [to_int(p.get("user_id"), 0) for p in pending if to_int(p.get("user_id"), 0) > 0]
    users_by_id: dict[int, dict[str, Any]] = {}
    if user_ids:
        users = await db.get_users_by_ids(user_ids)
        users_by_id = {u["user_id"]: u for u in users}
    for p in pending:
        pid = str(p.get("payment_id", ""))
        if not pid:
            continue
        uid = to_int(p.get("user_id"), 0)
        tg_id = 0
        if uid > 0:
            user_data = users_by_id.get(uid)
            if user_data:
                tg_id = to_int(user_data.get("telegram_id", 0), 0)
        text = build_pending_payment_text(p, tg_id=tg_id)
        markup = build_pending_payment_keyboard(pid)
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery) and event.message:
            await event.message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("pay_await_accept:"))
async def cmd_pay_await_accept(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    payment_id = event.data.split(":", 1)[1]
    payment = await claim_pending_payment_or_alert(event, payment_id, "accept")
    if not payment:
        return
    plan_type = str(payment.get("plan_type", "catalog"))
    plan_id = str(payment.get("plan_id", ""))
    if plan_type == "custom":
        plan, error = build_custom_plan_from_payment(payment)
    else:
        plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await rollback_claimed_payment(
            event,
            payment_id,
            "accept",
            error_message=error
            or translate(Config.DEFAULT_LANGUAGE, "texts.plan_not_found_during_payment"),
        )
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.plan_not_found_alert",
                error=error or translate(Config.DEFAULT_LANGUAGE, "texts.plan_not_found"),
            ),
            show_alert=True,
        )
        return
    plan_name = str(payment.get("plan_name") or "").strip() or plan.get("name", plan_id or "custom")
    paid_amount = to_float(payment.get("amount"), 0.0)
    resolved = await resolve_user_from_payment(payment)
    if not resolved:
        raw_uid = to_int(payment.get("user_id"), 0)
        uid = await resolve_tg_id(raw_uid) if raw_uid > 0 else 0
        await rollback_claimed_payment(
            event,
            payment_id,
            "accept",
            error_message=translate(Config.DEFAULT_LANGUAGE, "texts.invalid_payment_user_error"),
        )
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.invalid_payment_user_alert",
            ),
            show_alert=True,
        )
        logger.error(
            f"cmd_pay_await_accept: пользователь не найден для платежа {payment_id}, uid={uid}"
        )
        return
    uid = resolved.telegram_id
    user_data = resolved.user_data
    ref_by = user_data.get("ref_by") if user_data else None
    ref_rewarded = user_data.get("ref_rewarded") if user_data else None
    bonus_for_user = Config.REF_BONUS_DAYS if ref_by and not ref_rewarded else 0
    trust_before = await db.get_trust_score(uid)
    st = await get_subscription_state(uid)
    if st.get("status") == "active":
        vpn_url = await renew_subscription(
            uid, plan, extra_days=bonus_for_user, paid_amount=paid_amount
        )
    else:
        vpn_url = await create_subscription(
            uid, plan, extra_days=bonus_for_user, paid_amount=paid_amount
        )
    if vpn_url:
        trust_after = await db.get_trust_score(uid)
        trust_delta = trust_after - trust_before
        trust_line = build_trust_change_line(trust_delta, trust_before, trust_after)
        await db.set_has_subscription(uid)
        finalized = await finalize_claimed_payment_or_alert(event, payment_id, "accept", "accepted")
        if not finalized:
            return
        if not await verify_payment_final_status(payment_id, "accepted"):
            logger.error(f"Платеж {payment_id} не в 'accepted' после финализации")
            await event.answer(
                translate(Config.DEFAULT_LANGUAGE, "texts.payment_processed_warning"),
                show_alert=True,
            )
            return
        bonus_text = (
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.payment_bonus_line",
                bonus_days=format_duration(bonus_for_user, Config.DEFAULT_LANGUAGE),
            )
            if bonus_for_user > 0
            else ""
        )
        user_lang = await get_user_language(uid)
        setup_keyboard = build_setup_keyboard(user_lang)
        try:
            await notify_user(
                uid,
                translate(
                    user_lang,
                    "texts.payment_accepted_notification",
                    plan_name=plan_name,
                    ip_limit=plan.get("ip_limit", 0),
                    traffic=format_traffic(plan.get("traffic_gb", 0), user_lang),
                    servers=format_servers(plan.get("servers")),
                    duration=format_duration(
                        int(plan.get("duration_days", 30)) + bonus_for_user, user_lang
                    ),
                    bonus_text=bonus_text,
                    trust_change_line=trust_line,
                    vpn_url=vpn_url,
                ),
                reply_markup=setup_keyboard,
            )
        except Exception:  # noqa: BLE001, S110
            pass
        if ref_by and not ref_rewarded:
            fresh = await db.get_user_by_any_id(uid)
            if fresh and not fresh.get("ref_rewarded"):
                await reward_referrer(ref_by, Config.REF_BONUS_DAYS)
                await db.mark_ref_rewarded(uid)
        if ref_by:
            referrer = await db.get_user_by_any_id(ref_by)
            if referrer and referrer.get("is_mate"):
                commission = round(paid_amount * Config.PARTNER_COMMISSION_PERCENT / 100, 2)
                if commission > 0:
                    await db.update_partner_balance(ref_by, commission)
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.payment_accept_alert",
                payment_id=payment_id,
            ),
            show_alert=True,
        )
        await append_payment_decision_label(
            event.message,
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_decision_accepted"),
        )
    else:
        await rollback_claimed_payment(
            event,
            payment_id,
            "accept",
            error_message=translate(
                Config.DEFAULT_LANGUAGE, "texts.vpn_subscription_create_failed"
            ),
        )
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.payment_vpn_create_error",
                payment_id=payment_id,
            ),
            show_alert=True,
        )


@router.callback_query(F.data.startswith("pay_await_reject:"))
async def cmd_pay_await_reject(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    payment_id = event.data.split(":", 1)[1]
    payment = await claim_pending_payment_or_alert(event, payment_id, "reject")
    if not payment:
        return
    uid = await resolve_tg_id(to_int(payment.get("user_id"), 0))
    finalized = await finalize_claimed_payment_or_alert(event, payment_id, "reject", "rejected")
    if not finalized:
        return
    if not await verify_payment_final_status(payment_id, "rejected"):
        logger.error(f"Платеж {payment_id} не в 'rejected' после финализации")
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.payment_processed_warning"),
            show_alert=True,
        )
    if uid > 0:
        changed, before, after, delta = await apply_trust_score_delta(
            uid, -TRUST_SCORE_PENALTY_PAYMENT_REJECTED
        )
        if changed:
            trust_line = build_trust_change_line(delta, before, after)
        else:
            trust_line = translate(Config.DEFAULT_LANGUAGE, "texts.trust_change_short_none")
        user_lang = await get_user_language(uid)
        try:
            await notify_user(
                uid,
                translate(
                    user_lang,
                    "texts.payment_rejected_notification",
                    trust_change_line=trust_line,
                ),
                reply_markup=support_keyboard(include_main=True),
            )
        except Exception:  # noqa: BLE001, S110
            pass
    await event.answer(
        translate(Config.DEFAULT_LANGUAGE, "texts.payment_reject_alert", payment_id=payment_id),
        show_alert=True,
    )
    await append_payment_decision_label(
        event.message,
        translate(Config.DEFAULT_LANGUAGE, "texts.payment_decision_rejected"),
    )


# --- Админ-команды ---
@router.callback_query(F.data == "ban")
async def cmd_ban(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.ban_user_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(BanUserState.waiting_for_user_id)


@router.message(BanUserState.waiting_for_user_id)
async def process_ban_user_id(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return

    internal_uid, user_data = await _resolve_target_user(val, event, lang)
    if internal_uid is None:
        return

    tg_id = user_data.get("telegram_id", 0) if user_data else 0
    await state.update_data(user_id_to_ban=tg_id)
    await state.set_state(BanUserState.waiting_for_ban_reason)
    await event.answer(
        translate(Config.DEFAULT_LANGUAGE, "texts.ban_reason_prompt", user_id=tg_id),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(BanUserState.waiting_for_ban_reason)
async def process_ban_reason(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    data = await state.get_data()
    uid = data.get("user_id_to_ban")
    reason = val
    success = await db.ban_user(uid, reason)
    await state.clear()
    if success:
        await cleanup_subscription(uid, f"banned: {reason}", notify_user_about_cleanup=False)
        text = translate(Config.DEFAULT_LANGUAGE, "texts.user_banned", user_id=uid, reason=reason)
        user_lang = await get_user_language(uid)
        try:
            await notify_user(
                uid,
                translate(user_lang, "texts.user_ban_notification", reason=reason),
                reply_markup=support_keyboard(include_main=True),
            )
        except Exception:  # noqa: BLE001, S110
            pass
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.user_ban_error", user_id=uid)
    keyboard = kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.unban_user"),
                    "callback_data": "unban",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ],
        ]
    )
    await smart_answer(event, text, reply_markup=keyboard, delete_origin=True)


@router.callback_query(F.data == "unban")
async def cmd_unban(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.unban_user_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(UnbanUserState.waiting_for_user_id)


@router.message(UnbanUserState.waiting_for_user_id)
async def process_unban_user_id(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return

    internal_uid, user_data = await _resolve_target_user(val, event, lang)
    if internal_uid is None:
        return

    tg_id = user_data.get("telegram_id", 0) if user_data else 0
    await state.update_data(user_id_to_unban=tg_id)
    await state.set_state(UnbanUserState.waiting_for_unban_reason)
    await event.answer(
        translate(Config.DEFAULT_LANGUAGE, "texts.unban_reason_prompt", user_id=tg_id),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(UnbanUserState.waiting_for_unban_reason)
async def process_unban_reason(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    data = await state.get_data()
    uid = data.get("user_id_to_unban")
    reason = val
    success = await db.unban_user(uid)
    await state.clear()
    if success:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.user_unbanned", user_id=uid, reason=reason)
        user_lang = await get_user_language(uid)
        try:
            await notify_user(
                uid,
                translate(user_lang, "texts.user_unban_notification", reason=reason),
            )
        except Exception:  # noqa: BLE001, S110
            pass
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.user_unban_error", user_id=uid)
    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


@router.callback_query(F.data == "broadcast")
async def cmd_broadcast(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    text = translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_prompt")
    keyboard = kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.broadcast_all_users"),
                    "callback_data": "broadcast_all",
                }
            ],
            [
                {
                    "text": translate(
                        Config.DEFAULT_LANGUAGE, "buttons.broadcast_active_subscribers"
                    ),
                    "callback_data": "broadcast_active",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                    "callback_data": "cancel",
                }
            ],
        ]
    )
    await smart_answer(event, text, reply_markup=keyboard, delete_origin=True)
    await state.set_state(BroadcastState.waiting_for_broadcast_type)


@router.callback_query(BroadcastState.waiting_for_broadcast_type)
async def process_broadcast_type(event: CallbackQuery, state: FSMContext, **kwargs):
    if event.data in ("cancel", "start"):
        await state.clear()
        await cmd_start(event, state)
        return
    broadcast_type = event.data
    await state.update_data(broadcast_type=broadcast_type)
    type_text = (
        translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_target_all")
        if broadcast_type == "broadcast_all"
        else translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_target_active")
    )
    text = translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_message_prompt", type_text=type_text)
    await smart_answer(event, text, reply_markup=cancel_only_keyboard(), delete_origin=True)
    await state.set_state(BroadcastState.waiting_for_message)


@router.message(BroadcastState.waiting_for_message)
async def process_broadcast_message(event: Message, state: FSMContext, **kwargs):
    if not event.text or not isinstance(event.text, str):
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_message_must_be_text")
        )
        return
    msg = event.text.strip()
    lang = await get_lang(event)
    if not msg:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_text_required"))
        return
    if is_cancel_text(msg, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    data = await state.get_data()
    broadcast_type = data.get("broadcast_type")
    if broadcast_type == "broadcast_all":
        user_ids = await db.get_all_non_banned_user_ids()
    elif broadcast_type == "broadcast_active":
        user_ids = await db.get_subscribed_user_ids()
    else:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_invalid_type"))
        await state.clear()
        return
    await state.clear()
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await notify_user(uid, msg)
            sent += 1
        except Exception:  # noqa: BLE001
            failed += 1
        if sent % 10 == 0:
            await asyncio.sleep(1.0)
    type_text = (
        translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_target_all")
        if broadcast_type == "broadcast_all"
        else translate(Config.DEFAULT_LANGUAGE, "texts.broadcast_target_active")
    )
    text = translate(
        Config.DEFAULT_LANGUAGE,
        "texts.broadcast_completed",
        type_text=type_text,
        sent_count=sent,
        failed_count=failed,
    )
    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


@router.callback_query(F.data == "debug_menu")
async def cmd_debug_menu(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    text = translate(Config.DEFAULT_LANGUAGE, "texts.debug_menu_prompt")

    tech_work_text = (
        translate(Config.DEFAULT_LANGUAGE, "buttons.disable_tech_work")
        if tech_work_service.is_enabled()
        else translate(Config.DEFAULT_LANGUAGE, "buttons.enable_tech_work")
    )

    keyboard = kb(
        [
            [
                {
                    "text": tech_work_text,
                    "callback_data": "tech_work_toggle",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.search_user"),
                    "callback_data": "debug_search_user",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.broadcast"),
                    "callback_data": "broadcast",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.ban_user"),
                    "callback_data": "ban",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.unban_user"),
                    "callback_data": "unban",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.trust_add"),
                    "callback_data": "debug_trust_add",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.trust_remove"),
                    "callback_data": "debug_trust_remove",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.normalize_subscriptions"),
                    "callback_data": "debug_normalize",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.reset_all_trials"),
                    "callback_data": "debug_reset_trials",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.abuse_users"),
                    "callback_data": "debug_search_abuse_users",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.delete_user_subscription"),
                    "callback_data": "debug_delete_sub",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.add_traffic"),
                    "callback_data": "debug_add_traffic",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.change_username"),
                    "callback_data": "debug_change_username",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.change_password"),
                    "callback_data": "debug_change_password",
                }
            ],
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ],
        ]
    )
    await smart_answer(event, text, reply_markup=keyboard, delete_origin=True)


# --- Поиск пользователей в дебаг-меню ---
class SearchUserState(StatesGroup):
    waiting_for_query = State()


@router.callback_query(F.data == "debug_search_user")
async def cmd_debug_search_user(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await state.set_state(SearchUserState.waiting_for_query)
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.search_user_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


def _escape_md(text: str) -> str:
    text = text.replace("\\", "\\\\")
    special = r"_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in text)


def format_user_raw(u: dict[str, Any]) -> str:
    keys_to_hide = {
        "password_hash",
        "session_token",
        "session_expires_at",
        "session_created_at",
    }
    lines = []
    for key, val in u.items():
        if key in keys_to_hide:
            continue
        if val is None:
            continue
        if isinstance(val, bool):
            val = "TRUE" if val else "FALSE"
        elif isinstance(val, float):
            val = f"{val:.2f}" if val == int(val) else str(val)
        lines.append(f"{key}: {val}")
    return "```\n" + "\n".join(lines) + "\n```"


MAX_TG_LENGTH = 4096


def _split_markdown_message(text: str, max_length: int = MAX_TG_LENGTH) -> list[str]:
    if len(text) <= max_length:
        return [text]
    parts: list[str] = []
    current = ""
    blocks = text.split("```")
    for i, block in enumerate(blocks):
        is_code = i % 2 == 1
        sep = "```" if is_code else ""
        candidate = current + sep + block if current else sep + block
        if len(candidate) > max_length and current:
            parts.append(current)
            candidate = sep + block
        current = candidate
    if current:
        parts.append(current)
    return parts if parts else [text]


async def _send_markdown_answer(event: Message, text: str, reply_markup=None) -> bool:
    parts = _split_markdown_message(text)
    for i, part in enumerate(parts):
        try:
            await event.answer(
                part,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=reply_markup if i == len(parts) - 1 else None,
            )
        except TelegramBadRequest:
            await event.answer(
                part,
                parse_mode=None,
                reply_markup=reply_markup if i == len(parts) - 1 else None,
            )
    return True


@router.message(SearchUserState.waiting_for_query)
@log_error
async def process_search_user(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    query_str = event.text.strip() if event.text else ""
    if is_cancel_text(query_str, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not query_str:
        try:
            await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.search_user_prompt"))
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ошибка отправки ответа (search_user_prompt): {e}")
        return

    query_int: int | None = None
    try:
        query_int = int(query_str)
    except (ValueError, TypeError):
        pass

    if query_int is None:
        try:
            await event.answer(
                translate(
                    Config.DEFAULT_LANGUAGE,
                    "texts.search_user_not_found",
                    query=query_str,
                ),
                reply_markup=main_menu_keyboard(),
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ошибка отправки ответа (search_user_not_found): {e}")
        await state.clear()
        return

    users = await db.smart_lookup(query_int)
    if not users:
        users = await db.search_users(query_str)
        if not users:
            try:
                await event.answer(
                    translate(
                        Config.DEFAULT_LANGUAGE,
                        "texts.search_user_not_found",
                        query=query_str,
                    ),
                    reply_markup=main_menu_keyboard(),
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Ошибка отправки ответа (search_user_not_found 2): {e}")
            await state.clear()
            return

    text = translate(Config.DEFAULT_LANGUAGE, "texts.search_user_result", count=len(users))
    for u in users:
        match_type = u.pop("_match_type", "text") if "_match_type" in u else "text"
        match_label = translate(Config.DEFAULT_LANGUAGE, f"texts.search_match_{match_type}")
        text += f"\n\n{match_label}\n"
        text += format_user_raw(u)

    try:
        await _send_markdown_answer(event, text, reply_markup=main_menu_keyboard())
    except Exception:
        logger.exception("Ошибка отправки результата поиска")
    await state.clear()


# --- Режим тех. работ ---
class TechWorkCompensateState(StatesGroup):
    waiting_for_compensation_choice = State()
    waiting_for_days = State()
    waiting_for_confirmation = State()


@router.callback_query(F.data == "tech_work_toggle")
async def cmd_tech_work_toggle(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return

    if not tech_work_service.is_enabled():
        await tech_work_service.set_enabled(True)

        notify_text = translate(Config.DEFAULT_LANGUAGE, "texts.tech_work_started")
        notify_result = await notify_all_users(notify_text)
        logger.info(f"Уведомления отправлены: {notify_result}")

        switch_result = await switch_all_clients_to_backup()
        logger.info(f"Клиенты переключены на backup: {switch_result}")

        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.tech_work_enabled",
            notified=notify_result["sent"],
            switched=switch_result["switched"],
        )
        markup = kb(
            [
                [
                    {
                        "text": translate(Config.DEFAULT_LANGUAGE, "buttons.return_to_debug"),
                        "callback_data": "debug_menu",
                    }
                ]
            ]
        )
    else:
        await state.set_state(TechWorkCompensateState.waiting_for_compensation_choice)
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.tech_work_compensate_ask"),
            reply_markup=kb(
                [
                    [
                        {
                            "text": translate(Config.DEFAULT_LANGUAGE, "buttons.skip"),
                            "callback_data": "skip_compensate",
                        },
                        {
                            "text": translate(Config.DEFAULT_LANGUAGE, "buttons.cancel"),
                            "callback_data": "cancel_compensate",
                        },
                    ]
                ]
            ),
            delete_origin=True,
        )
        return

    await smart_answer(event, text, reply_markup=markup, delete_origin=True)


async def _run_normalization_with_notification(notified_count: int) -> None:
    logger.info("Запуск автоматической нормализации после тех. работ")
    report = await normalize_all_subscriptions_with_retry()
    logger.info(f"Нормализация завершена: {report}")

    total_changes = (
        report["expired_cleaned"]
        + report["traffic_exceeded_cleaned"]
        + report["missing_recovered"]
        + report["servers_normalized"]
        + report["subscriptions_updated"]
    )

    if report["all_normalized"]:
        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.tech_work_normalization_complete",
            iterations=report["iterations"],
            expired_cleaned=report["expired_cleaned"],
            traffic_exceeded=report["traffic_exceeded_cleaned"],
            missing_recovered=report["missing_recovered"],
            servers_normalized=report["servers_normalized"],
            subscriptions_updated=report.get("subscriptions_updated", 0),
            errors=report["errors"],
        )
    else:
        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.tech_work_normalization_incomplete",
            iterations=report["iterations"],
            total_changes=total_changes,
            errors=report["errors"],
        )
    await notify_admins(
        translate(Config.DEFAULT_LANGUAGE, "texts.admin_normalization_complete_header")
        + f"\n\n{text}"
    )


async def _end_tech_work_with_compensation(
    event: CallbackQuery | Message, days: int, broadcast: bool
) -> None:
    await tech_work_service.set_enabled(False)

    if broadcast and days > 0:
        broadcast_text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.tech_work_compensate_broadcast",
            days=days,
        )
        await notify_all_users(broadcast_text)

    restore_result = await restore_all_clients_from_backup()
    logger.info(f"Клиенты восстановлены с backup: {restore_result}")

    normalization_task = asyncio.create_task(normalize_all_subscriptions_with_retry())
    _scheduled_tasks.add(normalization_task)
    normalization_task.add_done_callback(_scheduled_tasks.discard)

    if broadcast:
        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.tech_work_compensate_complete",
            days=days,
            processed=0,
            errors=0,
        )
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.tech_work_compensate_skipped")

    markup = kb(
        [
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.return_to_debug"),
                    "callback_data": "debug_menu",
                }
            ]
        ]
    )
    await smart_answer(event, text, reply_markup=markup, delete_origin=True)


@router.callback_query(F.data == "skip_compensate")
async def cmd_skip_compensate(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event, silent=True):
        return
    await state.clear()
    await _end_tech_work_with_compensation(event, days=0, broadcast=False)


@router.callback_query(F.data == "cancel_compensate")
async def cmd_cancel_compensate(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event, silent=True):
        return
    await state.clear()
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.compensate_cancelled"),
        reply_markup=main_menu_keyboard(),
        delete_origin=True,
    )


@router.callback_query(F.data == "tech_work_compensate")
async def cmd_tech_work_compensate(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return

    await state.set_state(TechWorkCompensateState.waiting_for_days)
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.tech_work_compensate_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.message(TechWorkCompensateState.waiting_for_days)
async def process_tech_work_compensate(event: Message, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event, silent=True):
        return

    lang = await get_lang(event)
    val = event.text.strip() if event.text else ""
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return

    if not val.isdigit():
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_days_number"))
        return

    days = int(val)
    if days <= 0:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.compensate_positive_days"))
        return

    if days > 365:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.compensate_days_too_many"))
        return

    if days > 30:
        await state.set_state(TechWorkCompensateState.waiting_for_confirmation)
        await state.update_data(pending_days=days)
        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.compensate_confirm",
            days=days,
        )
        await event.answer(
            text,
            reply_markup=kb(
                [
                    [
                        {
                            "text": translate(Config.DEFAULT_LANGUAGE, "buttons.yes"),
                            "callback_data": "confirm_compensate",
                        },
                        {
                            "text": translate(Config.DEFAULT_LANGUAGE, "buttons.no"),
                            "callback_data": "cancel_compensate",
                        },
                    ],
                ]
            ),
        )
        return

    await state.clear()
    await _end_tech_work_with_compensation(event, days=days, broadcast=True)


@router.callback_query(F.data == "confirm_compensate")
async def confirm_compensate_handler(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event, silent=True):
        return
    data = await state.get_data()
    days = to_int(data.get("pending_days"), 0)
    if days < 31 or days > 365:
        await smart_answer(event, translate(Config.DEFAULT_LANGUAGE, "texts.invalid_days_number"))
        await state.clear()
        return
    await state.clear()
    await _end_tech_work_with_compensation(event, days=days, broadcast=True)


@router.callback_query(F.data == "debug_reset_trials")
async def cmd_debug_reset_trials(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    success, errors = await db.reset_all_trials()
    text = translate(
        Config.DEFAULT_LANGUAGE,
        "texts.trials_reset_result",
        success_count=success,
        error_count=errors,
    )
    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


@router.callback_query(F.data == "debug_search_abuse_users")
async def cmd_debug_search_abuse_users(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    abuse_users = await db.get_users_with_abuse()
    if not abuse_users:
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.no_abuse_users"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    rows: list[list[dict[str, str]]] = []
    for u in abuse_users:
        uid = u.get("telegram_id") or u.get("user_id")
        rows.append(
            [
                {
                    "text": translate(
                        Config.DEFAULT_LANGUAGE,
                        "texts.abuse_user_button",
                        user_id=uid,
                        abuse_status=u.get("abuse_status", "unknown"),
                    ),
                    "callback_data": f"debug_view_abuse_user:{uid}",
                },
            ]
        )
    rows.append(
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.back"),
                "callback_data": "start",
            }
        ]
    )
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.abuse_users_list_title"),
        reply_markup=kb(rows),
        delete_origin=True,
    )


@router.callback_query(F.data.startswith("debug_view_abuse_user:"))
async def cmd_debug_view_abuse_user(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    parts = event.data.split(":")
    if len(parts) < 2:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.error_generic"), show_alert=True
        )
        return
    uid = to_int(parts[1], 0)
    if uid <= 0:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_id"), show_alert=True)
        return
    user = await db.get_user_by_any_id(uid)
    if not user:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found_alert"),
            show_alert=True,
        )
        return
    abuse_status = user.get("abuse_status", "") or "нет"
    daily_traffic_gb = to_float(user.get("daily_traffic_gb"), 0.0)
    total_traffic_gb = to_float(user.get("total_traffic_gb"), 0.0)
    text = translate(
        Config.DEFAULT_LANGUAGE,
        "texts.abuse_user_info",
        user_id=uid,
        abuse_status=html.escape(abuse_status),
        daily_traffic=f"{daily_traffic_gb:.1f}",
        total_traffic=f"{total_traffic_gb:.1f}",
    )
    rows = []
    if abuse_status in ("blocked", "warning_daily", ""):
        rows.append(
            [
                {
                    "text": translate(Config.DEFAULT_LANGUAGE, "buttons.clear_abuse"),
                    "callback_data": f"debug_clear_abuse:{uid}",
                },
            ]
        )
    rows.append(
        [
            {
                "text": translate(Config.DEFAULT_LANGUAGE, "buttons.back"),
                "callback_data": "debug_search_abuse_users",
            }
        ]
    )
    await smart_answer(event, text, reply_markup=kb(rows), delete_origin=True)


@router.callback_query(F.data.startswith("debug_clear_abuse:"))
async def cmd_debug_clear_abuse(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    parts = event.data.split(":")
    if len(parts) < 2:
        await event.answer(
            translate(Config.DEFAULT_LANGUAGE, "texts.error_generic"), show_alert=True
        )
        return
    uid = to_int(parts[1], 0)
    if uid <= 0:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_id"), show_alert=True)
        return
    await db.update_user_by_telegram_id(uid, abuse_status="")
    await safe_send_message(bot, uid, translate(Config.DEFAULT_LANGUAGE, "texts.abuse_lifted"))
    user = await db.get_user_by_any_id(uid)
    if user and not user.get("vpn_url"):
        await recreate_subscription_for_user(uid, user)
    text = translate(Config.DEFAULT_LANGUAGE, "texts.abuse_admin_cleared", user_id=uid)
    await smart_answer(
        event,
        text,
        reply_markup=kb(
            [
                [
                    {
                        "text": translate(Config.DEFAULT_LANGUAGE, "buttons.back_to_list"),
                        "callback_data": "debug_search_abuse_users",
                    }
                ]
            ]
        ),
        delete_origin=True,
    )


@router.callback_query(F.data == "debug_trust_add")
async def cmd_debug_trust_add(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await state.set_state(TrustScoreState.waiting_for_user_id)
    await state.update_data(action="add")
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.trust_add_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.callback_query(F.data == "debug_trust_remove")
async def cmd_debug_trust_remove(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await state.set_state(TrustScoreState.waiting_for_user_id)
    await state.update_data(action="remove")
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.trust_remove_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.message(TrustScoreState.waiting_for_user_id)
async def process_trust_user_id(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = event.text.strip() if event.text else ""
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return

    internal_uid, user_data = await _resolve_target_user(val, event, lang)
    if internal_uid is None:
        return

    tg_id = user_data.get("telegram_id", 0) if user_data else 0
    await state.update_data(user_id_to_adjust=tg_id, internal_user_id=internal_uid)
    data = await state.get_data()
    action = data.get("action")
    action_text = translate(Config.DEFAULT_LANGUAGE, f"texts.trust_action_{action}")
    await event.answer(
        translate(
            Config.DEFAULT_LANGUAGE,
            "texts.trust_amount_prompt",
            action_text=action_text,
            user_id=tg_id,
        ),
        reply_markup=cancel_only_keyboard(),
    )
    await state.set_state(TrustScoreState.waiting_for_amount)


@router.message(TrustScoreState.waiting_for_amount)
async def process_trust_amount(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = event.text.strip() if event.text else ""
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.trust_amount_invalid"))
        return
    amount = int(val)
    if amount <= 0:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.trust_amount_positive"))
        return
    if amount > TRUST_SCORE_MAX:
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.trust_amount_exceeds_max",
                max_amount=TRUST_SCORE_MAX,
            )
        )
        return
    data = await state.get_data()
    action = data.get("action")
    uid = data.get("user_id_to_adjust")
    if not uid or action not in ("add", "remove"):
        await state.clear()
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.state_error"))
        return
    current = await db.get_trust_score(uid)
    future = current + (amount if action == "add" else -amount)
    if future < TRUST_SCORE_MIN:
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.trust_operation_negative_balance",
                current_score=current,
            )
        )
        return
    if future > TRUST_SCORE_MAX:
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.trust_operation_exceeds_max",
                max_amount=TRUST_SCORE_MAX,
                current_score=current,
            )
        )
        return
    delta = amount if action == "add" else -amount
    result = await db.add_trust_score(uid, delta)
    final = await db.get_trust_score(uid)
    actual_delta = final - current
    await state.clear()
    if result:
        action_text = translate(Config.DEFAULT_LANGUAGE, f"texts.trust_action_success_{action}")
        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.trust_update_success",
            user_id=uid,
            current_score=current,
            final_score=final,
            delta=actual_delta,
            discount=calculate_discount_percent(final),
            action_text=action_text,
        )
        admin_id = get_event_user_id(event) or 0
        admin_username = (event.from_user.username or "").strip()
        admin_identity = f"ID <code>{admin_id}</code>" + (
            f", username <code>@{admin_username}</code>" if admin_username else ""
        )
        admin_action = translate(Config.DEFAULT_LANGUAGE, f"texts.trust_admin_action_{action}")
        user_lang = await get_user_language(uid)
        try:
            await notify_user(
                uid,
                translate(
                    user_lang,
                    "texts.trust_update_notification",
                    admin_identity=admin_identity,
                    admin_action=admin_action,
                    amount=abs(actual_delta),
                    current_score=current,
                    final_score=final,
                    discount=calculate_discount_percent(final),
                ),
            )
        except Exception:  # noqa: BLE001, S110
            pass
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.trust_update_failed")
    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


@router.callback_query(F.data == "debug_normalize")
async def cmd_debug_normalize(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event, silent=True):
        return
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.normalize_subscriptions_running"),
        delete_origin=True,
    )
    report = await normalize_all_subscriptions_with_retry()

    total_changes = (
        report["expired_cleaned"]
        + report["traffic_exceeded_cleaned"]
        + report["missing_recovered"]
        + report["servers_normalized"]
        + report["subscriptions_updated"]
    )

    if report["all_normalized"]:
        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.normalize_all_complete",
            iterations=report["iterations"],
            expired_cleaned=report["expired_cleaned"],
            traffic_exceeded=report["traffic_exceeded_cleaned"],
            missing_recovered=report["missing_recovered"],
            servers_normalized=report["servers_normalized"],
            subscriptions_updated=report.get("subscriptions_updated", 0),
            errors=report["errors"],
        )
    else:
        text = translate(
            Config.DEFAULT_LANGUAGE,
            "texts.normalize_all_incomplete",
            iterations=report["iterations"],
            total_changes=total_changes,
            errors=report["errors"],
        )

    if total_changes > 0:
        text += f"\n\n📊 <b>Всего изменений:</b> {html.escape(str(total_changes))}"
    if report["errors"] > 0:
        text += f"\n⚠️ <b>Ошибок:</b> {html.escape(str(report['errors']))}"

    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


# --- Функция удаления подписки (debug) ---
@router.callback_query(F.data == "debug_delete_sub")
async def cmd_delete_subscription_start(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.delete_subscription_confirm_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(DeleteSubscriptionState.waiting_for_user_id)


@router.message(DeleteSubscriptionState.waiting_for_user_id)
async def process_delete_sub_user_id(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return

    internal_uid, user_data = await _resolve_target_user(val, event, lang)
    if internal_uid is None:
        return

    tg_id = user_data.get("telegram_id", 0) if user_data else 0
    await state.update_data(del_user_id=tg_id)
    await state.set_state(DeleteSubscriptionState.waiting_for_confirm)
    await event.answer(
        translate(Config.DEFAULT_LANGUAGE, "texts.delete_subscription_confirm", user_id=tg_id),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(DeleteSubscriptionState.waiting_for_confirm)
async def process_delete_sub_confirm(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if val.upper() != "ДА":
        await event.answer(translate(lang, "texts.confirmation_prompt"))
        return
    data = await state.get_data()
    uid = data.get("del_user_id")
    await state.clear()
    result = await cleanup_subscription(uid, "admin_deleted", notify_user_about_cleanup=True)
    if result["success"]:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.delete_subscription_success", user_id=uid)
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.delete_subscription_fail", user_id=uid)
    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


# --- Функция начисления доп. трафика (debug) ---
@router.callback_query(F.data == "debug_add_traffic")
async def cmd_add_traffic_start(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_user_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(AddTrafficState.waiting_for_user_id)


@router.message(AddTrafficState.waiting_for_user_id)
async def process_add_traffic_user_id(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return

    internal_uid, user_data = await _resolve_target_user(val, event, lang)
    if internal_uid is None:
        return

    tg_id = user_data.get("telegram_id", 0) if user_data else 0
    if not normalize_sub_id(user_data.get("vpn_url")) if user_data else True:
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.add_traffic_no_subscription",
                user_id=tg_id,
            )
        )
        return
    await state.update_data(traffic_user_id=tg_id)
    await state.set_state(AddTrafficState.waiting_for_gb)
    await event.answer(
        translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_gb_prompt", user_id=tg_id),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(AddTrafficState.waiting_for_gb)
async def process_add_traffic_gb(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_gb_invalid"))
        return
    gb = int(val)
    if gb <= 0:
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_gb_positive"))
        return
    data = await state.get_data()
    uid: int = int(data.get("traffic_user_id", 0))
    await state.clear()

    if uid <= 0:
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_fail", user_id=uid),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return

    user = await db.get_user_by_any_id(uid)
    if not user:
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    internal_uid = user.get("user_id", uid)
    tg_id = to_int(user.get("telegram_id"), uid)

    db_ok = await db.add_extra_traffic(uid, gb)
    if not db_ok:
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_fail", user_id=uid),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return

    base_email = build_base_email(internal_uid)
    panel_ok = await panel.add_client_traffic(base_email, gb)
    user_lang = await get_user_language(tg_id)
    try:
        await notify_user(
            tg_id,
            translate(user_lang, "texts.add_traffic_notification", gb=gb),
        )
    except Exception:  # noqa: BLE001, S110
        pass

    if panel_ok:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_success", user_id=uid, gb=gb)
    else:
        text = translate(Config.DEFAULT_LANGUAGE, "texts.add_traffic_partial", user_id=uid, gb=gb)
    await smart_answer(event, text, reply_markup=main_menu_keyboard(), delete_origin=True)


# --- Смена логина (debug) ---
@router.callback_query(F.data == "debug_change_username")
async def cmd_debug_change_username(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await state.set_state(ChangeUsernameState.waiting_for_user_id)
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.change_username_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.message(ChangeUsernameState.waiting_for_user_id)
async def process_change_username_user_id(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return
    internal_uid = int(val)
    if not await _validate_admin_target_by_user_id(internal_uid, event, lang):
        return
    await state.update_data(change_username_uid=internal_uid)
    await state.set_state(ChangeUsernameState.waiting_for_new_username)
    await event.answer(
        translate(
            Config.DEFAULT_LANGUAGE,
            "texts.change_username_new_prompt",
            user_id=internal_uid,
        ),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(ChangeUsernameState.waiting_for_new_username)
async def process_change_username_new(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not re.match(r"^[a-zA-Z0-9_]{3,32}$", val):
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.change_username_invalid"))
        return
    data = await state.get_data()
    uid = data.get("change_username_uid", 0)
    await state.clear()
    try:
        success = await db.change_username(uid, val)
        if success:
            await smart_answer(
                event,
                translate(
                    Config.DEFAULT_LANGUAGE,
                    "texts.change_username_success",
                    user_id=uid,
                    new_username=val,
                ),
                reply_markup=main_menu_keyboard(),
                delete_origin=True,
            )
        else:
            await smart_answer(
                event,
                translate(Config.DEFAULT_LANGUAGE, "texts.change_username_fail"),
                reply_markup=main_menu_keyboard(),
                delete_origin=True,
            )
    except Exception as e:  # noqa: BLE001
        logger.error(f"change_username error: {e}")
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.change_username_fail"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )


# --- Смена пароля (debug) ---
@router.callback_query(F.data == "debug_change_password")
async def cmd_debug_change_password(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await state.set_state(ChangePasswordState.waiting_for_user_id)
    await smart_answer(
        event,
        translate(Config.DEFAULT_LANGUAGE, "texts.change_password_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.message(ChangePasswordState.waiting_for_user_id)
async def process_change_password_user_id(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(Config.DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return
    internal_uid = int(val)
    if not await _validate_admin_target_by_user_id(internal_uid, event, lang):
        return
    await state.update_data(change_password_uid=internal_uid)
    await state.set_state(ChangePasswordState.waiting_for_new_password)
    await event.answer(
        translate(
            Config.DEFAULT_LANGUAGE,
            "texts.change_password_new_prompt",
            user_id=internal_uid,
        ),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(ChangePasswordState.waiting_for_new_password)
async def process_change_password_new(event: Message, state: FSMContext, **kwargs):
    lang = await get_lang(event)
    val = (event.text or "").strip()
    if is_cancel_text(val, lang):
        await state.clear()
        await cmd_start(event, state)
        return
    if len(val) < Config.PASSWORD_MIN_LENGTH:
        await event.answer(
            translate(
                Config.DEFAULT_LANGUAGE,
                "texts.change_password_invalid",
                min_length=Config.PASSWORD_MIN_LENGTH,
            )
        )
        return
    data = await state.get_data()
    uid = data.get("change_password_uid", 0)
    await state.clear()
    try:
        hashed = pwd_context.hash(val)
        success = await db.change_password(uid, hashed)
        if success:
            await smart_answer(
                event,
                translate(
                    Config.DEFAULT_LANGUAGE,
                    "texts.change_password_success",
                    user_id=uid,
                ),
                reply_markup=main_menu_keyboard(),
                delete_origin=True,
            )
        else:
            await smart_answer(
                event,
                translate(Config.DEFAULT_LANGUAGE, "texts.change_password_fail"),
                reply_markup=main_menu_keyboard(),
                delete_origin=True,
            )
    except Exception as e:  # noqa: BLE001
        logger.error(f"change_password error: {e}")
        await smart_answer(
            event,
            translate(Config.DEFAULT_LANGUAGE, "texts.change_password_fail"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )


async def normalize_all_subscriptions_with_retry(
    max_iterations: int = 5, delay_between_iterations: int = 2
) -> dict[str, Any]:
    report = {
        "iterations": 0,
        "expired_cleaned": 0,
        "traffic_exceeded_cleaned": 0,
        "missing_recovered": 0,
        "servers_normalized": 0,
        "subscriptions_updated": 0,
        "errors": 0,
        "panel_errors": 0,
        "all_normalized": False,
    }

    logger.info("🔧 === НАЧАЛО НОРМАЛИЗАЦИИ ===")

    for iteration in range(max_iterations):
        report["iterations"] = iteration + 1
        iter_changes = 0

        inbounds_data = await panel.get_inbounds()
        raw_inbounds: list[dict[str, Any]] = []
        if inbounds_data and inbounds_data.get("success"):
            obj = inbounds_data.get("obj", [])
            if isinstance(obj, dict):
                raw_inbounds = obj.get("items") or obj.get("data") or obj.get("inbounds") or []
            elif isinstance(obj, list):
                raw_inbounds = obj
            else:
                raw_inbounds = []

        db_subs = await db.get_subscribed_user_ids()
        users_list = await db.get_users_by_telegram_ids(db_subs)
        users_by_tgid: dict[int, dict[str, Any]] = {u["telegram_id"]: u for u in users_list}
        logger.info(
            f"Итерация {iteration + 1}/{max_iterations}: обрабатывается {len(db_subs)} подписок"
        )

        clients_cache: dict[str, list[dict[str, Any]]] = {}
        for uid in db_subs:
            try:
                user = users_by_tgid.get(uid)
                if not user:
                    logger.warning(f"⚠️ Пользователь {uid} не найден в БД")
                    continue

                is_admin = await is_admin_user(uid)
                if is_admin:
                    base_email = f"admin@{Config.VPN_NAME.lower()}.com"
                    all_location_codes = get_all_location_codes()
                    if all_location_codes:
                        stored_servers = parse_stored_servers(user.get("plan_servers"))
                        if set(stored_servers) != set(all_location_codes):
                            ok = await db.update_user_by_telegram_id(
                                uid,
                                force=True,
                                plan_servers=json.dumps(all_location_codes, ensure_ascii=False),
                            )
                            if ok:
                                logger.info(
                                    f"  🔄 Админ {uid}: установлены все локации: {all_location_codes}"
                                )
                                report["servers_normalized"] += 1
                                iter_changes += 1
                                user["plan_servers"] = json.dumps(
                                    all_location_codes, ensure_ascii=False
                                )
                            else:
                                logger.error(
                                    f"  ❌ Не удалось обновить plan_servers для админа {uid}"
                                )
                    # Админ нормализуется дальше: привязка ко всем inbound'ам.
                else:
                    base_email = build_base_email(user.get("user_id", uid))

                # === Шаг 1: Ищем план по subscription_id из БД ---
                subscription_id = str(user.get("subscription_id") or "").strip()
                plan = get_by_id(subscription_id) if subscription_id else None

                if not plan:
                    plan_text = user.get("plan_text", "")
                    base_plan_name = plan_text.split(" (", 1)[0].strip()
                    plan = get_by_name(base_plan_name) if base_plan_name else None

                # === Шаг 2: Если план найден - обновляем данные в БД ---
                if plan:
                    plan_servers = get_plan_servers(plan)
                    plan_ip = to_int(plan.get("ip_limit"), 0)
                    plan_gb = to_float(plan.get("traffic_gb"), 0.0)

                    stored_servers = parse_stored_servers(user.get("plan_servers"))
                    stored_ip = to_int(user.get("ip_limit"), 0)
                    stored_gb = to_float(user.get("traffic_gb"), 0.0)

                    needs_update = False
                    update_fields = {}

                    if plan_servers and set(stored_servers) != set(plan_servers):
                        logger.info(
                            f"  🔄 Нормализация серверов: {stored_servers} -> {plan_servers}"
                        )
                        update_fields["plan_servers"] = json.dumps(plan_servers, ensure_ascii=False)
                        needs_update = True

                    if stored_ip != plan_ip:
                        logger.info(f"  🔄 Обновление IP: {stored_ip} -> {plan_ip}")
                        update_fields["ip_limit"] = plan_ip
                        needs_update = True

                    if abs(stored_gb - plan_gb) > 0.1:
                        logger.info(f"  🔄 Обновление трафика: {stored_gb} -> {plan_gb}")
                        update_fields["traffic_gb"] = plan_gb
                        needs_update = True

                    if needs_update:
                        await db.update_user_by_telegram_id(uid, **update_fields)
                        report["subscriptions_updated"] += 1
                        iter_changes += 1
                        stored_servers = plan_servers
                    else:
                        logger.info(
                            f"  ✅ Данные уже нормализованы: servers={stored_servers}, ip={stored_ip}, gb={stored_gb}"
                        )

                    plan_servers = stored_servers
                else:
                    stored_servers = parse_stored_servers(user.get("plan_servers"))
                    stored_ip = to_int(user.get("ip_limit"), 0)
                    stored_gb = to_float(user.get("traffic_gb"), 0.0)
                    logger.info(
                        f"  ⚠️ План не найден по subscription_id='{subscription_id}', "
                        f"используем stored данные: servers={stored_servers}, ip={stored_ip}, gb={stored_gb}"
                    )

                    stored_expiry = str(user.get("expiry_sub_datatime") or "").strip()
                    if not stored_expiry:
                        default_expiry = (
                            datetime.now(timezone.utc) + timedelta(days=30)
                        ).isoformat()
                        logger.info(
                            f"  🕐 Нет expiry_sub_datatime для {uid}, устанавливаем default: {default_expiry}"
                        )
                        await db.update_user_by_telegram_id(uid, expiry_sub_datatime=default_expiry)
                        stored_expiry = default_expiry
                        iter_changes += 1

                    update_fields = {}
                    stored_servers_json = (
                        json.dumps(stored_servers, ensure_ascii=False) if stored_servers else ""
                    )
                    if stored_servers_json and user.get("plan_servers") != stored_servers_json:
                        update_fields["plan_servers"] = stored_servers_json
                    if stored_ip != to_int(user.get("ip_limit"), 0):
                        update_fields["ip_limit"] = stored_ip
                    if stored_gb != to_float(user.get("traffic_gb"), 0.0):
                        update_fields["traffic_gb"] = stored_gb

                    if update_fields:
                        await db.update_user_by_telegram_id(uid, **update_fields)
                        report["subscriptions_updated"] += 1
                        iter_changes += 1
                        logger.info(f"  🔄 Обновлены stored данные для {uid}: {update_fields}")

                    plan_servers = stored_servers

                # === Шаг 3: Нормализуем на сервере ---
                target_inbound_ids: list[int] = []
                # Админ всегда привязывается ко ВСЕМ инбаундам (фулл без лимита).
                if await is_admin_user(uid):
                    target_inbound_ids = [
                        to_int(inb.get("id"), 0)
                        for inb in raw_inbounds
                        if isinstance(inb, dict) and to_int(inb.get("id"), 0) > 0
                    ]
                    logger.info(
                        f"  🎯 Admin uid={uid}: привязываем ко ВСЕМ inbound'ам "
                        f"({len(target_inbound_ids)} шт.)"
                    )
                elif plan_servers:
                    matched_inbounds = _filter_inbounds_for_servers_list(raw_inbounds, plan_servers)
                    target_inbound_ids = [
                        to_int(inb.get("id"), 0)
                        for inb in matched_inbounds
                        if to_int(inb.get("id"), 0) > 0
                    ]
                    logger.info(
                        f"  🎯 Target inbound IDs: {target_inbound_ids} "
                        f"(servers={plan_servers}, matched_inbounds_count={len(matched_inbounds)})"
                    )
                else:
                    logger.warning(
                        f"  ⚠️ Нет plan_servers для uid={uid}, target_inbound_ids будет пустым"
                    )

                clients = clients_cache.get(base_email)
                if clients is None:
                    clients = await panel.find_clients_full_by_email(base_email)
                    clients_cache[base_email] = clients
                if clients:
                    for c in clients:
                        email = str(c.get("email") or "")
                        if not email:
                            continue

                        client = await panel.get_client_by_email(email) or c.get("clientObj") or c
                        if not isinstance(client, dict):
                            continue

                        if not client.get("enable"):
                            logger.info(f"  🔓 Включаем отключённого клиента: {email}")
                            client["enable"] = True
                            payload = panel._client_payload_for_update(client)
                            url = f"{panel.apibase}/panel/api/clients/update/{panel._quote_path(email)}"
                            status, data, _ = await panel._request_json_with_reauth(
                                "POST", url, headers=panel._headers(), json=payload
                            )
                            if status in (200, 201) and data.get("success"):
                                report["subscriptions_updated"] += 1
                                iter_changes += 1
                                logger.info(f"  ✅ Клиент {email} включён")
                            else:
                                logger.error(f"  ❌ Не удалось включить {email}: {data.get('msg')}")
                            continue

                        current_inbounds = client.get("inboundIds") or []
                        current_inbounds_ints = sorted(
                            {to_int(x, 0) for x in current_inbounds if to_int(x, 0) > 0}
                        )
                        target_inbounds_set = set(target_inbound_ids)
                        current_inbounds_set = set(current_inbounds_ints)

                        to_attach = sorted(target_inbounds_set - current_inbounds_set)
                        to_detach = sorted(current_inbounds_set - target_inbounds_set)

                        if to_attach or to_detach:
                            logger.info(
                                f"  🔄 Нормализация inbound: {current_inbounds_ints} -> {target_inbound_ids}"
                            )
                            normalized = False
                            if to_detach:
                                det_ok = await panel.detach_client_from_inbounds(email, to_detach)
                                if det_ok:
                                    logger.info(f"  📤 Открепление от inbound'ов: {to_detach}")
                                    normalized = True
                                else:
                                    report["panel_errors"] += 1
                                    logger.error(
                                        f"  ❌ Не удалось открепить от inbound'ов {to_detach} для {email}"
                                    )
                            if to_attach:
                                att_ok = await panel.attach_client_to_inbounds(email, to_attach)
                                if att_ok:
                                    logger.info(f"  📤 Подкрепление к inbound'ам: {to_attach}")
                                    normalized = True
                                else:
                                    report["panel_errors"] += 1
                                    logger.error(
                                        f"  ❌ Не удалось прикрепить к inbound'ам {to_attach} для {email}"
                                    )
                            if normalized:
                                report["servers_normalized"] += 1
                                iter_changes += 1
                                logger.info(f"  ✅ Inbound нормализован для {email}")
                        else:
                            logger.info(f"  ✅ Inbound уже нормализован: {current_inbounds_ints}")

                        curr_ip = to_int(user.get("ip_limit"), 0)
                        curr_gb = to_float(user.get("traffic_gb"), 0.0)

                        fresh_user = await db.get_user_by_any_id(uid)
                        if fresh_user:
                            plan_ip = to_int(fresh_user.get("ip_limit"), curr_ip)
                            plan_gb = to_float(fresh_user.get("traffic_gb"), curr_gb)
                        else:
                            plan_ip = curr_ip
                            plan_gb = curr_gb

                        extra_gb = to_int((fresh_user or user).get("extra_sub_gb"), 0)
                        total_gb = plan_gb + extra_gb

                        if curr_ip != plan_ip or abs(curr_gb - total_gb) > 0.1:
                            logger.info(
                                f"  🔄 Обновление настроек на сервере: IP {curr_ip}->{plan_ip}, GB {curr_gb}->{total_gb}"
                            )
                            client["limitIp"] = plan_ip
                            client["totalGB"] = int(total_gb * BYTES_IN_GB)
                            payload = panel._client_payload_for_update(client)
                            upd_url = f"{panel.apibase}/panel/api/clients/update/{panel._quote_path(email)}"
                            status, data, _ = await panel._request_json_with_reauth(
                                "POST",
                                upd_url,
                                headers=panel._headers(),
                                json=payload,
                            )
                            if status in (200, 201) and data.get("success"):
                                logger.info(f"  ✅ Настройки обновлены для {email}")
                            else:
                                logger.error(
                                    f"  ❌ Не удалось обновить настройки для {email}: {data.get('msg')}"
                                )
                        else:
                            logger.info(
                                f"  ✅ Настройки уже нормализованы: IP={curr_ip}, GB={curr_gb}"
                            )

                # === Шаг 4: Обновляем expiry_sub_datatime из данных панели ---
                if clients:
                    expiry_times = [to_int(c.get("expiryTime"), 0) for c in clients]
                    max_expiry = max((x for x in expiry_times if x > 0), default=0)
                    if max_expiry > 0:
                        expiry_iso = datetime.fromtimestamp(
                            max_expiry / 1000, tz=timezone.utc
                        ).isoformat()
                        stored_expiry = str(user.get("expiry_sub_datatime") or "").strip()
                        if stored_expiry != expiry_iso:
                            await db.update_user_by_telegram_id(uid, expiry_sub_datatime=expiry_iso)
                            logger.info(
                                f"  🕐 Обновлён expiry_sub_datatime для {uid}: "
                                f"{stored_expiry or 'пусто'} -> {expiry_iso}"
                            )

                state = await get_subscription_state(uid)
                status = state.get("status")

                # Админская подписка - фулл без лимита: никогда не удаляется
                # при expired/traffic_exhausted, но восстанавливается при
                # missing_on_panel как канонический клиент Admin (все inbound'ы).
                if await is_admin_user(uid):
                    if status in ("expired", "traffic_exhausted"):
                        logger.info(
                            f"  🛡 Админ {uid}: подписка защищена от очистки (status={status})"
                        )
                        continue
                    if status == "missing_on_panel":
                        logger.info(f"  🔄 Админ {uid}: восстанавливаем канонический Admin клиент")
                        admin_email = f"admin@{Config.VPN_NAME.lower()}.com"
                        inbound_ids = await panel.get_matching_inbound_ids([]) or []
                        if not inbound_ids:
                            report["errors"] += 1
                            logger.warning(f"  ⚠️ Админ {uid}: нет inbound'ов для восстановления")
                        else:
                            existing = None
                            existing_email = admin_email
                            ok, sub_clients = await panel.find_clients_by_sub_id_safe("Admin")
                            if ok and sub_clients:
                                c0 = sub_clients[0]
                                existing_email = str(c0.get("email") or admin_email)
                                existing = await panel.get_client_by_email(existing_email) or c0
                            if not existing:
                                existing = await panel.get_client_by_email(admin_email)
                                if existing:
                                    existing_email = admin_email

                            if existing:
                                client = dict(existing)
                                client["email"] = existing_email
                                client["enable"] = True
                                client["limitIp"] = 0
                                client["totalGB"] = 0
                                client["subId"] = "Admin"
                                client["tgId"] = max(0, int(uid))
                                client["inboundIds"] = inbound_ids
                                payload = panel._client_payload_for_update(client)
                                url = f"{panel.apibase}/panel/api/clients/update/{panel._quote_path(existing_email)}"
                                status, data, _ = await panel._request_json_with_reauth(
                                    "POST", url, headers=panel._headers(), json=payload
                                )
                                if status in (200, 201) and data.get("success"):
                                    logger.info(f"  ✅ Админ {uid}: Admin клиент обновлён")
                                else:
                                    report["errors"] += 1
                                    logger.warning(
                                        f"  ⚠️ Админ {uid}: не удалось обновить Admin клиент: {data.get('msg')}"
                                    )
                                await panel.attach_client_to_inbounds(existing_email, inbound_ids)
                            else:
                                client = await panel.create_client(
                                    email=admin_email,
                                    limit_ip=0,
                                    total_gb=0,
                                    days=Config.ADMIN_AUTO_SUBSCRIBE_DAYS,
                                    servers=[],
                                    tg_id=uid,
                                    sub_id="Admin",
                                    inbound_ids=inbound_ids,
                                )
                                if client:
                                    report["missing_recovered"] += 1
                                    iter_changes += 1
                                    logger.info(f"  ✅ Админ {uid}: Admin клиент восстановлен")
                                else:
                                    report["errors"] += 1
                                    logger.warning(
                                        f"  ⚠️ Админ {uid}: не удалось восстановить Admin клиент"
                                    )
                    continue

                if status == "expired":
                    logger.info(f"  🗑 Удаляем expired подписку: {uid}")
                    res = await cleanup_subscription(uid, "expired", notify_user_about_cleanup=True)
                    if res.get("success"):
                        report["expired_cleaned"] += 1
                        iter_changes += 1
                    else:
                        report["errors"] += 1

                elif status == "traffic_exhausted":
                    logger.info(f"  🗑 Удаляем traffic_exhausted подписку: {uid}")
                    res = await cleanup_subscription(
                        uid, "traffic_exhausted", notify_user_about_cleanup=True
                    )
                    if res.get("success"):
                        report["traffic_exceeded_cleaned"] += 1
                        iter_changes += 1
                    else:
                        report["errors"] += 1

                elif status == "missing_on_panel":
                    logger.info(f"  🔄 Восстанавливаем missing подписку: {uid}")

                    subscription_id = str(user.get("subscription_id") or "").strip()
                    plan = get_by_id(subscription_id) if subscription_id else None

                    if not plan:
                        plan_servers = get_user_plan_servers(user)
                        restore_ip = to_int(user.get("ip_limit"), 1)
                        restore_gb = to_float(user.get("traffic_gb"), 10.0)
                        restore_days = 30
                    else:
                        plan_servers = get_plan_servers(plan)
                        restore_ip = to_int(plan.get("ip_limit"), 1)
                        restore_gb = to_float(plan.get("traffic_gb"), 10.0)
                        restore_days = to_int(plan.get("duration_days"), 30)

                    extra_gb = to_int(user.get("extra_sub_gb"), 0)
                    restore_gb_total = restore_gb + extra_gb

                    expiry_str = str(user.get("expiry_sub_datatime") or "").strip()
                    if expiry_str:
                        try:
                            expiry_dt = datetime.fromisoformat(expiry_str)
                            remaining = (expiry_dt - datetime.now(timezone.utc)).days
                            if remaining > 0:
                                restore_days = remaining
                        except Exception:  # noqa: BLE001, S110
                            pass

                    inbound_ids = await panel.get_matching_inbound_ids(plan_servers)
                    if inbound_ids:
                        email = build_base_email(user.get("user_id", uid))
                        existing = await panel.get_client_by_email(email)
                        if existing:
                            logger.info(f"  ✅ Клиент уже существует на панели: {email}")
                        else:
                            client = await panel.create_client(
                                email=email,
                                limit_ip=restore_ip,
                                total_gb=restore_gb_total,
                                days=restore_days,
                                servers=plan_servers,
                                tg_id=uid,
                                inbound_ids=inbound_ids,
                            )
                            if client:
                                report["missing_recovered"] += 1
                                iter_changes += 1
                            else:
                                report["errors"] += 1
                                logger.warning(f"Не удалось восстановить подписку для user {uid}")
                    else:
                        report["errors"] += 1
                        logger.warning(f"Нет inbound'ов для восстановления user {uid}")

            except Exception:
                logger.exception(f"Ошибка нормализации {uid}")
                report["errors"] += 1

        logger.info(f"Итерация {iteration + 1} завершена: {iter_changes} изменений")

        if iter_changes == 0:
            report["all_normalized"] = True
            logger.info("✅ Изменений не найдено, нормализация завершена")
            break

        if iteration < max_iterations - 1:
            await asyncio.sleep(delay_between_iterations)

    logger.info(f"🔧 === КОНЕЦ НОРМАЛИЗАЦИИ: {report} ===")

    return report


# --- Фоновые задачи ---
@log_error
async def cleanup_stale_payments() -> int:
    try:
        released = await json_db.release_stale_processing_payments()
        if released:
            logger.info(f"Освобождено {released} зависших платежей")
        return released
    except Exception as e:  # noqa: BLE001
        logger.error(f"Ошибка очистки платежей: {e}")
        return 0


@log_error
async def check_expired_subscriptions() -> None:
    await asyncio.sleep(10)
    semaphore = asyncio.Semaphore(10)

    async def _check(uid: int) -> bool:
        async with semaphore:
            if await is_admin_user(uid):
                return True
            try:
                state = await ensure_subscription_state(uid, notify_user_about_cleanup=True)
                if state.get("status") == "active":
                    await notify_expiring_subscription(uid, state, days=Config.EXPIRY_ALERT_DAYS)
                return True
            except Exception as e:  # noqa: BLE001
                logger.error(f"Ошибка проверки подписки {uid}: {type(e).__name__}: {e}")
                return False

    while True:
        try:
            subscribed = await db.get_subscribed_user_ids()
            logger.info(f"Проверка {len(subscribed)} подписок")

            results = await asyncio.gather(
                *[_check(uid) for uid in subscribed], return_exceptions=True
            )
            processed = sum(1 for r in results if r and not isinstance(r, BaseException))
            errors = len(results) - processed

            if errors > 0:
                logger.warning(
                    f"Проверка подписок завершена: {processed} обработано, {errors} ошибок"
                )
            else:
                logger.info(f"✅ Проверка подписок завершена: {processed} обработано")

            await asyncio.sleep(SECONDS_IN_HOUR)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка в check_expired_subscriptions: {type(e).__name__}: {e}")
            await asyncio.sleep(60)


async def recreate_subscription_for_user(user_id: int, user: dict[str, Any]) -> bool:
    try:
        plan_id = user.get("subscription_id") or ""
        if not plan_id:
            plan = get_by_id(user.get("plan_text", ""))
            if not plan:
                logger.warning(f"recreate_subscription_for_user: no plan for {user_id}")
                return False
            plan_id = plan.get("id", "")
        plan = get_by_id(plan_id) if plan_id else None
        if not plan:
            logger.warning(f"recreate_subscription_for_user: plan not found for {user_id}")
            return False
        servers = get_plan_servers(plan)
        success = await create_subscription(
            user_id,
            plan.get("traffic_gb", 0),
            plan.get("ip_limit", 1),
            plan.get("duration_days", 30),
            servers,
            plan.get("price_rub", 0),
            plan.get("id", ""),
        )
        if success:
            logger.info(f"recreate_subscription_for_user: restored for {user_id}")
        else:
            logger.error(f"recreate_subscription_for_user: failed for {user_id}")
        return success
    except Exception as e:  # noqa: BLE001
        logger.error(f"recreate_subscription_for_user {user_id}: {type(e).__name__}: {e}")
        return False


@log_error
async def check_traffic_abuse() -> None:
    await asyncio.sleep(15)
    while True:
        try:
            await _run_traffic_abuse_check()
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка в check_traffic_abuse: {type(e).__name__}: {e}")
        await asyncio.sleep(Config.TRAFFIC_ABUSE_CHECK_INTERVAL_SEC)


async def _run_traffic_abuse_check() -> None:
    subscribed = await db.get_subscribed_user_ids()
    logger.info(f"Проверка трафика: {len(subscribed)} подписок")

    daily_limit_gb = Config.TRAFFIC_ABUSE_DAILY_LIMIT_GB
    total_limit_gb = Config.TRAFFIC_ABUSE_TOTAL_LIMIT_GB
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    all_clients_data = await panel.get_clients()
    all_clients_map: dict[str, list[dict[str, Any]]] = {}
    if all_clients_data and all_clients_data.get("success"):
        for row in panel._client_rows_from_response(all_clients_data):
            email = str(row.get("email") or "")
            if email:
                all_clients_map.setdefault(email, []).append(panel._normalize_client_row(row))

    for uid in subscribed:
        try:
            if await is_admin_user(uid):
                continue

            user = await db.get_user_by_any_id(uid)
            if not user:
                continue

            if user.get("abuse_status") == "blocked":
                continue

            user_id = user.get("user_id", uid)
            sub_id = normalize_sub_id(user.get("vpn_url"))
            if not sub_id:
                continue

            base_email = get_user_panel_email(user_id, user)
            clients = all_clients_map.get(base_email, [])

            if not clients:
                continue

            used_bytes = sum(
                max(0, to_int(c.get("up"), 0)) + max(0, to_int(c.get("down"), 0)) for c in clients
            )
            used_gb = used_bytes / BYTES_IN_GB
            user_traffic_gb = max(0.0, to_float(user.get("traffic_gb"), 0.0))
            extra_gb = max(0, to_int(user.get("extra_sub_gb"), 0))
            total_traffic_gb = user_traffic_gb + extra_gb

            is_unlimited = total_traffic_gb <= 0

            if is_unlimited:
                stored_date = str(user.get("daily_traffic_date", "") or "").strip()
                stored_daily = to_float(user.get("daily_traffic_gb"), 0.0)
                stored_total = to_float(user.get("total_traffic_gb"), 0.0)

                if stored_date == today:
                    daily_usage = stored_daily
                    total_usage = stored_total
                else:
                    daily_usage = 0.0
                    total_usage = stored_total

                delta_gb = max(0.0, used_gb - total_usage)
                if delta_gb > 0:
                    daily_usage += delta_gb
                    total_usage += delta_gb
                    await db.update_user_by_telegram_id(
                        uid,
                        daily_traffic_date=today,
                        daily_traffic_gb=round(daily_usage, 4),
                        total_traffic_gb=round(total_usage, 4),
                    )

                if daily_usage > daily_limit_gb:
                    await _handle_daily_abuse(uid, user_id, daily_usage, daily_limit_gb, user)
                    await db.update_user_by_telegram_id(uid, abuse_status="warning_daily")

                if total_usage > total_limit_gb:
                    await _handle_total_abuse(uid, user_id, total_usage, total_limit_gb, user)
                    await db.update_user_by_telegram_id(uid, abuse_status="blocked")
                    await _suspend_subscription(uid, user)

        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка проверки трафика для {uid}: {type(e).__name__}: {e}")


async def _handle_daily_abuse(
    uid: int,
    user_id: int,
    daily_gb: float,
    limit_gb: float,
    user: dict[str, Any],
) -> None:
    lang = await db.get_user_language_by_user_id(user_id) or Config.DEFAULT_LANGUAGE
    text = translate(
        lang,
        "texts.abuse_daily_traffic_exceeded",
        daily_gb=f"{daily_gb:.1f}",
        limit_gb=f"{limit_gb:.1f}",
    )
    await safe_send_message(bot, uid, text)

    admin_text = translate(
        Config.DEFAULT_LANGUAGE,
        "texts.abuse_notification_admin",
        user_id=uid,
        daily_gb=f"{daily_gb:.1f}",
        daily_limit=f"{limit_gb:.1f}",
        total_gb="0",
        total_limit=f"{Config.TRAFFIC_ABUSE_TOTAL_LIMIT_GB}",
    )
    await notify_admins(
        translate(Config.DEFAULT_LANGUAGE, "texts.admin_abuse_daily_header", user_id=uid)
        + f"\n\n{admin_text}"
    )
    logger.warning(f"ABUSE daily: user {uid} exceeded {daily_gb:.1f}GB")


async def _handle_total_abuse(
    uid: int,
    user_id: int,
    total_gb: float,
    limit_gb: float,
    user: dict[str, Any],
) -> None:
    lang = await db.get_user_language_by_user_id(user_id) or Config.DEFAULT_LANGUAGE
    text = translate(
        lang,
        "texts.abuse_total_traffic_exceeded",
        total_gb=f"{total_gb:.1f}",
    )
    await safe_send_message(bot, uid, text)
    logger.critical(f"ABUSE total: user {uid} exceeded {total_gb:.1f}GB")


async def _suspend_subscription(uid: int, user: dict[str, Any]) -> None:
    internal_uid = user.get("user_id", uid)
    base_email = get_user_panel_email(internal_uid, user)
    await panel.delete_client(base_email)
    await db.remove_subscription(internal_uid)
    admin_text = translate(
        Config.DEFAULT_LANGUAGE,
        "texts.abuse_notification_admin",
        user_id=uid,
        daily_gb="N/A",
        daily_limit=f"{Config.TRAFFIC_ABUSE_DAILY_LIMIT_GB}",
        total_gb="blocked",
        total_limit=f"{Config.TRAFFIC_ABUSE_TOTAL_LIMIT_GB}",
    )
    await notify_admins(
        translate(Config.DEFAULT_LANGUAGE, "texts.admin_abuse_total_header", user_id=uid)
        + f"\n\n{admin_text}"
    )


@log_error
async def cleanup_old_payments() -> None:
    while True:
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)

            def should_remove(p: dict[str, Any]) -> bool:
                if p.get("status") not in ("accepted", "rejected"):
                    return False
                processed = p.get("processed_at")
                if not processed:
                    return False
                try:
                    return datetime.fromisoformat(processed) < cutoff  # noqa: B023
                except Exception:  # noqa: BLE001
                    return False

            before = len(await json_db.read_all())
            await json_db.remove(should_remove)
            after = len(await json_db.read_all())
            removed = before - after
            if removed > 0:
                logger.info(f"Очищено {removed} старых записей о платежах")
            else:
                logger.info("✅ Старые платежи не найдены")

            await asyncio.sleep(Config.PAYMENT_CLEANUP_INTERVAL_SEC)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка очистки старых платежей: {type(e).__name__}: {e}")
            await asyncio.sleep(SECONDS_IN_HOUR)


class SSLUpdateTask:
    @staticmethod
    async def _run_ssh_update() -> bool:
        if not Config.SSH_HOST or not Config.SSH_USER:
            logger.warning("SSL задача пропущена: SSH_HOST/SSH_USER не настроены")
            return False

        ssh: paramiko.SSHClient | None = None
        shell = None
        try:

            def _connect() -> paramiko.SSHClient:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                if Config.SSH_PASSWORD:
                    client.connect(
                        Config.SSH_HOST,
                        username=Config.SSH_USER,
                        password=Config.SSH_PASSWORD,
                    )
                elif Config.SSH_KEY_PATH:
                    client.connect(
                        Config.SSH_HOST,
                        username=Config.SSH_USER,
                        key_filename=Config.SSH_KEY_PATH,
                    )
                else:
                    raise ConfigError("Не настроена SSH авторизация")
                return client

            last_error: Exception | None = None
            for attempt in range(3):
                try:
                    ssh = _connect()
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < 2:
                        await asyncio.sleep(1.0 * (2.0**attempt))
                    else:
                        raise
            if ssh is None:
                if last_error is not None:
                    raise last_error
                raise ConfigError("Не удалось подключиться по SSH")

            shell = ssh.invoke_shell()
            await asyncio.sleep(5)
            commands = [
                "/etc/init.d/nginx stop",
                "/etc/init.d/nginx stop",
                "x-ui",
                "20",
                "6",
                "y",
                "y",
                "",
                "80",
                "y",
                "",
                "0",
                "/etc/init.d/nginx start",
            ]
            for cmd in commands:
                shell.send(cmd + "\n")
                await asyncio.sleep(15)
            await asyncio.sleep(10)
            shell.close()
            shell = None
            ssh.close()
            ssh = None
            return True

        except Exception as e:
            logger.error(f"SSL SSH ошибка: {e}")
            raise
        finally:
            try:
                if shell is not None:
                    shell.close()
            except Exception:  # noqa: BLE001, S110
                pass
            try:
                if ssh is not None:
                    ssh.close()
            except Exception:  # noqa: BLE001, S110
                pass

    @staticmethod
    @log_error
    async def run() -> None:
        while True:
            try:
                await asyncio.sleep(432000)
                updated = await SSLUpdateTask._run_ssh_update()
                if updated:
                    await notify_admins(
                        translate(Config.DEFAULT_LANGUAGE, "texts.ssl_cert_updated")
                    )
                    logger.info("SSL-сертификат успешно обновлен")
            except asyncio.CancelledError:
                break
            except Exception as e:  # noqa: BLE001
                logger.error(f"SSL задача: {e}")
                await notify_admins(
                    translate(Config.DEFAULT_LANGUAGE, "texts.ssl_update_error")
                    + f"\n\n{html.escape(str(e))}"
                )
            await asyncio.sleep(Config.SUBSCRIPTION_CHECK_INTERVAL_SEC)


@log_error
async def cleanup_admin_test_subscriptions_periodic() -> None:
    while True:
        try:
            await asyncio.sleep(SECONDS_IN_HOUR)
            result = await cleanup_admin_test_subscriptions()
            if result["removed"] > 0:
                logger.info(f"🧹 Очищено {result['removed']} тестовых подписок админов")
            if result["errors"] > 0:
                logger.warning(f"⚠️ Ошибки при очистке тестовых: {result['errors']}")
            else:
                logger.info("✅ Тестовые подписки админов в порядке")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Ошибка задачи очистки тестовых подписок: {type(e).__name__}: {e}")
            await asyncio.sleep(SECONDS_IN_HOUR)


# --- FastAPI сервер ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class _SessionOrBearerAuth(HTTPBearer):
    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        auth = await super().__call__(request)
        if auth and auth.credentials:
            return auth
        cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
        if cookie_token:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=cookie_token)
        return None


security = _SessionOrBearerAuth(auto_error=False)

_SENSITIVE_USER_FIELDS = {
    "password_hash",
    "session_token",
    "session_expires_at",
    "session_created_at",
    "session_version",
}


def sanitize_user(user: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(user, dict):
        return user
    return {k: v for k, v in user.items() if k not in _SENSITIVE_USER_FIELDS}


_active_connections: dict[str, list[WebSocket]] = {}
_admin_connections: list[WebSocket] = []
_scheduled_tasks: set[asyncio.Task[Any]] = set()


class WebRegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=Config.PASSWORD_MIN_LENGTH, max_length=128)
    tg_id: int | None = Field(default=None, gt=0)


class WebLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class WebPasswordChangeRequest(BaseModel):
    old_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=Config.PASSWORD_MIN_LENGTH, max_length=128)


class WebTelegramLinkRequest(BaseModel):
    tg_id: int = Field(gt=0)
    password: str | None = Field(default=None, max_length=128)


class TelegramLoginRequest(BaseModel):
    tg_id: int = Field(gt=0)
    state: str = Field(min_length=16, max_length=128)


class CreateCheckoutRequest(BaseModel):
    plan_id: str
    method: str = "manual"
    custom_plan: dict[str, Any] | None = None


class BanUserRequest(BaseModel):
    reason: str = ""


class BroadcastRequest(BaseModel):
    message: str
    target_user_ids: list[int] | None = None


class CreateSubscriptionRequest(BaseModel):
    user_id: int | None = None
    plan_id: str
    plan_name: str | None = None
    price_rub: float | None = None
    ip_limit: int = 0
    traffic_gb: int = 0
    duration_days: int = 30
    servers: list[str] | None = None


class AbuseClearRequest(BaseModel):
    user_id: int
    reason: str | None = ""


class ExtendSubscriptionRequest(BaseModel):
    user_id: int | None = None
    days: int
    reason: str | None = ""


class CreateClientRequest(BaseModel):
    user_id: int
    email: str
    limit_ip: int = 0
    total_gb: int = 0
    days: int = 30
    inbound_ids: list[int] | None = None


# --- Новые модели для API ---
class CustomTariffRequest(BaseModel):
    traffic_gb: int
    ip_limit: int
    duration_days: int
    servers: list[str] | None = None


class ManualPaymentConfirmRequest(BaseModel):
    payment_id: str
    transaction_id: str | None = None
    amount: float


class BulkActionRequest(BaseModel):
    user_ids: list[int]
    action: str
    reason: str | None = ""


class PaymentVerifyRequest(BaseModel):
    payment_id: str
    status: str
    admin_note: str | None = ""


class DebugCleanupRequest(BaseModel):
    dry_run: bool = True
    cleanup_expired: bool = True
    cleanup_traffic_exhausted: bool = True
    cleanup_missing: bool = True


class AdminTokenRequest(BaseModel):
    admin_key: str = Field(min_length=1, max_length=256)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


class BOT_FastAPI:
    def __init__(self) -> None:
        @asynccontextmanager
        async def lifespan(app: FastAPI) -> Any:
            logger.info("FastAPI lifespan: startup")
            try:
                yield
            except asyncio.CancelledError:
                logger.info("FastAPI lifespan: cancelled")
            finally:
                logger.info("FastAPI lifespan: shutdown")

        self.app = FastAPI(
            title=f"{Config.VPN_NAME} API",
            version="1.0.0",
            docs_url="/docs" if Config.FASTAPI_DOCS else None,
            redoc_url="/redoc" if Config.FASTAPI_DOCS else None,
            lifespan=lifespan,
        )
        if Config.FASTAPI_CORS_ENABLED:
            allow_origins = list(
                dict.fromkeys(
                    o.strip() for o in Config.FASTAPI_ALLOW_ORIGINS.split(",") if o.strip()
                )
            )
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=allow_origins,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        self._setup_routes()

    def _setup_routes(self) -> None:
        # === Middleware ---

        @self.app.middleware("http")
        async def api_enabled_middleware(request: Request, call_next: Callable) -> JSONResponse:
            if not Config.BOT_API_ENABLED:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "API отключён в конфигурации."},
                )
            return await call_next(request)

        @self.app.middleware("http")
        async def logging_middleware(request: Request, call_next: Callable) -> JSONResponse:
            start_time = time.time()
            safe_path = re.sub(
                r"(Bearer\s+)[A-Za-z0-9_-]{10,}",
                r"\1***",
                str(request.url),
            )
            safe_path = re.sub(
                r"[?&](token|key|password|secret)=[^&]*",
                r"\1=***",
                safe_path,
                flags=re.IGNORECASE,
            )
            logger.info(
                f"HTTP {request.method} {safe_path} "
                f"from={request.client.host if request.client else 'unknown'}"
            )
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000
            log_request(
                request.method,
                str(request.url),
                status=response.status_code,
                duration_ms=duration_ms,
            )
            return response

        @self.app.middleware("http")
        async def security_middleware(request: Request, call_next: Callable) -> JSONResponse:
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
            if request.url.scheme == "https":
                response.headers["Strict-Transport-Security"] = (
                    f"max-age={SECONDS_IN_YEAR}; includeSubDomains"
                )
            if request.url.path.startswith("/api/"):
                response.headers["Cache-Control"] = "no-store"
            return response

        # === Rate limiting для FastAPI ---
        _api_request_times: dict[str, list[float]] = {}
        _API_RATE_LIMIT: int = Config.API_RATE_LIMIT
        _API_RATE_WINDOW: int = Config.API_RATE_WINDOW
        _sensitive_request_times: dict[str, list[float]] = {}
        _SENSITIVE_RATE_LIMIT: int = Config.API_RATE_LIMIT_SENSITIVE_MAX
        _SENSITIVE_RATE_WINDOW: int = Config.API_RATE_LIMIT_SENSITIVE_WINDOW
        _health_request_times: dict[str, float] = {}
        _HEALTH_RATE_LIMIT_SEC: float = 1.0
        _HEALTH_RATE_LIMIT_MAX_ENTRIES: int = 10000

        _SENSITIVE_PATHS = (
            "/api/v1/subscription/create",
            "/api/v1/subscription/renew",
            "/api/v1/subscription/trial",
            "/api/v1/payments/verify",
            "/api/v1/auth/telegram/start",
            "/api/v1/auth/telegram/link",
        )

        @self.app.middleware("http")
        async def sensitive_rate_limit_middleware(
            request: Request, call_next: Callable
        ) -> JSONResponse:
            path = request.url.path
            if not any(path.startswith(p) for p in _SENSITIVE_PATHS):
                return await call_next(request)

            client_ip = request.client.host if request.client else "unknown"
            now = time.time()

            if client_ip not in _sensitive_request_times:
                _sensitive_request_times[client_ip] = []

            _sensitive_request_times[client_ip] = [
                t for t in _sensitive_request_times[client_ip] if now - t < _SENSITIVE_RATE_WINDOW
            ]

            if len(_sensitive_request_times[client_ip]) >= _SENSITIVE_RATE_LIMIT:
                logger.warning(
                    f"Sensitive rate limit exceeded for IP {client_ip} "
                    f"({len(_sensitive_request_times[client_ip])}/{_SENSITIVE_RATE_LIMIT} in {_SENSITIVE_RATE_WINDOW}s)"
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": translate(Config.DEFAULT_LANGUAGE, "texts.rate_limited")},
                )

            _sensitive_request_times[client_ip].append(now)
            return await call_next(request)

        @self.app.middleware("http")
        async def health_rate_limit_middleware(
            request: Request, call_next: Callable
        ) -> JSONResponse:
            if request.url.path in ("/api/v1/health", "/api/v1/admin/health"):
                client_ip = request.client.host if request.client else "unknown"
                now = time.time()
                last = _health_request_times.get(client_ip, 0)
                if now - last < _HEALTH_RATE_LIMIT_SEC:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": translate(Config.DEFAULT_LANGUAGE, "texts.rate_limited")
                        },
                    )
                if len(_health_request_times) >= _HEALTH_RATE_LIMIT_MAX_ENTRIES:
                    cutoff = now - _HEALTH_RATE_LIMIT_SEC
                    stale = [ip for ip, ts in _health_request_times.items() if ts < cutoff]
                    for ip in stale:
                        _health_request_times.pop(ip, None)
                    if len(_health_request_times) >= _HEALTH_RATE_LIMIT_MAX_ENTRIES:
                        _health_request_times.clear()
                _health_request_times[client_ip] = now
            return await call_next(request)

        @self.app.middleware("http")
        async def rate_limit_middleware(request: Request, call_next: Callable) -> JSONResponse:
            if request.url.path in (
                "/docs",
                "/redoc",
                "/openapi.json",
                "/api/v1/health",
                "/api/v1/admin/health",
            ):
                return await call_next(request)

            client_ip = request.client.host if request.client else "unknown"
            now = time.time()

            if client_ip not in _api_request_times:
                _api_request_times[client_ip] = []

            _api_request_times[client_ip] = [
                t for t in _api_request_times[client_ip] if now - t < _API_RATE_WINDOW
            ]

            if len(_api_request_times[client_ip]) >= _API_RATE_LIMIT:
                logger.warning(
                    f"Rate limit exceeded for IP {client_ip} "
                    f"({len(_api_request_times[client_ip])}/{_API_RATE_LIMIT} in {_API_RATE_WINDOW}s)"
                )
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Слишком много запросов. Попробуйте позже."},
                )

            _api_request_times[client_ip].append(now)
            return await call_next(request)

        # === Tech work mode для FastAPI ---
        @self.app.middleware("http")
        async def tech_work_middleware(request: Request, call_next: Callable) -> JSONResponse:
            if not tech_work_service.is_enabled():
                return await call_next(request)

            if request.url.path in (
                "/docs",
                "/redoc",
                "/openapi.json",
                "/api/v1/health",
            ):
                return await call_next(request)

            auth_header = request.headers.get("authorization", "")
            token = (
                auth_header.replace(BEARER_PREFIX, "").strip()
                if auth_header.startswith("Bearer ")
                else auth_header.strip()
            )

            is_admin = False
            if _is_admin_token(token):
                is_admin = True
            elif token:
                user = await db.get_user_by_session_token(token)
                if user and await is_admin_user(to_int(user.get("telegram_id"), 0)):
                    is_admin = True
            elif request.url.path.startswith("/ws/admin/"):
                legacy_admin_key = request.url.path.split("/")[-1]
                if _is_admin_token(legacy_admin_key):
                    is_admin = True
                    logger.warning(
                        "DEPRECATED: WS admin авторизация через path-параметр. "
                        "Передавайте admin_key в Authorization: Bearer <key>."
                    )

            if not is_admin:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Ведутся технические работы. Попробуйте позже."},
                )

            return await call_next(request)

        # === Auth helpers ---
        async def _get_current_user(
            request: Request,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> str | None:
            token: str | None = None
            if credentials and credentials.credentials:
                token = credentials.credentials
            if not token:
                token = request.cookies.get(SESSION_COOKIE_NAME)
            if not token:
                return None
            if _is_admin_token(token):
                return "admin"
            if Config.BOT_API_KEY and secrets.compare_digest(token, Config.BOT_API_KEY):
                return "public"
            user = await db.get_user_by_session_token(token)
            if user:
                if await is_admin_user(to_int(user.get("telegram_id"), 0)):
                    return "admin"
                return str(user["user_id"])
            return None

        async def _require_admin(
            user: str | None = Depends(_get_current_user),
        ) -> str:
            if user != "admin":
                raise HTTPException(
                    status_code=403,
                    detail=translate(Config.DEFAULT_LANGUAGE, "texts.admin_required"),
                )
            return user

        # === Health ---
        @self.app.get("/api/v1/health")
        async def health() -> dict[str, str]:
            return {"status": "ok", "version": "1.0.0"}

        # === Admin: Users ---
        @self.app.get("/api/v1/users")
        async def api_get_users(
            page: int = Query(1, ge=1),
            limit: int = Query(50, ge=1, le=200),
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                offset = (page - 1) * limit
                cur = await db.conn.execute(
                    "SELECT * FROM users WHERE (web_id IS NOT NULL AND web_id != 0) OR (telegram_id IS NOT NULL AND telegram_id != 0) ORDER BY user_id LIMIT ? OFFSET ?",
                    (limit, offset),
                )
                rows = await cur.fetchall()
                users = [sanitize_user(dict(row)) for row in rows]
                total_cur = await db.conn.execute(
                    "SELECT COUNT(*) FROM users WHERE (web_id IS NOT NULL AND web_id != 0) OR (telegram_id IS NOT NULL AND telegram_id != 0)"
                )
                total_row = await total_cur.fetchone()
                total = int(total_row[0]) if total_row else 0
                return JSONResponse(
                    content={
                        "users": users,
                        "total": total,
                        "page": page,
                        "limit": limit,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_get_users: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/users/{user_id}")
        async def api_get_user(
            user_id: int,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                u = await db.get_user_by_any_id(user_id)
                if not u:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                return JSONResponse(content={"user": sanitize_user(u)})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_get_user {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/users/search")
        async def api_search_users(
            query: str = Query(..., min_length=1),
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                users = await db.search_users(query)
                return JSONResponse(content={"users": [sanitize_user(u) for u in users]})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_search_users: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/users/{user_id}/subscription-state")
        async def api_user_subscription_state(
            user_id: int,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                if _is_admin_token(credentials.credentials):
                    pass
                else:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")
                        },
                    )
            else:
                if session_user["user_id"] != user_id and not _is_admin_token(
                    credentials.credentials
                ):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.access_denied")
                        },
                    )
            try:
                state = await get_subscription_state(user_id)
                return JSONResponse(content={"state": state})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_user_subscription_state {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Stats ---
        @self.app.get("/api/v1/stats/overview")
        async def api_stats_overview() -> JSONResponse:
            try:
                stats = await db.get_user_stats()
                return JSONResponse(content=stats)
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_stats_overview: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/admin/panel-status")
        async def api_admin_panel_status(
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                panel_info = await panel.get_panel_info()
                server_status = await panel.get_server_status(sanitize=False)
                nodes = await panel.get_nodes(sanitize=False)
                return JSONResponse(
                    content={
                        "panel": panel_info,
                        "server_status": server_status,
                        "nodes": nodes,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_panel_status: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/stats/panel-status")
        async def api_stats_panel_status() -> JSONResponse:
            try:
                panel_info = await panel.get_panel_info()
                server_status = await panel.get_server_status(sanitize=True)
                nodes = await panel.get_nodes(sanitize=True)

                minimal_panel = {
                    "panel_version": panel_info.get("panel_version", ""),
                    "xray_version": panel_info.get("xray_version", ""),
                }

                minimal_status: dict[str, Any] = {}
                if isinstance(server_status, dict):
                    xray_obj = server_status.get("xray")
                    if isinstance(xray_obj, dict):
                        minimal_status["xray"] = {"state": xray_obj.get("state")}
                    elif xray_obj is not None:
                        minimal_status["xray"] = {"state": str(xray_obj)}
                    if "uptime" in server_status:
                        minimal_status["uptime"] = server_status["uptime"]

                minimal_nodes: list[dict[str, Any]] = []
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    minimal_nodes.append(
                        {
                            "name": node.get("name", ""),
                            "status": node.get("status", "offline"),
                            "uptime": node.get("uptime"),
                            "panel_version": node.get("panel_version", ""),
                            "xray_version": node.get("xray_version", ""),
                        }
                    )

                return JSONResponse(
                    content={
                        "panel": minimal_panel,
                        "server_status": minimal_status,
                        "nodes": minimal_nodes,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_stats_panel_status: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Tariffs ---
        @self.app.get("/api/v1/tariffs")
        async def api_get_tariffs() -> JSONResponse:
            try:
                active = get_all_active()
                result = []
                for plan in active:
                    item = dict(plan)
                    item["is_trial"] = bool(tariff_catalog.is_trial(plan))
                    servers = normalize_servers(item.get("servers"))
                    item["locations"] = [
                        str(get_location_by_code(s).get("label") or s) for s in servers
                    ]
                    result.append(item)
                return JSONResponse(content={"tariffs": result})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_get_tariffs: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Auth (public) ---
        @self.app.post("/api/v1/auth/register")
        async def api_auth_register(req: WebRegisterRequest, request: Request) -> JSONResponse:
            logger.info(f"API auth_register: username={req.username}")
            try:
                username = req.username.strip()
                if not username or not req.password:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.username_and_password_required",
                            )
                        },
                    )
                client_ip = request.client.host if request.client else "unknown"
                lockout = _check_auth_lockout(username, client_ip)
                if lockout is not None and lockout > 0:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.api_too_many_attempts",
                                lockout=lockout,
                            )
                        },
                    )
                now = time.time()
                if client_ip not in _registrations_per_ip:
                    _registrations_per_ip[client_ip] = []
                _registrations_per_ip[client_ip] = [
                    t for t in _registrations_per_ip[client_ip] if now - t < _REGISTRATION_WINDOW
                ]
                if len(_registrations_per_ip[client_ip]) >= _REGISTRATION_LIMIT:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.too_many_registrations_from_ip",
                            )
                        },
                    )
                existing = await db.get_user_by_username(username)
                if existing:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.username_already_registered",
                            )
                        },
                    )
                password_hash = pwd_context.hash(req.password)
                user = await db.create_web_account(username, password_hash, req.tg_id)
                if not user:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.failed_to_create_account",
                            )
                        },
                    )
                await db.ensure_ref_code_by_user_id(user["user_id"])
                _clear_auth_failures(username, client_ip)
                token = secrets.token_urlsafe(32)
                expires = (
                    datetime.now(timezone.utc) + timedelta(seconds=Config.SESSION_MAX_AGE)
                ).isoformat()
                await db.update_web_auth(
                    user["user_id"],
                    session_token=token,
                    session_expires_at=expires,
                    session_created_at=datetime.now(timezone.utc).isoformat(),
                )
                logger.info(
                    f"✅ API auth_register: пользователь зарегистрирован user_id={user['user_id']}"
                )
                return JSONResponse(
                    content={
                        "user_id": user["user_id"],
                        "web_id": user["web_id"],
                        "token": token,
                    },
                    status_code=201,
                    headers=_cookie_headers_for_session(token),
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_register: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/auth/login")
        async def api_auth_login(req: WebLoginRequest, request: Request) -> JSONResponse:
            logger.info(f"API auth_login: username={req.username}")
            try:
                username = req.username.strip()
                client_ip = request.client.host if request.client else "unknown"
                lockout = _check_auth_lockout(username, client_ip)
                if lockout is not None and lockout > 0:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.api_too_many_attempts",
                                lockout=lockout,
                            )
                        },
                    )
                cur = await db.conn.execute(
                    "SELECT * FROM users WHERE LOWER(username) = LOWER(?)",
                    (username,),
                )
                row = await cur.fetchone()
                user = dict(row) if row else None
                if not user or not pwd_context.verify(req.password, user.get("password_hash", "")):
                    _record_auth_failure(username, client_ip)
                    logger.warning(
                        f"⚠️ API auth_login: неверные учётные данные username={req.username}"
                    )
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_credentials")
                        },
                    )
                _clear_auth_failures(username, client_ip)
                token = secrets.token_urlsafe(32)
                expires = (
                    datetime.now(timezone.utc) + timedelta(seconds=Config.SESSION_MAX_AGE)
                ).isoformat()
                await db.update_web_auth(
                    user["user_id"],
                    session_token=token,
                    session_expires_at=expires,
                    session_created_at=datetime.now(timezone.utc).isoformat(),
                    web_last_login=datetime.now(timezone.utc).isoformat(),
                )
                if await is_admin_user(to_int(user.get("telegram_id"), 0)):
                    await _ensure_admin_subscription(user["user_id"])
                logger.info(f"✅ API auth_login: пользователь вошёл user_id={user['user_id']}")
                return JSONResponse(
                    content={
                        "user_id": user["user_id"],
                        "web_id": user["web_id"],
                        "token": token,
                    },
                    headers=_cookie_headers_for_session(token),
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_login: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/auth/me")
        async def api_auth_me(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            logger.info(
                f"API auth_me: пользователь запросил свой профиль user_id={user['user_id']}"
            )
            return JSONResponse(content={"user": sanitize_user(user)})

        @self.app.post("/api/v1/auth/logout")
        async def api_auth_logout(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if user:
                await db.update_web_auth(user["user_id"], session_token="", session_expires_at="")
                logger.info(f"API auth_logout: пользователь вышел user_id={user['user_id']}")
            return JSONResponse(
                content={"message": translate(Config.DEFAULT_LANGUAGE, "texts.api_logged_out")},
                headers=_cookie_headers_clear(),
            )

        @self.app.post("/api/v1/auth/change-password")
        async def api_auth_change_password(
            req: WebPasswordChangeRequest,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            if not pwd_context.verify(req.old_password, user.get("password_hash", "")):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.old_password_incorrect")
                    },
                )
            new_hash = pwd_context.hash(req.new_password)
            await db.update_web_auth(user["user_id"], password_hash=new_hash)
            await _notify_account_change(user["user_id"], "texts.password_changed_notification")
            return JSONResponse(
                content={
                    "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_password_changed")
                }
            )

        @self.app.post("/api/v1/auth/telegram/link")
        async def api_auth_telegram_link(
            req: WebTelegramLinkRequest,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            if user.get("telegram_id", 0) and user["telegram_id"] != req.tg_id:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.account_already_linked_to_different_telegram",
                        )
                    },
                )
            existing = await db.get_user_by_any_id(req.tg_id)
            if existing and existing.get("web_id") and existing["web_id"] == user["web_id"]:
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE, "texts.telegram_already_linked"
                        )
                    }
                )
            await db.reconcile_telegram_account(req.tg_id)
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            if req.password and not pwd_context.verify(req.password, user.get("password_hash", "")):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.password_incorrect")
                    },
                )
            existing = await db.get_user_by_any_id(req.tg_id)
            if existing and to_int(existing.get("user_id"), 0) != to_int(user.get("user_id"), 0):
                if existing.get("web_id") and existing["web_id"] != user["web_id"]:
                    await db.merge_accounts(user["user_id"], existing["user_id"])
                    merged_user = await db.get_user_by_session_token(credentials.credentials)
                    if merged_user:
                        user = merged_user
                    await db.update_web_auth(user["user_id"], telegram_id=req.tg_id)
                elif to_int(existing.get("telegram_id"), 0) == req.tg_id:
                    await db.update_web_auth(
                        existing["user_id"],
                        web_id=user.get("web_id"),
                        username=user.get("username"),
                        password_hash=user.get("password_hash"),
                        web_auth_method=user.get("web_auth_method"),
                        session_token=user.get("session_token"),
                        session_expires_at=user.get("session_expires_at"),
                        session_created_at=user.get("session_created_at"),
                        web_last_login=user.get("web_last_login"),
                        web_registered_at=user.get("web_registered_at"),
                    )
                    await db.delete_user(user["user_id"])
                    user = existing
                else:
                    await db.update_web_auth(user["user_id"], telegram_id=req.tg_id)
            else:
                if to_int(user.get("telegram_id"), 0) != req.tg_id:
                    await db.update_web_auth(user["user_id"], telegram_id=req.tg_id)
            await db.cleanup_telegram_phantoms(req.tg_id, user["user_id"])
            return JSONResponse(
                content={"message": translate(Config.DEFAULT_LANGUAGE, "texts.api_telegram_linked")}
            )

        @self.app.post("/api/v1/auth/telegram/unlink")
        async def api_auth_telegram_unlink(
            req: dict[str, Any] = Body(default={}),  # noqa: B008
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            password = str(req.get("password", "") or "")
            if password and not pwd_context.verify(password, user.get("password_hash", "")):
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.password_incorrect")
                    },
                )
            await _notify_account_change(user["user_id"], "texts.telegram_unlinked_notification")
            await db.update_web_auth(user["user_id"], telegram_id=0)
            return JSONResponse(
                content={
                    "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_telegram_unlinked")
                }
            )

        @self.app.post("/api/v1/auth/telegram/login")
        async def api_auth_telegram_login(
            req: TelegramLoginRequest,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            try:
                verified_tg_id = await consume_telegram_verification(req.state)
                if verified_tg_id is not None and verified_tg_id != req.tg_id:
                    logger.warning(
                        f"api_auth_telegram_login: tg_id mismatch: req={req.tg_id}, verified={verified_tg_id}"
                    )
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.telegram_id_verification_failed",
                            )
                        },
                    )

                tg_user = await db.get_user_by_any_id(req.tg_id)
                if not tg_user or not tg_user.get("web_id"):
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.no_web_account_linked"
                            )
                        },
                    )
                if tg_user["web_id"] != session_user["web_id"]:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.telegram_account_already_linked",
                            )
                        },
                    )
                token = secrets.token_urlsafe(32)
                expires = (
                    datetime.now(timezone.utc) + timedelta(seconds=Config.SESSION_MAX_AGE)
                ).isoformat()
                await db.update_web_auth(
                    tg_user["user_id"],
                    session_token=token,
                    session_expires_at=expires,
                    session_created_at=datetime.now(timezone.utc).isoformat(),
                    web_last_login=datetime.now(timezone.utc).isoformat(),
                    web_auth_method="telegram",
                )
                return JSONResponse(
                    content={
                        "user_id": tg_user["user_id"],
                        "web_id": tg_user["web_id"],
                        "token": token,
                    },
                    headers=_cookie_headers_for_session(token),
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_telegram_login: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/auth/telegram/start")
        async def api_auth_telegram_start() -> JSONResponse:
            try:
                state = secrets.token_urlsafe(32)
                success = await create_bot_auth_state(state, "web_login", ttl=300)
                if not success or not BOT_USERNAME:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.telegram_auth_not_configured",
                            )
                        },
                    )
                url = f"https://t.me/{BOT_USERNAME}?start=web_login_{state}"
                return JSONResponse(content={"url": url, "state": state})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_telegram_start: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/auth/telegram/link-start")
        async def api_auth_telegram_link_start(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            try:
                if not credentials:
                    return JSONResponse(
                        status_code=401,
                        content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                    )
                user = await db.get_user_by_session_token(credentials.credentials)
                if not user:
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")
                        },
                    )
                state = secrets.token_urlsafe(32)
                success = await create_bot_auth_state(
                    state, "link", ttl=300, session_token=credentials.credentials
                )
                if not success or not BOT_USERNAME:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.telegram_auth_not_configured",
                            )
                        },
                    )
                url = f"https://t.me/{BOT_USERNAME}?start=web_link_{state}"
                return JSONResponse(content={"url": url, "state": state})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_telegram_link_start: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/auth/telegram/status/{state}")
        async def api_auth_telegram_status(state: str) -> JSONResponse:
            try:
                auth_state = await get_bot_auth_state(state)
                if not auth_state:
                    return JSONResponse(content={"status": "pending"})
                if auth_state.get("completed"):
                    auth_token = auth_state.get("auth_token", "")
                    user = await db.get_user_by_session_token(auth_token) if auth_token else None
                    if not user:
                        return JSONResponse(content={"status": "expired"})
                    return JSONResponse(
                        content={
                            "status": "completed",
                            "token": auth_token,
                        },
                        headers=_cookie_headers_for_session(auth_token),
                    )
                return JSONResponse(content={"status": "pending"})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_telegram_status: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/auth/admin/token")
        async def api_auth_admin_token(req: AdminTokenRequest) -> JSONResponse:
            try:
                if not Config.BOT_ADMIN_KEY or not secrets.compare_digest(
                    req.admin_key, Config.BOT_ADMIN_KEY
                ):
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_admin_key")
                        },
                    )
                access_token = _create_admin_jwt(admin_id=0, refresh=False)
                refresh_token = _create_admin_jwt(admin_id=0, refresh=True)
                return JSONResponse(
                    content={
                        "access_token": access_token,
                        "refresh_token": refresh_token,
                        "token_type": "bearer",
                        "expires_in": Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_admin_token: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/auth/admin/refresh")
        async def api_auth_admin_refresh(req: RefreshTokenRequest) -> JSONResponse:
            try:
                payload = _verify_admin_jwt(req.refresh_token)
                if not payload or payload.get("type") != "refresh":
                    return JSONResponse(
                        status_code=401,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.invalid_refresh_token"
                            )
                        },
                    )
                access_token = _create_admin_jwt(admin_id=payload.get("admin_id", 0), refresh=False)
                return JSONResponse(
                    content={
                        "access_token": access_token,
                        "token_type": "bearer",
                        "expires_in": Config.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_auth_admin_refresh: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/config/features")
        async def api_config_features() -> JSONResponse:
            try:
                panel_types = Features.available_panel_types()
                return JSONResponse(
                    content={
                        "payment_methods": Features.available_payment_methods(),
                        "payment_card": Config.PAYMENT_CARD_NUMBER or None,
                        "yoomoney": Config.YOOMONEY_WALLET or None,
                        "panel_types": panel_types,
                        "features": Features.features_dict(),
                        "public_links": Features.public_links(),
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_config_features: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin endpoints ---
        @self.app.post("/api/v1/users/{user_id}/subscribe")
        async def api_subscribe(
            user_id: int,
            req: CreateSubscriptionRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin subscribe: user_id={user_id}, plan_id={req.plan_id}")
            try:
                user = await db.get_user_by_any_id(user_id)
                if not user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                internal_uid = user.get("user_id", user_id)
                plan = get_by_id(req.plan_id)
                plan_name = req.plan_name or (
                    plan.get("name", req.plan_id) if plan else req.plan_id
                )
                ip_limit = req.ip_limit or (plan.get("ip_limit", 0) if plan else 0)
                traffic_gb = req.traffic_gb or (plan.get("traffic_gb", 0) if plan else 0)
                servers = req.servers or (normalize_servers(plan.get("servers")) if plan else [])
                await db.update_user(
                    internal_uid,
                    force=True,
                    has_subscription=1,
                    plan_text=plan_name,
                    subscription_id=req.plan_id,
                    ip_limit=ip_limit,
                    traffic_gb=traffic_gb,
                    vpn_url=servers[0] if servers else "",
                )
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE, "texts.api_subscription_created"
                        )
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_subscribe {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/users/{user_id}/unsubscribe")
        async def api_unsubscribe(
            user_id: int,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin unsubscribe: user_id={user_id}")
            try:
                target_user = await db.get_user_by_any_id(user_id)
                if target_user:
                    tg_id = target_user.get("telegram_id", 0)
                    if tg_id and await is_admin_user(tg_id):
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": translate(
                                    Config.DEFAULT_LANGUAGE,
                                    "texts.cannot_modify_admin_user",
                                )
                            },
                        )
                internal_uid = target_user.get("user_id", user_id) if target_user else user_id
                await db.update_user(
                    internal_uid,
                    force=True,
                    has_subscription=0,
                    plan_text="",
                    plan_servers="",
                    subscription_id="",
                    ip_limit=0,
                    vpn_url="",
                    traffic_gb=0,
                    expiry_sub_datatime="",
                )
                logger.info(f"✅ API admin unsubscribe: подписка удалена user_id={user_id}")
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE, "texts.api_subscription_removed"
                        )
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_unsubscribe {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/admin/abuse-users")
        async def api_get_abuse_users(
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            abuse_users = await db.get_users_with_abuse()
            return JSONResponse(content={"users": abuse_users})

        @self.app.post("/api/v1/admin/users/{user_id}/clear-abuse")
        async def api_clear_abuse(
            user_id: int,
            req: AbuseClearRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin clear_abuse: user_id={user_id}")
            try:
                target_user = await db.get_user_by_any_id(user_id)
                if not target_user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                tg_id = target_user.get("telegram_id", 0)
                if tg_id and await is_admin_user(tg_id):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.cannot_modify_admin_user",
                            )
                        },
                    )
                internal_uid = target_user.get("user_id", user_id)
                await db.update_user(internal_uid, force=True, abuse_status="")
                if target_user:
                    await safe_send_message(
                        bot,
                        tg_id,
                        translate(Config.DEFAULT_LANGUAGE, "texts.abuse_lifted"),
                    )
                    if not target_user.get("vpn_url"):
                        await recreate_subscription_for_user(tg_id, target_user)
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.abuse_admin_cleared",
                            user_id=user_id,
                        )
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_clear_abuse {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/users/{user_id}/extend")
        async def api_extend(
            user_id: int,
            req: ExtendSubscriptionRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin extend: user_id={user_id}, days={req.days}")
            try:
                user = await db.get_user_by_any_id(user_id)
                if not user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                internal_uid = user.get("user_id", user_id)
                extended = await panel.extend_client_expiry_by_user_id(internal_uid, req.days)
                logger.info(f"API admin extend: user_id={user_id}, success={extended}")
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.api_extended_days",
                            days=req.days,
                        ),
                        "success": extended,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_extend {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.delete("/api/v1/users/{user_id}")
        async def api_delete_user(
            user_id: int,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.warning(f"⚠️ API admin delete_user: user_id={user_id}")
            try:
                target_user = await db.get_user_by_any_id(user_id)
                if target_user:
                    tg_id = target_user.get("telegram_id", 0)
                    if tg_id and await is_admin_user(tg_id):
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": translate(
                                    Config.DEFAULT_LANGUAGE,
                                    "texts.cannot_delete_admin_user",
                                )
                            },
                        )
                internal_uid = target_user.get("user_id", user_id) if target_user else user_id
                await db.delete_user(internal_uid)
                logger.info(f"✅ API admin delete_user: пользователь удалён user_id={user_id}")
                return JSONResponse(
                    content={
                        "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_user_deleted")
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_delete_user {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/users/{user_id}/ban")
        async def api_ban_user(
            user_id: int,
            req: BanUserRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin ban_user: user_id={user_id}, reason={req.reason}")
            try:
                target_user = await db.get_user_by_any_id(user_id)
                if not target_user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                tg_id = target_user.get("telegram_id", 0)
                if tg_id and await is_admin_user(tg_id):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.cannot_modify_admin_user",
                            )
                        },
                    )
                internal_uid = target_user.get("user_id", user_id)
                success = await db.ban_user_by_uid(internal_uid, reason=req.reason)
                if not success:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.failed_to_ban_user")
                        },
                    )
                logger.info(f"✅ API admin ban_user: пользователь забанен user_id={user_id}")
                return JSONResponse(
                    content={
                        "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_user_banned"),
                        "success": True,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_ban_user {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/users/{user_id}/unban")
        async def api_unban_user(
            user_id: int,
            req: BanUserRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin unban_user: user_id={user_id}")
            try:
                target_user = await db.get_user_by_any_id(user_id)
                if not target_user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                tg_id = target_user.get("telegram_id", 0)
                if tg_id and await is_admin_user(tg_id):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.cannot_modify_admin_user",
                            )
                        },
                    )
                internal_uid = target_user.get("user_id", user_id)
                success = await db.unban_user_by_uid(internal_uid)
                if not success:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.failed_to_unban_user"
                            )
                        },
                    )
                logger.info(f"✅ API admin unban_user: разбанен user_id={user_id}")
                return JSONResponse(
                    content={
                        "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_user_unbanned"),
                        "success": True,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_unban_user {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/users/{user_id}/ban-by-uid")
        async def api_ban_user_by_uid(
            user_id: int,
            req: BanUserRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin ban_by_uid: uid={user_id}, reason={req.reason}")
            try:
                user = await db.get_user_by_any_id(user_id)
                if not user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                success = await db.ban_user_by_uid(user_id, reason=req.reason)
                if not success:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.failed_to_ban_user")
                        },
                    )
                logger.info(f"✅ API admin ban_by_uid: пользователь забанен uid={user_id}")
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE, "texts.api_user_banned_by_uid"
                        ),
                        "success": True,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_ban_user_by_uid {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/users/{user_id}/unban-by-uid")
        async def api_unban_user_by_uid(
            user_id: int,
            req: BanUserRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin unban_by_uid: uid={user_id}")
            try:
                user = await db.get_user_by_any_id(user_id)
                if not user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                success = await db.unban_user_by_uid(user_id)
                if not success:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.failed_to_unban_user"
                            )
                        },
                    )
                logger.info(f"✅ API admin unban_by_uid: разбанен uid={user_id}")
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE, "texts.api_user_unbanned_by_uid"
                        ),
                        "success": True,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_unban_user_by_uid {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/payments/confirm/{payment_id}")
        async def api_confirm_payment(
            payment_id: str,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.warning(
                f"DEPRECATED: /payments/confirm/{payment_id}, "
                f"используйте /payments/verify/{payment_id} с status=confirmed"
            )
            try:
                payment = await json_db.claim_pending_payment(payment_id, 0, "accept")
                if not payment:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.payment_not_found")
                        },
                    )
                logger.info(
                    f"✅ API admin confirm_payment: платёж подтверждён payment_id={payment_id}"
                )
                return JSONResponse(
                    content={
                        "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_payment_confirmed")
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_confirm_payment {payment_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/payments/reject/{payment_id}")
        async def api_reject_payment(
            payment_id: str,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.warning(
                f"DEPRECATED: /payments/reject/{payment_id}, "
                f"используйте /payments/verify/{payment_id} с status=rejected"
            )
            try:
                payment = await json_db.claim_pending_payment(payment_id, 0, "reject")
                if not payment:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.payment_not_found")
                        },
                    )
                logger.info(f"⚠️ API admin reject_payment: платёж отклонён payment_id={payment_id}")
                return JSONResponse(
                    content={
                        "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_payment_rejected")
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_reject_payment {payment_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/payments/pending")
        async def api_pending_payments(
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                payments = await json_db.read_all()
                pending = [p for p in payments if p.get("status") == "pending"]
                logger.info(f"API admin pending_payments: {len(pending)} ожидающих")
                return JSONResponse(content={"payments": pending})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_pending_payments: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/payments/create-checkout")
        async def api_create_checkout(
            req: CreateCheckoutRequest,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            token = credentials.credentials
            session_user = await db.get_user_by_session_token(token)
            if not session_user and not _is_admin_token(token):
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            try:
                plan = None
                amount = 0.0
                plan_name = ""
                plan_type = "catalog"
                custom_plan_data = None

                if req.plan_id == "custom" and req.custom_plan:
                    custom_plan_data = req.custom_plan
                    plan_name = custom_plan_data.get("name", "Custom Plan")
                    amount = float(custom_plan_data.get("price_rub", 0))
                    plan_type = "custom"
                    if amount <= 0:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": translate(
                                    Config.DEFAULT_LANGUAGE,
                                    "texts.invalid_custom_plan_price",
                                )
                            },
                        )
                else:
                    plan = get_by_id(req.plan_id)
                    if not plan or not plan.get("active", True):
                        return JSONResponse(
                            status_code=404,
                            content={
                                "error": translate(
                                    Config.DEFAULT_LANGUAGE, "texts.tariff_not_found"
                                )
                            },
                        )
                    amount = float(plan.get("price_rub", 0))
                    plan_name = plan.get("name", req.plan_id)
                    if amount <= 0:
                        return JSONResponse(
                            status_code=400,
                            content={
                                "error": translate(
                                    Config.DEFAULT_LANGUAGE,
                                    "texts.invalid_tariff_price",
                                )
                            },
                        )

                user_id = session_user["user_id"] if session_user else 0
                tg_id = to_int(session_user.get("telegram_id") if session_user else 0, 0)
                if user_id and await is_active_subscription(
                    user_id, notify_user_about_cleanup=True
                ):
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.active_subscription_exists",
                            ),
                            "wait_admin": True,
                        },
                    )
                payment_id = f"pay_{user_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
                payment_data = {
                    "payment_id": payment_id,
                    "user_id": user_id,
                    "tg_id": tg_id,
                    "plan_id": req.plan_id,
                    "plan_type": plan_type,
                    "plan_name": plan_name,
                    "amount": amount,
                    "currency": "RUB",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "pending",
                    "payment_method": req.method,
                }
                if user_id == 0:
                    logger.warning(
                        "api_create_checkout: pending payment created without authenticated user (user_id=0)"
                    )
                if custom_plan_data:
                    payment_data["custom_plan"] = custom_plan_data
                added = await json_db.add_pending_for_user(user_id, payment_data)
                if not added:
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.payment_request_already_exists",
                            )
                        },
                    )
                checkout_url = ""
                if req.method == "yoomoney" and Config.YOOMONEY_WALLET:
                    checkout_params = {
                        "receiver": Config.YOOMONEY_WALLET,
                        "quickpay-form": "shop",
                        "targets": f"{Config.VPN_NAME} {payment_id}",
                        "paymentType": "AC",
                        "sum": amount,
                        "label": payment_id,
                    }
                    checkout_url = "https://yoomoney.ru/quickpay/confirm?" + urlencode(
                        checkout_params
                    )
                elif req.method == "yoomoney":
                    logger.warning(
                        "api_create_checkout: yoomoney method requested but YOOMONEY_WALLET is not configured"
                    )
                if not checkout_url:
                    logger.warning(
                        f"api_create_checkout: empty checkout_url for method={req.method} (payment_id={payment_id})"
                    )
                return JSONResponse(
                    content={"checkout_url": checkout_url, "payment_id": payment_id}
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_create_checkout: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/operations/await")
        async def api_await_operations(
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info("API admin await_operations: запрос списка")
            try:
                payments = await json_db.read_all()
                pending = [p for p in payments if p.get("status") == "pending"]
                return JSONResponse(content={"await_payments": pending})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_await_operations: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/operations/partner")
        async def api_partner_operations(
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info("API admin partner_operations: запрос списка")
            try:
                ops = await get_pending_partner_operations()
                return JSONResponse(content={"partner_operations": ops})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_partner_operations: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/broadcast/send")
        async def api_broadcast(
            req: BroadcastRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(
                f"API admin broadcast: message_len={len(req.message) if req.message else 0}"
            )
            try:
                result = await notify_all_users(req.message)
                logger.info(
                    f"API admin broadcast: sent={result.get('sent', 0)}, failed={result.get('failed', 0)}"
                )
                return JSONResponse(content=result)
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_broadcast: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/panel/clients/create")
        async def api_create_client(
            req: CreateClientRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(
                f"API admin create_client: email={req.email}, ip={req.limit_ip}, gb={req.total_gb}"
            )
            try:
                inbound_ids = req.inbound_ids or await panel.get_matching_inbound_ids(None)
                client_data = await panel.create_client(
                    email=req.email,
                    limit_ip=req.limit_ip,
                    total_gb=req.total_gb,
                    days=req.days,
                    tg_id=req.user_id,
                    inbound_ids=inbound_ids,
                )
                logger.info(f"API admin create_client: success={client_data is not None}")
                return JSONResponse(content={"client": client_data})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_create_client: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/panel/clients")
        async def api_list_clients(
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info("API admin list_clients")
            try:
                clients = await panel.get_all_clients()
                return JSONResponse(content={"clients": clients})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_list_clients: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.delete("/api/v1/panel/clients/{sub_id}")
        async def api_delete_client(
            sub_id: str,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin delete_client: sub_id={sub_id}")
            try:
                success = await panel.delete_client(sub_id)
                logger.info(f"API admin delete_client: sub_id={sub_id}, success={success}")
                return JSONResponse(
                    content={
                        "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_client_deleted"),
                        "success": success,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_delete_client {sub_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Пользовательский личный кабинет ---
        @self.app.get("/api/v1/profile")
        async def api_get_profile(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            if bool(user.get("banned", False)):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.account_banned"),
                        "banned": True,
                        "ban_reason": str(user.get("ban_reason", "")),
                    },
                )
            if await is_admin_user(to_int(user.get("telegram_id"), 0)):
                try:
                    await _ensure_admin_subscription(user["user_id"])
                    user = await db.get_user_by_any_id(user["user_id"]) or user
                except Exception:  # noqa: BLE001, S110
                    pass
            try:
                lang = (
                    await db.get_user_language_by_user_id(user["user_id"])
                    or Config.DEFAULT_LANGUAGE
                )
                db_uid = user["user_id"]
                sub_state = await get_subscription_state(db_uid)
                trust_score = await db.get_trust_score(db_uid)
                ref_count = await db.count_referrals(db_uid)
                ref_paid = await db.count_referrals_paid(db_uid)
                ref_code = user.get("ref_code", "")
                if not ref_code:
                    tg_id_for_ref = to_int(user.get("telegram_id"), 0)
                    ref_code = (
                        await db.ensure_ref_code(tg_id_for_ref) or "" if tg_id_for_ref else ""
                    )
                is_partner = bool(user.get("is_mate"))
                partner_data: dict[str, Any] = {}
                if is_partner:
                    partner_data = {
                        "mate_balance": to_float(user.get("mate_balance", 0), 0.0),
                        "mate_commission_total": to_float(
                            user.get("mate_commission_total", 0), 0.0
                        ),
                        "mate_status": str(user.get("mate_status", "") or ""),
                        "mate_followers": to_int(user.get("mate_followers", 0), 0),
                        "mate_avg_reach": to_int(user.get("mate_avg_reach", 0), 0),
                        "mate_period_months": to_int(user.get("mate_period_months", 0), 0),
                        "mate_ref_link_code": str(user.get("mate_ref_link_code", "") or ""),
                        "mate_subscription_id": str(user.get("mate_subscription_id", "") or ""),
                        "mate_expiry": str(user.get("mate_expiry", "") or ""),
                    }
                discount = calculate_discount_percent(trust_score)
                sub_data: dict[str, Any] = {}
                if sub_state.get("status") == "active":
                    sub_data = {
                        "status": "active",
                        "plan_text": str(user.get("plan_text", "") or ""),
                        "traffic_gb": to_float(user.get("traffic_gb", 0), 0.0),
                        "extra_sub_gb": to_int(user.get("extra_sub_gb", 0), 0),
                        "ip_limit": to_int(user.get("ip_limit", 0), 0),
                        "vpn_url": str(user.get("vpn_url", "") or ""),
                        "plan_servers": parse_stored_servers(user.get("plan_servers")),
                        "used_gb": round(sub_state.get("used_gb", 0), 2),
                        "max_expiry": sub_state.get("max_expiry", 0),
                        "expiry_sub_datatime": str(user.get("expiry_sub_datatime", "") or ""),
                    }
                else:
                    sub_data = {"status": sub_state.get("status", "none")}
                ref_link = get_ref_link(ref_code) if ref_code else ""
                admin_sub_data = None
                panel_types = Features.available_panel_types()
                if await is_admin_user(to_int(user.get("telegram_id"), 0)):
                    admin_vpn_url = str(user.get("vpn_url", "") or "")
                    admin_sub_url = (
                        build_subscription_url(admin_vpn_url)
                        if panel_types["main"] and admin_vpn_url
                        else ""
                    )
                    admin_json_url = (
                        build_json_subscription_url(admin_vpn_url)
                        if panel_types["json"] and admin_vpn_url
                        else ""
                    )
                    admin_sub_data = {
                        "url": admin_sub_url,
                        "json_url": admin_json_url,
                    }
                partner_sub_data = None
                if is_partner:
                    mate_sub_id = user.get("mate_subscription_id", "")
                    mate_expiry = user.get("mate_expiry", "")
                    partner_sub_data = {
                        "sub_id": mate_sub_id,
                        "expiry": mate_expiry,
                        "url": (build_subscription_url(mate_sub_id) if mate_sub_id else ""),
                        "json_url": (
                            build_json_subscription_url(mate_sub_id) if mate_sub_id else ""
                        ),
                    }
                try:
                    pending_ops = await get_pending_partner_operations()
                    pending_app = any(
                        str(o.get("user_id")) == str(user.get("telegram_id"))
                        and o.get("op_type") == "partner_new"
                        for o in pending_ops
                    )
                except Exception:  # noqa: BLE001
                    pending_app = False
                try:
                    has_pending_payment = await json_db.has_pending_payment_for_user(
                        user["user_id"]
                    )
                except Exception:  # noqa: BLE001
                    has_pending_payment = False
                return JSONResponse(
                    content={
                        "user_id": user["user_id"],
                        "telegram_id": to_int(user.get("telegram_id", 0), 0),
                        "web_id": user.get("web_id", 0),
                        "username": str(user.get("username", "") or ""),
                        "login": str(user.get("username", "") or ""),
                        "language": lang,
                        "trust_score": trust_score,
                        "discount_percent": discount,
                        "subscription": sub_data,
                        "referral": {
                            "ref_code": ref_code,
                            "ref_link": ref_link,
                            "referrals_count": ref_count,
                            "referrals_paid": ref_paid,
                        },
                        "partner": partner_data if is_partner else {},
                        "is_partner": is_partner,
                        "pending_partner_application": pending_app,
                        "trial_used": bool(user.get("trial_used")),
                        "join_date": str(user.get("join_date", "") or ""),
                        "is_admin": await is_admin_user(to_int(user.get("telegram_id"), 0)),
                        "has_pending_payment": bool(has_pending_payment),
                        "admin_subscription": admin_sub_data,
                        "partner_subscription": partner_sub_data,
                        "has_password": bool(user.get("password_hash", "")),
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_get_profile: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.patch("/api/v1/profile/language")
        async def api_change_language(
            req: dict[str, str] = Body(),  # noqa: B008
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            lang = str(req.get("language", "")).strip().lower()
            if lang not in LANGUAGES:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.language_not_supported")
                    },
                )
            ok = await db.set_user_language_by_user_id(user["user_id"], lang)
            if not ok:
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE, "texts.failed_to_update_language"
                        )
                    },
                )
            return JSONResponse(
                content={
                    "message": "Language updated",
                    "language": lang,
                    "display_name": get_language_display_name(lang),
                }
            )

        # === Создание подписки через API ---
        @self.app.post("/api/v1/subscription/create")
        async def api_create_subscription(
            req: CreateSubscriptionRequest,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            user_id = session_user["user_id"]
            telegram_id = to_int(session_user.get("telegram_id"), 0)
            if await is_admin_user(telegram_id):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.admins_cannot_purchase")
                    },
                )
            if not telegram_id:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.link_telegram_for_trial")
                    },
                )
            try:
                state = await ensure_subscription_state(user_id, notify_user_about_cleanup=True)
                if state.get("status") == "active" and not is_expiring_soon(
                    state, Config.EXPIRY_ALERT_DAYS
                ):
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.active_subscription_exists",
                            ),
                            "state": state,
                        },
                    )
                plan = get_by_id(req.plan_id)
                if not plan or not plan.get("active", True):
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.tariff_not_found_or_inactive",
                            )
                        },
                    )
                if tariff_catalog.is_trial(plan):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.use_trial_endpoint_for_trial_plans",
                            )
                        },
                    )
                plan_name = req.plan_name or plan.get("name", req.plan_id)
                ip_limit = req.ip_limit or plan.get("ip_limit", 0)
                traffic_gb = req.traffic_gb or plan.get("traffic_gb", 0)
                servers = req.servers or normalize_servers(plan.get("servers"))
                duration_days = req.duration_days or plan.get("duration_days", 30)
                custom_plan: dict[str, Any] = {
                    "id": req.plan_id,
                    "name": plan_name,
                    "price_rub": req.price_rub or plan.get("price_rub", 0),
                    "ip_limit": ip_limit,
                    "traffic_gb": traffic_gb,
                    "duration_days": duration_days,
                    "servers": servers,
                    "active": True,
                }
                vpn_url = await create_subscription(
                    telegram_id,
                    custom_plan,
                    days_override=duration_days,
                    earn_trust=True,
                    paid_amount=req.price_rub,
                )
                if vpn_url:
                    return JSONResponse(
                        content={
                            "message": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.api_subscription_created",
                            ),
                            "vpn_url": vpn_url,
                            "plan_name": plan_name,
                        },
                        status_code=201,
                    )
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.failed_to_create_subscription",
                        )
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_create_subscription: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Продление подписки ---
        @self.app.post("/api/v1/subscription/renew")
        async def api_renew_subscription(
            req: CreateSubscriptionRequest,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            _user_id = session_user["user_id"]
            telegram_id = to_int(session_user.get("telegram_id"), 0)
            if not telegram_id:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.link_telegram_for_trial")
                    },
                )
            try:
                plan = get_by_id(req.plan_id)
                if not plan or not plan.get("active", True):
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.tariff_not_found_or_inactive",
                            )
                        },
                    )
                if tariff_catalog.is_trial(plan):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.cannot_renew_with_trial_plan",
                            )
                        },
                    )
                plan_name = req.plan_name or plan.get("name", req.plan_id)
                ip_limit = req.ip_limit or plan.get("ip_limit", 0)
                traffic_gb = req.traffic_gb or plan.get("traffic_gb", 0)
                servers = req.servers or normalize_servers(plan.get("servers"))
                duration_days = req.duration_days or plan.get("duration_days", 30)
                custom_plan: dict[str, Any] = {
                    "id": req.plan_id,
                    "name": plan_name,
                    "price_rub": req.price_rub or plan.get("price_rub", 0),
                    "ip_limit": ip_limit,
                    "traffic_gb": traffic_gb,
                    "duration_days": duration_days,
                    "servers": servers,
                    "active": True,
                }
                vpn_url = await renew_subscription(
                    telegram_id,
                    custom_plan,
                    earn_trust=True,
                    paid_amount=req.price_rub,
                )
                if vpn_url:
                    return JSONResponse(
                        content={
                            "message": "Subscription renewed",
                            "vpn_url": vpn_url,
                            "plan_name": plan_name,
                        }
                    )
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.failed_to_renew_subscription",
                        )
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_renew_subscription: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Пробный тариф ---
        @self.app.post("/api/v1/subscription/trial")
        async def api_trial_subscription(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            user_id = session_user["user_id"]
            telegram_id = to_int(session_user.get("telegram_id"), 0)
            if await is_admin_user(telegram_id):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.trial_for_admins_via_telegram_bot",
                        )
                    },
                )
            if not telegram_id:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.link_telegram_for_trial")
                    },
                )
            try:
                if await is_active_subscription(user_id, notify_user_about_cleanup=True):
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.active_subscription_exists",
                            )
                        },
                    )
                plan = get_by_id("trial")
                if not plan or not is_trial_plan(plan):
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.trial_plan_not_found"
                            )
                        },
                    )
                user = await db.get_user_by_any_id(telegram_id)
                if user and (user.get("trial_used") or user.get("has_subscription")):
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.trial_already_used_or_has_subscription",
                            )
                        },
                    )
                vpn_url = await create_subscription(
                    telegram_id,
                    plan,
                    plan_suffix=translate(Config.DEFAULT_LANGUAGE, "texts.trial_plan_suffix"),
                    earn_trust=False,
                )
                if vpn_url:
                    await db.mark_trial_used(telegram_id)
                    return JSONResponse(
                        content={
                            "message": "Trial subscription created",
                            "vpn_url": vpn_url,
                            "plan_name": plan.get("name", "trial"),
                        },
                        status_code=201,
                    )
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.failed_to_create_trial_subscription",
                        )
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_trial_subscription: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Получение VPN-ссылки ---
        @self.app.get("/api/v1/subscription/link")
        async def api_get_subscription_link(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            try:
                sub_id = normalize_sub_id(user.get("vpn_url"))
                if not sub_id:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.no_active_subscription"
                            )
                        },
                    )
                vpn_url = build_subscription_url(sub_id)
                json_vpn_url = build_json_subscription_url(sub_id)
                return JSONResponse(
                    content={
                        "subscription_id": sub_id,
                        "vpn_url": vpn_url,
                        "json_vpn_url": json_vpn_url,
                        "plan_text": str(user.get("plan_text", "") or ""),
                        "traffic_gb": to_float(user.get("traffic_gb", 0), 0.0),
                        "ip_limit": to_int(user.get("ip_limit", 0), 0),
                        "plan_servers": parse_stored_servers(user.get("plan_servers")),
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_get_subscription_link: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Дополнительный трафик ---
        @self.app.post("/api/v1/subscription/add-traffic")
        async def api_add_traffic(
            req: dict[str, Any],
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            user_id = session_user["user_id"]
            try:
                extra_gb = to_int(req.get("gb", 0), 0)
                if extra_gb <= 0:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.gb_must_be_positive")
                        },
                    )
                await db.add_extra_traffic(user_id, extra_gb)
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.api_added_gb",
                            gb=extra_gb,
                        ),
                        "extra_gb": extra_gb,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_add_traffic: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Проверка подписки по sub_id (публичный) ---
        @self.app.get("/api/v1/subscription/verify/{sub_id}")
        async def api_verify_subscription(
            sub_id: str,
        ) -> JSONResponse:
            try:
                clients_ok, clients = await panel.find_clients_by_sub_id_safe(sub_id)
                if not clients_ok:
                    return JSONResponse(
                        status_code=500,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.panel_unavailable")
                        },
                    )
                if not clients:
                    return JSONResponse(content={"valid": False, "reason": "not_found"})
                now_ms = int(time.time() * 1000)
                active = False
                max_expiry = 0
                for c in clients:
                    exp = to_int(c.get("expiryTime"), 0)
                    if exp > 0 and exp > now_ms:
                        active = True
                        max_expiry = max(max_expiry, exp)
                    if to_int(c.get("totalGB", 0), 0) > 0:
                        used = to_int(c.get("up", 0), 0) + to_int(c.get("down", 0), 0)
                        if used >= to_int(c.get("totalGB", 0), 0):
                            active = False
                return JSONResponse(
                    content={
                        "valid": active,
                        "max_expiry": max_expiry,
                        "clients_count": len(clients),
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_verify_subscription: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Локации / Серверы (публичный) ---
        @self.app.get("/api/v1/locations")
        async def api_get_locations() -> JSONResponse:
            try:
                locations = get_custom_locations()
                return JSONResponse(content={"locations": locations})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_get_locations: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Партнёрская программа (публично) ---
        @self.app.get("/api/v1/partner/public-info")
        async def api_partner_public_info() -> JSONResponse:
            try:
                return JSONResponse(
                    content={
                        "commission_percent": Config.PARTNER_COMMISSION_PERCENT,
                        "min_followers": Config.PARTNER_MIN_FOLLOWERS,
                        "min_avg_reach": Config.PARTNER_MIN_AVG_REACH,
                        "required_socials": ", ".join(Config.required_socials_list()),
                        "terms_url": Config.PARTNER_TERMS_URL,
                        "min_period_months": Config.PARTNER_MIN_PERIOD_MONTHS,
                        "max_period_months": Config.PARTNER_MAX_PERIOD_MONTHS,
                        "bonus_days_min": Config.PARTNER_BONUS_DAYS_MIN,
                        "bonus_days_max": Config.PARTNER_BONUS_DAYS_MAX,
                        "trust_points_min": Config.PARTNER_TRUST_POINTS_MIN,
                        "trust_points_max": Config.PARTNER_TRUST_POINTS_MAX,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_partner_public_info: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Партнёрский кабинет ---
        @self.app.get("/api/v1/partner/profile")
        async def api_partner_profile(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            user_id = user["user_id"]
            if not bool(user.get("is_mate")):
                pending = bool(user.get("pending_partner_application"))
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.not_a_partner"),
                        "pending_partner_application": pending,
                    },
                )
            try:
                ref_count = await db.count_partner_referrals(user_id)
                ref_paid = await db.count_partner_referrals_paid(user_id)
                ref_link_code = str(user.get("mate_ref_link_code", "") or "")
                ref_link = get_ref_link(ref_link_code) if ref_link_code else ""
                commission_total = to_float(user.get("mate_commission_total", 0), 0.0)
                conversion_rate = round((ref_paid / ref_count * 100) if ref_count > 0 else 0, 2)
                avg_commission_per_paid = round(
                    commission_total / ref_paid if ref_paid > 0 else 0, 2
                )
                return JSONResponse(
                    content={
                        "balance": to_float(user.get("mate_balance", 0), 0.0),
                        "commission_total": commission_total,
                        "referrals_count": ref_count,
                        "referrals_paid": ref_paid,
                        "conversion_rate": conversion_rate,
                        "avg_commission_per_paid": avg_commission_per_paid,
                        "period_months": to_int(user.get("mate_period_months", 0), 0),
                        "subscription_id": str(user.get("mate_subscription_id", "") or ""),
                        "expiry": str(user.get("mate_expiry", "") or ""),
                        "ref_link_code": ref_link_code,
                        "ref_link": ref_link,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_partner_profile: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/partner/apply")
        async def api_partner_apply(
            req: dict[str, Any],
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            tg_id = to_int(session_user.get("telegram_id"), 0)
            if await is_admin_user(tg_id):
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.admins_cannot_apply")
                    },
                )
            try:
                if not Config.PARTNER_ENABLED:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.partner_program_disabled",
                            )
                        },
                    )
                if bool(session_user.get("is_mate")):
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.already_a_partner")
                        },
                    )
                followers = to_int(req.get("followers", 0), 0)
                social_links = str(req.get("social_links", "")).strip()
                nickname = str(req.get("nickname", "")).strip()
                period_months = to_int(req.get("period_months", 0), 0)
                bonus_type = str(req.get("bonus_type", "")).strip()
                bonus_value = to_int(req.get("bonus_value", 0), 0)
                pd_consent = to_int(req.get("pd_consent", 0), 0)
                if not social_links or not nickname:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.social_links_and_nickname_required",
                            )
                        },
                    )
                if not re.match(r"^[a-zA-Z0-9_]+$", nickname):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.nickname_english_letters_digits",
                            )
                        },
                    )
                if (
                    period_months < Config.PARTNER_MIN_PERIOD_MONTHS
                    or period_months > Config.PARTNER_MAX_PERIOD_MONTHS
                ):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.partner_period_out_of_range",
                                min_months=Config.PARTNER_MIN_PERIOD_MONTHS,
                                max_months=Config.PARTNER_MAX_PERIOD_MONTHS,
                            )
                        },
                    )
                app_id = await db.add_partner_application(
                    tg_id,
                    followers,
                    social_links,
                    nickname,
                    period_months,
                    bonus_type,
                    bonus_value,
                    pd_consent,
                )
                if app_id:
                    return JSONResponse(
                        content={
                            "message": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.api_application_submitted",
                            ),
                            "app_id": app_id,
                        },
                        status_code=201,
                    )
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.failed_to_submit_application",
                        )
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_partner_apply: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.get("/api/v1/partner/pending-status")
        async def api_partner_pending_status(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            user_id = session_user["user_id"]
            try:
                ops = await get_pending_partner_operations()
                pending = any(
                    o.get("user_id") == user_id and o.get("op_type") == "partner_new" for o in ops
                )
                return JSONResponse(content={"has_pending_application": pending})
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_partner_pending_status: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        @self.app.post("/api/v1/partner/withdraw")
        async def api_partner_withdraw(
            req: dict[str, Any],
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            session_user = await db.get_user_by_session_token(credentials.credentials)
            if not session_user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            tg_id = to_int(session_user.get("telegram_id"), 0)
            try:
                if not bool(session_user.get("is_mate")):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.not_a_partner")
                        },
                    )
                amount = to_float(req.get("amount"), 0.0)
                fio = str(req.get("fio", "")).strip()
                phone = str(req.get("phone", "")).strip()
                bank = str(req.get("bank", "")).strip()
                if amount <= 0:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.amount_must_be_positive"
                            )
                        },
                    )
                if not fio:
                    return JSONResponse(
                        status_code=400,
                        content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.fio_required")},
                    )
                if not phone:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.phone_required")
                        },
                    )
                if not bank:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.bank_required")
                        },
                    )
                balance = to_float(session_user.get("mate_balance"), 0.0)
                if amount > balance:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.partner_insufficient_balance",
                            ),
                            "balance": balance,
                        },
                    )
                withdrawal_id = await db.add_partner_withdrawal_request(
                    tg_id, amount, fio=fio, phone=phone, bank=bank
                )
                if withdrawal_id:
                    payment_data = {
                        "payment_id": withdrawal_id,
                        "user_id": tg_id,
                        "plan_id": "partner_withdrawal",
                        "plan_type": "withdrawal",
                        "plan_name": f"Partner Withdrawal #{withdrawal_id[:12]}",
                        "amount": amount,
                        "currency": "RUB",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "pending",
                        "payment_method": "partner_balance",
                        "withdrawal_fio": fio,
                        "withdrawal_phone": phone,
                        "withdrawal_bank": bank,
                    }
                    await json_db.add_pending_for_user(tg_id, payment_data)
                    return JSONResponse(
                        content={
                            "message": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.withdrawal_request_submitted",
                            ),
                            "withdrawal_id": withdrawal_id,
                        },
                        status_code=201,
                    )
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(
                            Config.DEFAULT_LANGUAGE, "texts.failed_to_create_withdrawal"
                        )
                    },
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_partner_withdraw: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === WebSocket ---
        @self.app.websocket("/ws/notifications/{user_id}")
        async def ws_notifications(websocket: WebSocket, user_id: str) -> None:
            logger.info(f"WS connect: notifications user_id={user_id}")
            await websocket.accept()
            key = f"notif_{user_id}"
            if key not in _active_connections:
                _active_connections[key] = []
            _active_connections[key].append(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info(f"WS disconnect: notifications user_id={user_id}")
                _active_connections.get(key, []).remove(websocket)
                if key in _active_connections and not _active_connections[key]:
                    del _active_connections[key]

        @self.app.websocket("/ws/admin/{admin_key}")
        async def ws_admin(websocket: WebSocket, admin_key: str) -> None:
            auth_header = websocket.headers.get("authorization", "")
            header_key = (
                auth_header.replace(BEARER_PREFIX, "").strip()
                if auth_header.startswith("Bearer ")
                else auth_header.strip()
            )

            if _is_admin_token(header_key):
                logger.info("WS admin: авторизованное подключение (Authorization header)")
            elif _is_admin_token(admin_key):
                logger.warning(
                    "DEPRECATED: WS admin auth через path-параметр. "
                    "Передавайте admin_key в Authorization: Bearer <key>."
                )
            else:
                logger.warning("WS admin: неавторизованное подключение (неверный admin_key)")
                await websocket.close(code=4001)
                return
            await websocket.accept()
            _admin_connections.append(websocket)
            try:
                while True:
                    await websocket.receive_text()
            except WebSocketDisconnect:
                logger.info("WS admin: отключение")
                if websocket in _admin_connections:
                    _admin_connections.remove(websocket)

        # === Custom Tariff Generation API ---
        @self.app.post("/api/v1/tariffs/custom/generate")
        async def api_generate_custom_tariff(
            req: CustomTariffRequest,
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            token = credentials.credentials
            session_user = await db.get_user_by_session_token(token)
            if not session_user and not _is_admin_token(token):
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            try:
                if not custom_tariff_enabled():
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE, "texts.custom_tariffs_disabled"
                            )
                        },
                    )
                if not is_valid_custom_limits(req.traffic_gb, req.ip_limit, req.duration_days):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.invalid_custom_tariff_limits",
                            ),
                            "gb_bounds": list(custom_gb_bounds()),
                            "ip_bounds": list(custom_ip_bounds()),
                            "days_bounds": list(custom_days_bounds()),
                        },
                    )
                if req.servers and not is_valid_custom_servers(req.servers):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.invalid_server_locations",
                            )
                        },
                    )
                plan = build_custom_plan(
                    req.traffic_gb, req.ip_limit, req.duration_days, servers=req.servers
                )
                total_price = calculate_custom_tariff_total(
                    req.traffic_gb, req.ip_limit, req.duration_days, req.servers
                )
                return JSONResponse(
                    content={
                        "plan": plan,
                        "total_price": total_price,
                        "formatted_name": plan["name"],
                        "price_rub": plan["price_rub"],
                    },
                    status_code=200,
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_generate_custom_tariff: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Custom Tariff Params API ---
        @self.app.get("/api/v1/tariffs/custom/params")
        async def api_get_custom_tariff_params(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            token = credentials.credentials
            session_user = await db.get_user_by_session_token(token)
            if not session_user and not _is_admin_token(token):
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            try:
                min_gb, max_gb = custom_gb_bounds()
                min_ip, max_ip = custom_ip_bounds()
                min_days, max_days = custom_days_bounds()
                locations = get_custom_locations()
                return JSONResponse(
                    content={
                        "base_price": Config.CUSTOM_TARIFF_BASE_PRICE,
                        "gb_coef": Config.CUSTOM_TARIFF_GB_COEF,
                        "ip_day_coef": Config.CUSTOM_TARIFF_IP_DAY_COEF,
                        "min_gb": min_gb,
                        "max_gb": max_gb,
                        "min_ip": min_ip,
                        "max_ip": max_ip,
                        "min_days": min_days,
                        "max_days": max_days,
                        "locations": [
                            {
                                "code": loc.get("code", ""),
                                "name": loc.get("name", ""),
                                "flag": loc.get("flag", ""),
                                "label": loc.get("label", ""),
                                "price_per_day_rub": loc.get("price_per_day_rub", 0),
                            }
                            for loc in locations
                        ],
                    },
                    status_code=200,
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_get_custom_tariff_params: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Full User Info ---
        @self.app.get("/api/v1/admin/users/{user_id}/full-info")
        async def api_admin_user_full_info(
            user_id: int,
            include_payments: bool = Query(True),
            include_referrals: bool = Query(True),
            include_panel_data: bool = Query(True),
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin full-info: user_id={user_id}")
            try:
                user = await db.get_user_by_any_id(user_id)
                if not user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                result: dict[str, Any] = {"user": sanitize_user(user)}
                sub_state = await get_subscription_state(user_id)
                result["subscription_state"] = sub_state
                trust = await db.get_trust_score(user_id)
                result["trust_score"] = trust
                result["discount_percent"] = calculate_discount_percent(trust)
                if include_referrals:
                    db_uid = user.get("user_id", 0)
                    result["referrals"] = {
                        "total": await db.count_referrals(db_uid),
                        "paid": await db.count_referrals_paid(db_uid),
                        "ref_code": user.get("ref_code", ""),
                        "ref_by": user.get("ref_by"),
                    }
                if bool(user.get("is_mate")):
                    result["partner"] = {
                        "balance": to_float(user.get("mate_balance", 0), 0.0),
                        "commission_total": to_float(user.get("mate_commission_total", 0), 0.0),
                        "status": str(user.get("mate_status", "")),
                        "expiry": str(user.get("mate_expiry", "")),
                        "nickname": str(user.get("mate_nickname", "")),
                    }
                if include_payments:
                    all_payments = await json_db.read_all()
                    tg_id = to_int(user.get("telegram_id"), user_id)
                    user_payments = [
                        p for p in all_payments if to_int(p.get("user_id"), 0) == tg_id
                    ]
                    result["pending_payments"] = [
                        p for p in user_payments if p.get("status") == "pending"
                    ]
                    result["payment_history"] = [
                        p for p in user_payments if p.get("status") in ("accepted", "rejected")
                    ]
                if include_panel_data:
                    base_email = build_base_email(user.get("user_id", user_id))
                    panel_clients = await panel.find_clients_full_by_email(base_email)
                    result["panel_clients"] = panel_clients
                return JSONResponse(content=result)
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_user_full_info {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Payment History ---
        @self.app.get("/api/v1/admin/payments/history")
        async def api_admin_payment_history(
            page: int = Query(1, ge=1),
            limit: int = Query(50, ge=1, le=200),
            status: str | None = Query(None),
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                all_payments = await json_db.read_all()
                if status:
                    all_payments = [p for p in all_payments if p.get("status") == status]
                all_payments.sort(key=lambda p: p.get("timestamp", ""), reverse=True)
                total = len(all_payments)
                offset = (page - 1) * limit
                page_payments = all_payments[offset : offset + limit]
                return JSONResponse(
                    content={
                        "payments": page_payments,
                        "total": total,
                        "page": page,
                        "limit": limit,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_payment_history: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Payment Verification API ---
        @self.app.post("/api/v1/payments/verify/{payment_id}")
        async def api_verify_payment(
            payment_id: str,
            req: PaymentVerifyRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API verify_payment: payment_id={payment_id}, status={req.status}")
            try:
                if req.status not in ("confirmed", "rejected"):
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_status")
                        },
                    )
                action = "accept" if req.status == "confirmed" else "reject"
                payment = await json_db.claim_pending_payment(payment_id, 0, action)
                if not payment:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.payment_not_found_or_already_processed",
                            )
                        },
                    )
                await finalize_claimed_payment_or_alert(None, payment_id, action, req.status)
                if req.status == "confirmed":
                    resolved = await resolve_user_from_payment(payment)
                    if not resolved:
                        uid = to_int(payment.get("user_id"), 0)
                        logger.error(
                            f"api_verify_payment: пользователь не найден для платежа {payment_id}, uid={uid}"
                        )
                        return JSONResponse(
                            content={
                                "message": "payment_confirmed_but_user_not_found",
                                "payment_id": payment_id,
                            }
                        )
                    uid = resolved.telegram_id
                    user_data = resolved.user_data
                    plan_type = str(payment.get("plan_type", "catalog"))
                    plan_id = str(payment.get("plan_id", ""))
                    if plan_type == "custom":
                        plan, error = build_custom_plan_from_payment(payment)
                    else:
                        plan, error = get_purchasable_catalog_plan(plan_id)  # noqa: RUF059
                    if plan:
                        paid_amount = to_float(payment.get("amount"), 0.0)
                        ref_by = user_data.get("ref_by")
                        ref_rewarded = user_data.get("ref_rewarded")
                        bonus_for_user = Config.REF_BONUS_DAYS if ref_by and not ref_rewarded else 0
                        st = await get_subscription_state(uid)
                        if st.get("status") == "active":
                            vpn_url = await renew_subscription(
                                uid,
                                plan,
                                extra_days=bonus_for_user,
                                paid_amount=paid_amount,
                            )
                        else:
                            vpn_url = await create_subscription(
                                uid,
                                plan,
                                extra_days=bonus_for_user,
                                paid_amount=paid_amount,
                            )
                        if vpn_url:
                            await db.set_has_subscription(uid)
                            if ref_by and not ref_rewarded:
                                await reward_referrer(ref_by, Config.REF_BONUS_DAYS)
                                await db.mark_ref_rewarded(uid)
                            if ref_by:
                                referrer = await db.get_user_by_any_id(ref_by)
                                if referrer and referrer.get("is_mate"):
                                    commission = round(
                                        paid_amount * Config.PARTNER_COMMISSION_PERCENT / 100,
                                        2,
                                    )
                                    if commission > 0:
                                        await db.update_partner_balance(ref_by, commission)
                            user_lang = await get_user_language(uid)
                            plan_name = str(payment.get("plan_name", ""))
                            duration_days = int(plan.get("duration_days", 30)) if plan else 30
                            text = translate(
                                user_lang,
                                "texts.subscription_purchased_notification",
                                plan_name=plan_name,
                                duration=format_duration(duration_days, user_lang),
                            )
                            await notify_user(uid, text)
                        logger.info(f"✅ Payment {payment_id} confirmed, subscription created")
                else:
                    resolved = await resolve_user_from_payment(payment)
                    if resolved:
                        await apply_trust_score_delta(
                            resolved.telegram_id, -TRUST_SCORE_PENALTY_PAYMENT_REJECTED
                        )
                    else:
                        raw_uid = to_int(payment.get("user_id"), 0)
                        uid = await resolve_tg_id(raw_uid) if raw_uid > 0 else 0
                        if uid > 0:
                            await apply_trust_score_delta(
                                uid, -TRUST_SCORE_PENALTY_PAYMENT_REJECTED
                            )
                    logger.info(f"⚠️ Payment {payment_id} rejected, trust penalty applied")
                return JSONResponse(
                    content={
                        "message": f"Payment {req.status}",
                        "payment_id": payment_id,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_verify_payment {payment_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Partner Stats API ---
        @self.app.get("/api/v1/partner/stats")
        async def api_partner_stats(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            user_id = user["user_id"]
            if not bool(user.get("is_mate")):
                return JSONResponse(
                    status_code=403,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.not_a_partner")},
                )
            try:
                total_refs = await db.count_partner_referrals(user_id)
                paid_refs = await db.count_partner_referrals_paid(user_id)
                balance = to_float(user.get("mate_balance", 0), 0.0)
                commission_total = to_float(user.get("mate_commission_total", 0), 0.0)
                return JSONResponse(
                    content={
                        "total_refs": total_refs,
                        "paid_refs": paid_refs,
                        "unpaid_refs": total_refs - paid_refs,
                        "balance": balance,
                        "commission_total": commission_total,
                        "conversion_rate": round(
                            (paid_refs / total_refs * 100) if total_refs > 0 else 0, 2
                        ),
                        "avg_commission_per_paid": round(
                            balance / paid_refs if paid_refs > 0 else 0, 2
                        ),
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_partner_stats: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Referral Stats API ---
        @self.app.get("/api/v1/referrals/stats")
        async def api_referral_stats(
            credentials: HTTPAuthorizationCredentials | None = Depends(security),  # noqa: B008
        ) -> JSONResponse:
            if not credentials:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.unauthorized")},
                )
            user = await db.get_user_by_session_token(credentials.credentials)
            if not user:
                return JSONResponse(
                    status_code=401,
                    content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.invalid_session")},
                )
            user_id = user["user_id"]
            try:
                total_refs = await db.count_referrals(user_id)
                paid_refs = await db.count_referrals_paid(user_id)
                ref_code = user.get("ref_code", "")
                if not ref_code:
                    tg_id_for_ref = to_int(user.get("telegram_id"), 0)
                    ref_code = (
                        await db.ensure_ref_code(tg_id_for_ref) or "" if tg_id_for_ref else ""
                    )
                ref_link = get_ref_link(ref_code) if ref_code else ""
                return JSONResponse(
                    content={
                        "ref_code": ref_code,
                        "ref_link": ref_link,
                        "total_refs": total_refs,
                        "paid_refs": paid_refs,
                        "unpaid_refs": total_refs - paid_refs,
                        "conversion_rate": round(
                            (paid_refs / total_refs * 100) if total_refs > 0 else 0, 2
                        ),
                        "bonus_days_per_paid": Config.REF_BONUS_DAYS,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_referral_stats: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Bulk User Actions ---
        @self.app.post("/api/v1/admin/users/bulk-action")
        async def api_admin_bulk_action(
            req: BulkActionRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin bulk-action: action={req.action}, count={len(req.user_ids)}")
            try:
                result = {
                    "processed": 0,
                    "errors": 0,
                    "skipped_admins": 0,
                    "results": [],
                }
                for uid in req.user_ids:
                    try:
                        user = await db.get_user_by_any_id(uid)
                        if user:
                            tg_id = user.get("telegram_id", 0)
                            if tg_id and await is_admin_user(tg_id):
                                result["results"].append(
                                    {
                                        "user_id": uid,
                                        "error": "Cannot modify admin user",
                                    }
                                )
                                result["skipped_admins"] += 1
                                continue
                        if req.action == "ban":
                            internal_uid = user.get("user_id", uid) if user else uid
                            tg_id = user.get("telegram_id", uid) if user else uid
                            success = await db.ban_user_by_uid(
                                internal_uid, reason=req.reason or "bulk_ban"
                            )
                            if success:
                                await cleanup_subscription(
                                    internal_uid,
                                    "bulk_ban",
                                    notify_user_about_cleanup=False,
                                )
                        elif req.action == "unban":
                            internal_uid = user.get("user_id", uid) if user else uid
                            success = await db.unban_user_by_uid(internal_uid)
                        elif req.action == "remove_subscription":
                            internal_uid = user.get("user_id", uid) if user else uid
                            await db.remove_subscription(internal_uid)
                        elif req.action == "reset_trial":
                            tg_id = user.get("telegram_id", uid) if user else uid
                            await db.mark_trial_used(tg_id)
                        else:
                            result["results"].append(
                                {
                                    "user_id": uid,
                                    "error": translate(
                                        Config.DEFAULT_LANGUAGE, "texts.unknown_action"
                                    ),
                                }
                            )
                            result["errors"] += 1
                            continue
                        result["processed"] += 1
                    except Exception as e:  # noqa: BLE001
                        result["errors"] += 1
                        result["results"].append({"user_id": uid, "error": str(e)})
                return JSONResponse(content=result)
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_bulk_action: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Debug Cleanup ---
        @self.app.post("/api/v1/admin/debug/cleanup")
        async def api_admin_debug_cleanup(
            req: DebugCleanupRequest,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.info(f"API admin debug cleanup: dry_run={req.dry_run}")
            try:
                if req.dry_run:
                    subscribed = await db.get_subscribed_user_ids()
                    expired_count = 0
                    traffic_exhausted_count = 0
                    missing_count = 0
                    for uid in subscribed:
                        if await is_admin_user(uid):
                            continue
                        try:
                            state = await get_subscription_state(uid)
                            if state.get("status") == "expired" and req.cleanup_expired:
                                expired_count += 1
                            elif (
                                state.get("status") == "traffic_exhausted"
                                and req.cleanup_traffic_exhausted
                            ):
                                traffic_exhausted_count += 1
                            elif state.get("status") == "missing_on_panel" and req.cleanup_missing:
                                missing_count += 1
                        except Exception:  # noqa: BLE001, S110
                            pass
                    return JSONResponse(
                        content={
                            "dry_run": True,
                            "would_clean": {
                                "expired": expired_count,
                                "traffic_exhausted": traffic_exhausted_count,
                                "missing_on_panel": missing_count,
                                "total": expired_count + traffic_exhausted_count + missing_count,
                            },
                            "total_subscribed": len(subscribed),
                        }
                    )
                else:
                    report = await normalize_all_subscriptions_with_retry(max_iterations=2)
                    return JSONResponse(
                        content={
                            "dry_run": False,
                            "report": report,
                        }
                    )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_debug_cleanup: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Debug Search ---
        @self.app.get("/api/v1/admin/debug/search")
        async def api_admin_debug_search(
            q: str = Query("", min_length=1),
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                users = await db.search_users(q)
                return JSONResponse(
                    content={
                        "query": q,
                        "count": len(users),
                        "users": [sanitize_user(u) for u in users],
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_debug_search: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: System Health ---
        @self.app.get("/api/v1/admin/health")
        async def api_admin_health(
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                total_users = await db.get_total_users()
                banned_users = await db.get_banned_users_count()
                active_subs = len(await db.get_subscribed_user_ids())
                mate_count = len(await db.get_mate_user_ids())
                pending_payments = await json_db.read_all()
                pending_count = len([p for p in pending_payments if p.get("status") == "pending"])
                processing_count = len(
                    [p for p in pending_payments if p.get("status") == "processing"]
                )
                all_partner_ops = await get_pending_partner_operations()
                partner_pending = len(all_partner_ops)
                return JSONResponse(
                    content={
                        "status": "ok",
                        "users": {
                            "total": total_users,
                            "banned": banned_users,
                            "active_subscriptions": active_subs,
                            "partners": mate_count,
                        },
                        "payments": {
                            "pending": pending_count,
                            "processing": processing_count,
                            "total_stored": len(pending_payments),
                        },
                        "partner_operations": {
                            "pending": partner_pending,
                        },
                        "tech_work_mode": tech_work_service.is_enabled(),
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_health: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Reset User State ---
        @self.app.post("/api/v1/admin/users/{user_id}/reset")
        async def api_admin_reset_user(
            user_id: int,
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            logger.warning(f"API admin reset user: user_id={user_id}")
            try:
                target_user = await db.get_user_by_any_id(user_id)
                if target_user:
                    tg_id = target_user.get("telegram_id", 0)
                    if tg_id and await is_admin_user(tg_id):
                        return JSONResponse(
                            status_code=403,
                            content={
                                "error": translate(
                                    Config.DEFAULT_LANGUAGE,
                                    "texts.cannot_reset_admin_user",
                                )
                            },
                        )
                await cleanup_subscription(user_id, "admin_reset", notify_user_about_cleanup=True)
                return JSONResponse(
                    content={
                        "message": translate(
                            Config.DEFAULT_LANGUAGE,
                            "texts.api_user_state_reset",
                            user_id=user_id,
                        ),
                        "success": True,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_reset_user {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Send Message to User ---
        @self.app.post("/api/v1/admin/users/{user_id}/message")
        async def api_admin_send_message(
            user_id: int,
            message: dict[str, str],
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                target_user = await db.get_user_by_any_id(user_id)
                if not target_user:
                    return JSONResponse(
                        status_code=404,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.user_not_found")
                        },
                    )
                tg_id = target_user.get("telegram_id", 0)
                if tg_id and await is_admin_user(tg_id):
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error": translate(
                                Config.DEFAULT_LANGUAGE,
                                "texts.cannot_message_admin_user",
                            )
                        },
                    )
                text = str(message.get("text", "")).strip()
                if not text:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": translate(Config.DEFAULT_LANGUAGE, "texts.empty_message")
                        },
                    )
                sent = await safe_send_message(bot, tg_id, text)
                return JSONResponse(
                    content={
                        "message": translate(Config.DEFAULT_LANGUAGE, "texts.api_message_sent")
                        if sent
                        else translate(Config.DEFAULT_LANGUAGE, "texts.api_message_failed"),
                        "sent": sent,
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_send_message {user_id}: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Admin: Export User Data ---
        @self.app.get("/api/v1/admin/users/export")
        async def api_admin_export_users(
            format: str = Query("json", pattern="^(json|csv)$"),
            admin: str = Depends(_require_admin),
        ) -> JSONResponse:
            try:
                all_users = await db.get_all_users()
                if format == "csv":
                    if not all_users:
                        return JSONResponse(content={"data": ""})
                    headers = list(all_users[0].keys())
                    csv_lines = [",".join(headers)]
                    for user in all_users:
                        row = []
                        for h in headers:
                            val = str(user.get(h, "")).replace(",", ";")
                            row.append(val)
                        csv_lines.append(",".join(row))
                    csv_data = "\n".join(csv_lines)
                    return JSONResponse(
                        content={
                            "data": csv_data,
                            "format": "csv",
                            "count": len(all_users),
                        }
                    )
                else:
                    sanitized = [sanitize_user(u) for u in all_users]
                    return JSONResponse(
                        content={
                            "data": sanitized,
                            "format": "json",
                            "count": len(sanitized),
                        }
                    )
            except Exception as e:  # noqa: BLE001
                logger.error(f"api_admin_export_users: {e}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                    },
                )

        # === Error handling for unknown endpoints ---
        @self.app.exception_handler(HTTPException)
        async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
            logger.warning(f"HTTP exception: {exc.status_code} - {exc.detail}")
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": translate(Config.DEFAULT_LANGUAGE, "texts.bad_request")},
            )

        @self.app.exception_handler(Exception)
        async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
            logger.error(f"Uncaught exception: {exc}")
            return JSONResponse(
                status_code=500,
                content={
                    "error": translate(Config.DEFAULT_LANGUAGE, "texts.internal_server_error")
                },
            )


# --- Запуск ---
async def main() -> None:
    background_tasks: list[asyncio.Task] = []
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    async def stop_polling_safely() -> None:
        try:
            await dp.stop_polling()
        except RuntimeError:
            pass
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Ошибка остановки polling: {type(e).__name__}: {e}")

    def signal_handler(sig: int, frame: Any) -> None:
        logger.info(f"Получен сигнал {sig}. Запуск graceful shutdown...")
        shutdown_event.set()
        for task in background_tasks:
            if not task.done():
                task.cancel()
        loop.create_task(stop_polling_safely())

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, signal_handler)
        except (AttributeError, ValueError):
            pass

    try:
        Config.validate()
        logger.info("Конфигурация валидна")
    except ConfigError as e:
        logger.critical(f"Ошибка конфигурации:\n{e}")
        sys.exit(1)

    feature_errors = Features.validate()
    if feature_errors:
        error_msg = "Ошибка конфигурации функций:\n" + "\n".join(f"  • {e}" for e in feature_errors)
        logger.critical(error_msg)
        try:
            bot_temp = Bot(
                token=Config.BOT_TOKEN,
                default=DefaultBotProperties(parse_mode=ParseMode.HTML),
            )
            for admin_id in Config.ADMIN_USER_IDS:
                try:
                    await safe_send_message(bot_temp, admin_id, error_msg)
                except Exception:  # noqa: BLE001, S110
                    pass
            await bot_temp.session.close()
        except Exception:  # noqa: BLE001, S110
            pass
        return
    logger.info("Функции валидированы")

    try:
        load_tariffs()
        logger.info("Тарифы загружены успешно")
    except Exception as e:  # noqa: BLE001
        logger.critical(f"Не удалось загрузить тарифы: {type(e).__name__}: {e}")
        return

    if not is_valid_bot_token_format(Config.BOT_TOKEN):
        logger.critical("BOT_TOKEN не настроен или некорректен")
        return

    logger.info("Формат BOT_TOKEN корректен")

    try:
        await db.connect()
        logger.info("База данных подключена")

        try:
            await _ensure_partner_ops_file()
            logger.info("partner_operations.json инициализирована")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Не удалось инициализировать partner_operations.json: {e}")

        try:
            await panel.start()
            logger.info("PanelAPI запущен")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"PanelAPI не удалось запустить: {e}")

        try:
            me = await bot.get_me()
            set_bot_username(me.username or "")
            logger.info(f"Бот авторизован как @{BOT_USERNAME}")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Не удалось получить информацию о боте: {e}")
            set_bot_username("")

        try:
            await ensure_startup_admin_accounts()
            logger.info("Админ-аккаунты и подписки проверены при запуске")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Не удалось проверить админ-аккаунты при запуске: {e}")

        for admin_id in Config.ADMIN_USER_IDS:
            try:
                await safe_send_message(
                    bot,
                    admin_id,
                    translate(Config.DEFAULT_LANGUAGE, "texts.bot_started"),
                )
                logger.info(f"Уведомление администратора {admin_id} отправлено")
            except Exception:  # noqa: BLE001, S110
                pass

        # --- FastAPI сервер ---
        bot_api = BOT_FastAPI()

        async def run_api() -> None:
            try:
                import uvicorn

                await uvicorn.Server(
                    uvicorn.Config(
                        bot_api.app,
                        host=Config.FASTAPI_HOST,
                        port=Config.FASTAPI_PORT,
                        log_level="info",
                    )
                ).serve()
            except (asyncio.CancelledError, SystemExit, KeyboardInterrupt):
                pass
            except Exception as e:  # noqa: BLE001
                logger.warning(f"Ошибка FastAPI сервера: {e}")

        try:
            # Приоритет: API, подписки, безопасность, платежи, партнёры, SSL.
            background_tasks.append(asyncio.create_task(run_api()))
            logger.info(f"FastAPI сервер запущен на {Config.FASTAPI_HOST}:{Config.FASTAPI_PORT}")
            background_tasks.append(asyncio.create_task(check_expired_subscriptions()))
            background_tasks.append(asyncio.create_task(check_traffic_abuse()))
            background_tasks.append(asyncio.create_task(cleanup_old_payments()))
            background_tasks.append(asyncio.create_task(check_partner_expiry_notifications()))
            background_tasks.append(asyncio.create_task(SSLUpdateTask.run()))
            logger.info("Фоновые задачи запущены")
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Не удалось запустить часть фоновых задач: {e}")

        logger.info("Запуск polling...")
        await dp.start_polling(bot)
        logger.info("Polling завершен")

    except ConfigError as e:
        logger.critical(f"Ошибка конфигурации: {e}")
        sys.exit(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Остановка бота")
    except Exception as e:
        logger.critical(f"Неожиданная ошибка: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)
    finally:
        logger.info("🛑 Запуск graceful shutdown...")

        if tech_work_service.is_enabled():
            logger.info("Выключение режима тех. работ при shutdown")
            await tech_work_service.set_enabled(False)

        logger.info("Остановка фоновых задач...")
        for task in background_tasks:
            if not task.done():
                task.cancel()
        if background_tasks:
            try:
                await asyncio.gather(*background_tasks, return_exceptions=True)
            except asyncio.CancelledError:
                pass

        try:
            for admin_id in Config.ADMIN_USER_IDS:
                try:
                    await safe_send_message(
                        bot,
                        admin_id,
                        translate(Config.DEFAULT_LANGUAGE, "texts.bot_stopped"),
                    )
                except Exception:  # noqa: BLE001, S110
                    pass
        except Exception:  # noqa: BLE001, S110
            pass

        await cleanup_stale_payments()

        await panel.close()
        await db.close()
        if bot.session:
            await bot.session.close()

        logger.info("✅ Бот остановлен")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Принудительная остановка")
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {e}", exc_info=True)
        sys.exit(1)
