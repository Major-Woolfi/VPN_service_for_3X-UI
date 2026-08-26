import asyncio
import html
import json
import logging
import os
import paramiko  # type: ignore[import-untyped]
import re
import secrets
import signal
import string
import sys
import time
import uuid
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
    Set,
    Callable,
    TypeVar,
)
from urllib.parse import quote, urlencode

import aiofiles  # type: ignore[import-untyped]
import aiohttp
import aiosqlite
from aiogram import Bot, Dispatcher, Router, F
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

# === Настройка окружения ===
BASE_DIR: Path = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# === Настройка логирования ===
LOGS_DIR: Path = BASE_DIR / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FILE: Path = LOGS_DIR / f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"

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
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
logger.info("=== Логгер инициализирован ===")

# === Константы ===
LANGS_DIR: Path = Path(os.getenv("LANGS_DIR", str(BASE_DIR / "langs"))).expanduser()
if not LANGS_DIR.is_absolute():
    LANGS_DIR = BASE_DIR / LANGS_DIR
DEFAULT_LANGUAGE: str = "ru"

# === Типы для строгой типизации ===
T = TypeVar("T")
JSONValue = Union[
    str, int, float, bool, None, List["JsonValue"], Dict[str, "JsonValue"]
]
JsonValue = Dict[str, JSONValue]


# === Кастомные исключения ===
class BotError(Exception):

    def __init__(self, message: str, code: int = 500):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ConfigError(BotError):
    def __init__(self, message: str):
        super().__init__(message, code=400)


class DatabaseError(BotError):
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.original_error = original_error
        super().__init__(message, code=500)


class PanelError(BotError):
    def __init__(self, message: str, status_code: Optional[int] = None):
        self.status_code = status_code
        super().__init__(message, code=status_code or 500)


class ValidationError(BotError):
    def __init__(self, message: str, field: Optional[str] = None):
        self.field = field
        super().__init__(message, code=400)


# === Утилиты логирования ===
def log_error(func: Callable) -> Callable:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Ошибка в {func.__name__}: {e}", exc_info=True)
            raise

    return wrapper


def log_warning(func: Callable) -> Callable:
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            logger.warning(f"Предупреждение в {func.__name__}: {e}")
            raise

    return wrapper


# === Утилиты для работы с событиями ===
async def safe_send_message(
    bot: Bot,
    user_id: int,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
) -> bool:
    if not bot.session:
        logger.error(
            f"safe_send_message: сессия бота не инициализирована для user {user_id}"
        )
        return False
    try:
        await bot.send_message(
            user_id, text, parse_mode=ParseMode.HTML, reply_markup=reply_markup
        )
        return True
    except TelegramBadRequest as e:
        error_msg = str(e).lower()
        if "blocked" in error_msg or "bot was blocked" in error_msg:
            return False
        try:
            await bot.send_message(
                user_id,
                html.escape(text),
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup,
            )
            return True
        except Exception:
            try:
                await bot.send_message(user_id, text, reply_markup=reply_markup)
                return True
            except Exception as e2:
                logger.error(f"Ошибка отправки сообщения {user_id}: {e2}")
                return False
    except Exception as e:
        logger.error(f"Ошибка отправки {user_id}: {e}")
        return False


async def smart_answer(
    event: Union[Message, CallbackQuery],
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
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
                    except Exception:
                        pass
            try:
                await event.answer()
            except Exception:
                pass
        return True
    except Exception as e:
        logger.error(f"smart_answer error: {e}")
        return False


# === Retry декоратор для самоисправления ===
async def retry_async(
    func: Callable,
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: Tuple[type, ...] = (Exception,),
) -> Any:
    if max_retries <= 0:
        raise BotError("max_retries должен быть больше 0")

    last_exception: Optional[Exception] = None

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
                logger.error(
                    f"Все {max_retries} попытки исчерпаны: {type(e).__name__}: {e}",
                    exc_info=True,
                )

    if last_exception:
        raise last_exception

    raise BotError("Неизвестная ошибка в retry_async")


# === Валидация данных ===
def validate_email(email: str) -> bool:
    if not email or not isinstance(email, str):
        return False
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_user_id(user_id: Any) -> bool:
    return isinstance(user_id, int) and user_id > 0


def validate_positive_number(value: Any, field_name: str = "value") -> float:
    try:
        num = float(value)
        if num < 0:
            raise ValidationError(f"{field_name} должен быть положительным", field_name)
        return num
    except (ValueError, TypeError) as e:
        raise ValidationError(
            f"Некорректное значение {field_name}: {value}", field_name
        ) from e


def validate_non_empty_string(value: Any, field_name: str = "value") -> str:
    text = str(value or "").strip()
    if not text:
        raise ValidationError(f"{field_name} не может быть пустым", field_name)
    return text


def validate_required_config() -> None:
    errors: List[str] = []

    if not Config.BOT_TOKEN:
        errors.append("BOT_TOKEN не установлен")

    if not Config.PANEL_BASE:
        errors.append("PANEL_BASE не установлен")

    if not (Config.PANEL_TOKEN or (Config.PANEL_LOGIN and Config.PANEL_PASSWORD)):
        errors.append(
            "Не настроена авторизация в панели (PANEL_TOKEN или PANEL_LOGIN+PANEL_PASSWORD)"
        )

    if errors:
        error_msg = "Ошибка конфигурации:\n" + "\n".join(f"  • {e}" for e in errors)
        logger.critical(error_msg)
        raise ConfigError(error_msg)


# === In-memory cache for expiry alerts ===
_expiry_alert_cache: Dict[int, float] = {}
_EXPIRY_ALERT_CACHE_MAX_SIZE: int = 10000
_EXPIRY_ALERT_CACHE_TTL: int = 86400  # 24 часа


async def should_send_expiry_alert(user_id: int) -> bool:
    if not validate_user_id(user_id):
        logger.warning(f"Некорректный user_id для проверки уведомления: {user_id}")
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


def env_int(name: str, default: int) -> int:
    try:
        return int(str(os.getenv(name, default)).strip())
    except Exception:
        return default


def env_float(name: str, default: float) -> float:
    try:
        return float(str(os.getenv(name, default)).strip())
    except Exception:
        return default


def env_int_list(name: str) -> List[int]:
    values = []
    for raw in os.getenv(name, "").split(","):
        item = raw.strip()
        if item:
            try:
                values.append(int(item))
            except Exception:
                logger.warning(f"Некорректное значение в {name}: {item}")
    return values


def resolve_local_path(value: Any, default: str = "") -> str:
    raw = str(value if value not in (None, "") else default).strip()
    if not raw:
        return ""
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = BASE_DIR / path
    return str(path)


class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
    ADMIN_USER_IDS: List[int] = env_int_list("ADMIN_USER_IDS")
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
    DATA_DIR: str = resolve_local_path(os.getenv("DATA_DIR"), "data")
    DATA_FILE: str = resolve_local_path(
        os.getenv("DATA_FILE"), os.path.join(DATA_DIR, "users.db")
    )
    DATA_AWAIT: str = resolve_local_path(
        os.getenv("DATA_AWAIT"), os.path.join(DATA_DIR, "await_payments.json")
    )
    TARIFFS_PATH: str = resolve_local_path(
        os.getenv("TARIFFS_PATH"), os.path.join(DATA_DIR, "tarifs.json")
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
    REF_BONUS_DAYS: int = env_int("REF_BONUS_DAYS", 7)
    TRUST_SCORE_MIN: int = env_int("TRUST_SCORE_MIN", 0)
    TRUST_SCORE_MAX: int = env_int("TRUST_SCORE_MAX", 100)
    TRUST_SCORE_EARN_PERCENT: int = env_int("TRUST_SCORE_EARN_PERCENT", 5)
    TRUST_SCORE_MAX_DISCOUNT_PERCENT: int = env_int(
        "TRUST_SCORE_MAX_DISCOUNT_PERCENT", 50
    )
    TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED: int = env_int(
        "TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED", 5
    )
    TRUST_SCORE_PENALTY_PAYMENT_REJECTED: int = env_int(
        "TRUST_SCORE_PENALTY_PAYMENT_REJECTED", 10
    )
    CUSTOM_TARIFF_ENABLED: bool = str_to_bool(
        os.getenv("CUSTOM_TARIFF_ENABLED", "false")
    )
    CUSTOM_TARIFF_MIN_IP: int = env_int("CUSTOM_TARIFF_MIN_IP", 1)
    CUSTOM_TARIFF_MAX_IP: int = env_int("CUSTOM_TARIFF_MAX_IP", 30)
    CUSTOM_TARIFF_MIN_GB: int = env_int("CUSTOM_TARIFF_MIN_GB", 1)
    CUSTOM_TARIFF_MAX_GB: int = env_int("CUSTOM_TARIFF_MAX_GB", 36500)
    CUSTOM_TARIFF_MIN_DAYS: int = env_int("CUSTOM_TARIFF_MIN_DAYS", 1)
    CUSTOM_TARIFF_MAX_DAYS: int = env_int("CUSTOM_TARIFF_MAX_DAYS", 365)
    CUSTOM_TARIFF_BASE_PRICE: float = env_float("CUSTOM_TARIFF_BASE_PRICE", 20.0)
    CUSTOM_TARIFF_GB_COEF: float = env_float("CUSTOM_TARIFF_GB_COEF", 0.2)
    CUSTOM_TARIFF_IP_DAY_COEF: float = env_float("CUSTOM_TARIFF_IP_DAY_COEF", 1.5)
    CUSTOM_TARIFF_LOCATION_DAY_PRICE: float = env_float(
        "CUSTOM_TARIFF_LOCATION_DAY_PRICE", 2.0
    )
    EXPIRY_ALERT_DAYS: int = env_int("EXPIRY_ALERT_DAYS", 7)

    @classmethod
    def validate(cls) -> None:
        errors: List[str] = []

        if not cls.BOT_TOKEN:
            errors.append("BOT_TOKEN не установлен")

        if not cls.PANEL_BASE:
            errors.append("PANEL_BASE не установлен")

        if not (cls.PANEL_TOKEN or (cls.PANEL_LOGIN and cls.PANEL_PASSWORD)):
            errors.append(
                "Не настроена авторизация в панели "
                "(PANEL_TOKEN или PANEL_LOGIN+PANEL_PASSWORD)"
            )

        if not cls.ADMIN_USER_IDS:
            logger.warning(
                "ADMIN_USER_IDS не настроен - админ-функции будут недоступны"
            )

        if errors:
            error_msg = "Ошибка конфигурации:\n" + "\n".join(f"  • {e}" for e in errors)
            logger.critical(error_msg)
            raise ConfigError(error_msg)


try:
    os.makedirs(Config.DATA_DIR, exist_ok=True)
except Exception as e:
    logger.warning(f"Не удалось создать DATA_DIR: {e}")

ADMIN_USER_ID_SET = set(Config.ADMIN_USER_IDS)
BYTES_IN_GB = 1073741824
PAYMENT_PROCESSING_TIMEOUT_SEC = Config.PAYMENT_PROCESSING_TIMEOUT_SEC

# === Rate limiting ===
_RATE_LIMIT_COOLDOWN: float = env_float("RATE_LIMIT_COOLDOWN", 0.3)
_user_request_times: Dict[int, float] = {}

# === Tech work mode ===
_is_tech_work_mode: bool = False
_tech_work_mode_lock: asyncio.Lock = asyncio.Lock()


def is_tech_work_mode() -> bool:
    return _is_tech_work_mode


async def set_tech_work_mode(enabled: bool) -> bool:
    global _is_tech_work_mode
    async with _tech_work_mode_lock:
        _is_tech_work_mode = enabled
        logger.info(f"Тех. работы {'ВКЛЮЧЕНЫ' if enabled else 'ВЫКЛЮЧЕНЫ'}")
        return enabled


async def disconnect_all_subscriptions(reason: str) -> Dict[str, int]:
    result = {"total": 0, "success": 0, "failed": 0}
    try:
        user_ids = await db.get_subscribed_user_ids()
        result["total"] = len(user_ids)

        for user_id in user_ids:
            try:
                user = await db.get_user(user_id)
                sub_id = normalize_sub_id(user.get("vpn_url")) if user else ""
                if sub_id:
                    if await panel.disconnect_subscription(sub_id):
                        result["success"] += 1
                        logger.info(f"Подписка отключена для user {user_id}: {reason}")
                    else:
                        result["failed"] += 1
                else:
                    result["failed"] += 1
            except Exception as e:
                result["failed"] += 1
                logger.error(f"Ошибка отключения для user {user_id}: {e}")
    except Exception as e:
        logger.error(f"Ошибка при отключении всех подписок: {e}")

    return result


async def notify_all_users(message: str) -> Dict[str, int]:
    result = {"sent": 0, "failed": 0, "no_subscription": 0}

    try:
        user_ids = await db.get_subscribed_user_ids()

        for user_id in user_ids:
            user = await db.get_user(user_id)
            if user and normalize_sub_id(user.get("vpn_url")):
                try:
                    if await safe_send_message(bot, user_id, message):
                        result["sent"] += 1
                    else:
                        result["failed"] += 1
                    logger.info(f"Уведомление отправлено user {user_id}")
                except Exception as e:
                    result["failed"] += 1
                    logger.error(f"Ошибка отправки уведомления user {user_id}: {e}")
            else:
                result["no_subscription"] += 1
    except Exception as e:
        logger.error(f"Ошибка при отправке уведомлений: {e}")

    return result


async def compensate_all_users(days: int) -> Dict[str, int]:
    result = {"processed": 0, "errors": 0}

    if days <= 0:
        logger.warning(f"Компенсация: некорректное число дней ({days})")
        return result

    try:
        user_ids = await db.get_subscribed_user_ids()
        logger.info(f"Компенсация {days} дней для {len(user_ids)} пользователей")

        for user_id in user_ids:
            try:
                base_email = build_base_email(user_id)
                extended = await panel.extend_client_expiry(base_email, days)

                if extended:
                    result["processed"] += 1
                    logger.info(f"✓ Компенсация {days} дней для user {user_id}")
                else:
                    result["errors"] += 1
                    logger.warning(
                        f"✗ Не удалось продлить user {user_id} (клиент не найден на панели)"
                    )
            except Exception as e:
                result["errors"] += 1
                logger.error(
                    f"✗ Ошибка компенсации для user {user_id}: {type(e).__name__}: {e}"
                )
    except Exception as e:
        logger.error(f"Ошибка при компенсации: {type(e).__name__}: {e}", exc_info=True)

    logger.info(f"Компенсация завершена: {result}")
    return result


# === Языки и перевод ===
def load_languages() -> Dict[str, Dict[str, Any]]:
    languages: Dict[str, Dict[str, Any]] = {}
    if not LANGS_DIR.exists():
        logger.warning(f"Папка языков не найдена: {LANGS_DIR}")
        return languages
    for path in sorted(LANGS_DIR.glob("*.json")):
        try:
            raw = path.read_bytes()
            if raw[:3] == b"\xef\xbb\xbf":
                raw = raw[3:]
            data = json.loads(raw.decode("utf-8"))
            code = (
                str(data.get("meta", {}).get("code", path.stem)).strip().lower()
                or path.stem
            )
            languages[code] = data
        except Exception as e:
            logger.warning(f"Ошибка загрузки {path.stem}: {e}")
    if not languages:
        logger.warning("Не удалось загрузить ни одного языка")
    return languages


LANGUAGES = load_languages()


def get_available_languages() -> List[str]:
    return list(LANGUAGES.keys())


def get_language_display_name(code: str) -> str:
    data = LANGUAGES.get(code, {})
    return str(data.get("meta", {}).get("name", code)).strip() or code


def _resolve_key(data: Dict[str, Any], key: str) -> Optional[Any]:
    node = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


# === Кэширование языков ===
_LANG_CACHE: Dict[str, Dict[str, Any]] = {}
_LANG_CACHE_MAX_SIZE: int = 100


def translate(language_code: str, key: str, **kwargs: Any) -> str:
    lang = (language_code or DEFAULT_LANGUAGE).strip().lower()

    if lang not in _LANG_CACHE:
        if len(_LANG_CACHE) >= _LANG_CACHE_MAX_SIZE:
            first_key = next(iter(_LANG_CACHE), None)
            if first_key and first_key != DEFAULT_LANGUAGE:
                del _LANG_CACHE[first_key]
        try:
            path = LANGS_DIR / f"{lang}.json"
            if path.exists():
                raw = path.read_bytes()
                if raw[:3] == b"\xef\xbb\xbf":
                    raw = raw[3:]
                _LANG_CACHE[lang] = json.loads(raw.decode("utf-8"))
            else:
                _LANG_CACHE[lang] = {}
        except Exception as e:
            _LANG_CACHE[lang] = {}

    data = _LANG_CACHE.get(lang) or LANGUAGES.get(DEFAULT_LANGUAGE, {})
    text = _resolve_key(data, key)
    if text is None and lang != DEFAULT_LANGUAGE:
        data = LANGUAGES.get(DEFAULT_LANGUAGE, {})
        text = _resolve_key(data, key)
    if text is None:
        return key
    if kwargs and isinstance(text, str):
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return str(text)


# === Утилиты ===
def to_int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def flag_to_country_code(value: Any) -> str:
    text = str(value or "").strip()
    regional = [ch for ch in text if 0x1F1E6 <= ord(ch) <= 0x1F1E6 + 25]
    if len(regional) < 2:
        return ""
    return "".join(chr(ord(ch) - 0x1F1E6 + ord("A")) for ch in regional[:2])


def country_code_to_flag(value: Any) -> str:
    code = str(value or "").strip().upper()
    if len(code) != 2 or not code.isalpha() or not code.isascii():
        return ""
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code)


def normalize_server_code(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    flag = flag_to_country_code(text)
    if flag:
        return flag
    return text.upper() if text.isascii() else text


def normalize_servers(value: Any) -> List[str]:
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
    except Exception:
        return default


def format_traffic(traffic_gb: Any, lang: str = DEFAULT_LANGUAGE) -> str:
    try:
        v = float(traffic_gb)
    except Exception:
        return str(traffic_gb)
    if v >= 1024 and v % 1024 == 0:
        return translate(lang, "texts.traffic_tb", value=int(v / 1024))
    if v.is_integer():
        return translate(lang, "texts.traffic_gb", value=int(v))
    return translate(lang, "texts.traffic_gb", value=v)


def format_duration(days: int, lang: str = DEFAULT_LANGUAGE) -> str:
    return translate(lang, "texts.duration_days", days=days)


def generate_ref_code() -> str:
    return "".join(
        secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
    )


def build_base_email(user_id: int) -> str:
    return f"user_{user_id}@vpn_bot_for_3x-ui.com"


def normalize_sub_id(raw: Any) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    value = value.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    if len(value) < 3:
        logger.warning(f"Подозрительный sub_id: {value[:20]}...")
    return value.strip()


def build_subscription_url(sub_id: Any, json_format: bool = False) -> str:
    clean = normalize_sub_id(sub_id)
    if not clean:
        logger.warning("build_subscription_url: пустой sub_id")
        return ""
    base = str(
        Config.JSON_SUB_PANEL_BASE if json_format else Config.SUB_PANEL_BASE
    ).strip()
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


def is_admin_user(user_id: int) -> bool:
    return user_id in ADMIN_USER_ID_SET


def parse_stored_servers(value: Any) -> List[str]:
    if isinstance(value, list):
        return normalize_servers(value)
    text = str(value or "").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        return normalize_servers(parsed)
    except Exception:
        return normalize_servers(text)


def get_user_plan_servers(user: Optional[Dict[str, Any]]) -> List[str]:
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
        return translate(DEFAULT_LANGUAGE, "texts.all_available")
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


def get_server_match_tokens(server: Any) -> List[str]:
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
    inbounds: List[Dict[str, Any]], servers: List[str]
) -> List[Dict[str, Any]]:
    if not servers:
        return [dict(i) for i in inbounds if isinstance(i, dict)]
    result: List[Dict[str, Any]] = []
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
            if remark.upper().startswith(label.upper()) or tag.upper().startswith(
                label.upper()
            ):
                result.append(inb)
                break
    return result


def format_payment_time(timestamp: Any) -> str:
    raw = str(timestamp or "")
    if not raw:
        return "-"
    try:
        return datetime.fromisoformat(raw).strftime("%d.%m.%Y %H:%M")
    except Exception:
        return raw


def is_expiring_soon(state: Dict[str, Any], days: Optional[int] = None) -> bool:
    days = days if days is not None else Config.EXPIRY_ALERT_DAYS
    max_expiry = to_int(state.get("max_expiry"), 0)
    if max_expiry <= 0:
        return False
    return 0 < (max_expiry - int(time.time() * 1000)) <= days * 86400 * 1000


def kb(rows: List[List[Dict[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(**btn) for btn in row]  # type: ignore[arg-type]
            for row in rows
        ]
    )


# === Тарифы ===
class TariffCatalog:
    def __init__(self, path: str):
        self.path = path
        self._active: List[Dict[str, Any]] = []
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self._by_name: Dict[str, Dict[str, Any]] = {}
        self._locations: List[Dict[str, Any]] = []
        self._locations_by_code: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def is_trial(plan: Optional[Dict[str, Any]]) -> bool:
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
                    raw.get("code")
                    or raw.get("id")
                    or raw.get("flag")
                    or raw.get("name")
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
            except Exception as e:
                logger.error(f"Ошибка обработки локации {i}: {e}")

        plans = data.get("plans") or []
        normalized = []
        for raw in plans:
            if not isinstance(raw, dict):
                continue
            try:
                plan = dict(raw)
                plan["servers"] = normalize_servers(
                    plan.get("servers")
                    if "servers" in plan
                    else plan.get("description")
                )
                plan.setdefault("active", True)
                normalized.append(plan)
            except Exception as e:
                logger.error(f"Ошибка обработки плана: {e}")

        self._locations = locations
        self._locations_by_code = locations_by_code
        self._active = [p for p in normalized if p.get("active", True)]
        self._active.sort(key=lambda p: (p.get("sort", 9999), p.get("price_rub", 0)))
        self._by_id = {p.get("id"): p for p in normalized if p.get("id")}
        self._by_name = {p.get("name"): p for p in normalized if p.get("name")}

    def get_all_active(self) -> List[Dict[str, Any]]:
        return self._active

    def get_by_id(self, plan_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(plan_id)

    def get_by_name(self, plan_name: str) -> Optional[Dict[str, Any]]:
        return self._by_name.get(plan_name)

    def get_minimal_by_price(self) -> Optional[Dict[str, Any]]:
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

    def get_locations(self) -> List[Dict[str, Any]]:
        return [dict(loc) for loc in self._locations]

    def get_location_by_code(self, code: str) -> Optional[Dict[str, Any]]:
        loc = self._locations_by_code.get(normalize_server_code(code))
        return dict(loc) if loc else None


tariff_catalog = TariffCatalog(Config.TARIFFS_PATH)


def load_tariffs() -> None:
    tariff_catalog.load()


def get_all_active() -> List[Dict[str, Any]]:
    return tariff_catalog.get_all_active()


def get_by_id(plan_id: str) -> Optional[Dict[str, Any]]:
    return tariff_catalog.get_by_id(plan_id)


def get_by_name(plan_name: str) -> Optional[Dict[str, Any]]:
    return tariff_catalog.get_by_name(plan_name)


def is_trial_plan(plan: Optional[Dict[str, Any]]) -> bool:
    return tariff_catalog.is_trial(plan)


def get_minimal_by_price() -> Optional[Dict[str, Any]]:
    return tariff_catalog.get_minimal_by_price()


def get_custom_locations() -> List[Dict[str, Any]]:
    return tariff_catalog.get_locations()


def get_location_by_code(code: str) -> Optional[Dict[str, Any]]:
    return tariff_catalog.get_location_by_code(code)


def get_plan_servers(plan: Optional[Dict[str, Any]]) -> List[str]:
    if not plan:
        return []
    return normalize_servers(plan.get("servers"))


def get_location_price_per_day(code: str) -> float:
    loc = get_location_by_code(code)
    if not loc:
        return Config.CUSTOM_TARIFF_LOCATION_DAY_PRICE
    return max(0.0, parse_float_value(loc.get("price_per_day_rub"), 0.0))


def get_purchasable_catalog_plan(plan_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    plan = get_by_id(plan_id)
    if not plan or not plan.get("active", True):
        return None, translate(DEFAULT_LANGUAGE, "texts.plan_not_found")
    if is_trial_plan(plan):
        return None, translate(DEFAULT_LANGUAGE, "texts.trial_note")
    return plan, ""


# === Кастомный тариф ===
def custom_tariff_enabled() -> bool:
    return bool(Config.CUSTOM_TARIFF_ENABLED)


def custom_ip_bounds() -> Tuple[int, int]:
    mn = max(1, min(Config.CUSTOM_TARIFF_MIN_IP, Config.CUSTOM_TARIFF_MAX_IP))
    mx = max(1, max(Config.CUSTOM_TARIFF_MIN_IP, Config.CUSTOM_TARIFF_MAX_IP))
    return mn, mx


def custom_gb_bounds() -> Tuple[int, int]:
    mn = max(1, min(Config.CUSTOM_TARIFF_MIN_GB, Config.CUSTOM_TARIFF_MAX_GB))
    mx = max(1, max(Config.CUSTOM_TARIFF_MIN_GB, Config.CUSTOM_TARIFF_MAX_GB))
    return mn, mx


def custom_days_bounds() -> Tuple[int, int]:
    mn = max(1, min(Config.CUSTOM_TARIFF_MIN_DAYS, Config.CUSTOM_TARIFF_MAX_DAYS))
    mx = max(1, max(Config.CUSTOM_TARIFF_MIN_DAYS, Config.CUSTOM_TARIFF_MAX_DAYS))
    return mn, mx


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
    servers: Optional[List[str]] = None,
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
    servers: Optional[List[str]] = None,
) -> str:
    return translate(
        DEFAULT_LANGUAGE,
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
    servers: Optional[List[str]] = None,
    plan_name: Optional[str] = None,
) -> Dict[str, Any]:
    selected = normalize_servers(servers)
    base = int(
        round(
            calculate_custom_tariff_total(traffic_gb, ip_limit, duration_days, selected)
        )
    )
    return {
        "id": "custom",
        "name": plan_name
        or build_custom_plan_name(traffic_gb, ip_limit, duration_days, selected),
        "price_rub": base,
        "ip_limit": ip_limit,
        "traffic_gb": traffic_gb,
        "duration_days": duration_days,
        "servers": selected,
        "active": True,
    }


def build_custom_tariff_info_block(lang: str = DEFAULT_LANGUAGE) -> str:
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
                price=format_number(
                    parse_float_value(loc.get("price_per_day_rub"), 0.0)
                ),
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
    payment: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], str]:
    custom = payment.get("custom_plan")
    if not isinstance(custom, dict):
        return None, translate(DEFAULT_LANGUAGE, "texts.custom_plan_invalid_params")
    traffic = to_int(custom.get("traffic_gb"), 0)
    ip = to_int(custom.get("ip_limit"), 0)
    days = to_int(custom.get("duration_days"), 0)
    servers = normalize_servers(custom.get("servers"))
    if not is_valid_custom_limits(traffic, ip, days):
        return None, translate(
            DEFAULT_LANGUAGE, "texts.custom_plan_limits_out_of_range"
        )
    if not is_valid_custom_servers(servers):
        return None, translate(DEFAULT_LANGUAGE, "texts.custom_plan_invalid_locations")
    plan_name = str(custom.get("plan_name") or "").strip()
    return (
        build_custom_plan(
            traffic, ip, days, servers=servers, plan_name=plan_name or None
        ),
        "",
    )


# === Очки доверия ===
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


def apply_trust_discount(price: float, trust_score: int) -> Tuple[float, int]:
    if trust_score <= 0:
        return price, 0
    disc = calculate_discount_percent(trust_score)
    return price - (price * disc / 100.0), disc


async def apply_trust_score_delta(
    user_id: int, delta: int
) -> Tuple[bool, int, int, int]:
    before = await db.get_trust_score(user_id)
    if delta == 0:
        return True, before, before, 0
    updated = await db.add_trust_score(user_id, delta)
    if not updated:
        return False, before, before, 0
    after = await db.get_trust_score(user_id)
    return True, before, after, after - before


def build_trust_change_line(delta: int, before: int, after: int) -> str:
    if delta > 0:
        return translate(
            DEFAULT_LANGUAGE,
            "texts.trust_change_positive",
            delta=delta,
            before=before,
            after=after,
        )
    if delta < 0:
        return translate(
            DEFAULT_LANGUAGE,
            "texts.trust_change_negative",
            delta=delta,
            before=before,
            after=after,
        )
    return translate(DEFAULT_LANGUAGE, "texts.trust_change_none", after=after)


# === База данных SQLite ===
class Database:
    USER_COLUMN_DEFS: Dict[str, str] = {
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
    }

    def __init__(self, db_path: str):
        self.db_path: str = db_path
        self.conn: Optional[aiosqlite.Connection] = None
        self.lock: asyncio.Lock = asyncio.Lock()

    async def connect(self) -> None:
        try:
            parent = os.path.dirname(self.db_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

            async def _connect() -> aiosqlite.Connection:
                conn = await aiosqlite.connect(self.db_path, timeout=30.0)
                return conn

            self.conn = await retry_async(
                _connect,
                max_retries=3,
                delay=1.0,
                exceptions=(aiosqlite.Error, Exception),
            )
            self.conn.row_factory = aiosqlite.Row
            await self.conn.execute("PRAGMA foreign_keys = ON")
            await self.conn.execute("PRAGMA journal_mode = WAL")
            await self.conn.execute("PRAGMA busy_timeout = 5000")
            await self.conn.execute("PRAGMA cache_size = -256000")  # 256MB cache
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
            except Exception as e:
                logger.warning(f"Ошибка закрытия БД: {e}")
            finally:
                self.conn = None

    async def init_db(self) -> None:
        if not self.conn:
            return
        async with self.lock:
            try:
                await self.conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
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
                        extra_sub_gb INTEGER DEFAULT 0
                    )
                """)
                await self._migrate_users_table()
                try:
                    await self.conn.execute("""
                        CREATE UNIQUE INDEX IF NOT EXISTS idx_users_ref_code
                        ON users(ref_code)
                        WHERE ref_code IS NOT NULL AND ref_code != ''
                        """)
                except Exception as e:
                    logger.warning(f"Не удалось создать индекс ref_code: {e}")
                await self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_ref_by ON users(ref_by)"
                )
                await self.conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_users_vpn_url ON users(vpn_url)"
                )
                await self.conn.commit()
                logger.info("Таблица users создана/проверена")
            except Exception as e:
                logger.error(f"Ошибка инициализации БД: {e}")
                raise DatabaseError(f"Ошибка init_db: {e}") from e

    async def _migrate_users_table(self) -> None:
        if not self.conn:
            return
        cur = await self.conn.execute("PRAGMA table_info(users)")
        rows = await cur.fetchall()
        existing = {str(row[1]) for row in rows}
        for column, definition in self.USER_COLUMN_DEFS.items():
            if column in existing:
                continue
            await self.conn.execute(
                f"ALTER TABLE users ADD COLUMN {column} {definition}"
            )
            logger.info(f"Добавлена колонка users.{column}")

    @log_error
    async def add_user(self, user_id: int, *, force: bool = False) -> bool:
        if not force and is_admin_user(user_id):
            return False
        if not self.conn:
            return False

        try:
            async with self.lock:

                async def _insert() -> None:
                    assert self.conn is not None
                    await self.conn.execute(
                        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
                        (user_id,),
                    )
                    await self.conn.commit()

                await retry_async(_insert, max_retries=3, delay=0.5)
            return True
        except Exception as e:
            logger.error(f"add_user {user_id}: {e}")
            return False

    @log_error
    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        if not self.conn:
            logger.error(f"get_user {user_id}: соединение с БД отсутствует")
            return None

        try:
            async with self.lock:
                cur = await self.conn.execute(
                    "SELECT * FROM users WHERE user_id = ?", (user_id,)
                )
                row = await cur.fetchone()
                return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_user {user_id}: {e}")
            return None

    @log_error
    async def get_user_by_ref_code(self, ref_code: str) -> Optional[Dict[str, Any]]:
        if not self.conn:
            return None

        try:
            cur = await self.conn.execute(
                "SELECT * FROM users WHERE ref_code = ?", (ref_code,)
            )
            row = await cur.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"get_user_by_ref_code {ref_code}: {e}")
            return None

    @log_error
    async def update_user(self, user_id: int, *, force: bool = False, **kwargs) -> bool:
        if not self.conn or not kwargs:
            return False
        if not force and is_admin_user(user_id):
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
        values: List[Any] = list(values_by_column.values()) + [user_id]

        try:
            async with self.lock:
                await self.conn.execute(
                    f"UPDATE users SET {set_clause} WHERE user_id = ?",
                    values,
                )
                await self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"update_user {user_id}: {e}")
            return False

    @log_error
    async def get_total_users(self) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute("SELECT COUNT(*) FROM users")
            row = await cur.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"get_total_users: {e}")
            return 0

    @log_error
    async def get_banned_users_count(self) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1")
            row = await cur.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"get_banned_users_count: {e}")
            return 0

    @log_error
    async def get_banned_user_ids(self) -> List[int]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute("SELECT user_id FROM users WHERE banned = 1")
            rows = await cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"get_banned_user_ids: {e}")
            return []

    @log_error
    async def get_subscribed_user_ids(self) -> List[int]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute(
                "SELECT user_id FROM users WHERE vpn_url != '' AND vpn_url IS NOT NULL"
            )
            rows = await cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"get_subscribed_user_ids: {e}")
            return []

    @log_error
    async def get_all_non_banned_user_ids(self) -> List[int]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute("SELECT user_id FROM users WHERE banned = 0")
            rows = await cur.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"get_all_non_banned_user_ids: {e}")
            return []

    @log_error
    async def get_all_users(self) -> List[Dict[str, Any]]:
        if not self.conn:
            return []
        try:
            cur = await self.conn.execute("SELECT * FROM users ORDER BY user_id")
            rows = await cur.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"get_all_users: {e}")
            return []

    @log_error
    async def ban_user(self, user_id: int, reason: str = "") -> bool:
        if is_admin_user(user_id):
            return False
        await self.add_user(user_id)
        await self.update_user(user_id, trust_score=0)
        return await self.update_user(user_id, banned=True, ban_reason=reason)

    @log_error
    async def unban_user(self, user_id: int) -> bool:
        if is_admin_user(user_id):
            return False
        return await self.update_user(user_id, banned=False, ban_reason="")

    @log_error
    async def set_subscription(
        self,
        user_id: int,
        plan_text: str,
        ip_limit: int,
        vpn_url: str,
        traffic_gb: int,
        plan_servers: Optional[List[str]] = None,
        subscription_id: Optional[str] = None,
        expiry_sub_datatime: str = "",
    ) -> bool:
        await self.add_user(user_id, force=True)
        return await self.update_user(
            user_id=user_id,
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
        await self.add_user(user_id, force=True)
        return await self.update_user(
            user_id=user_id,
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
        if is_admin_user(user_id):
            return False
        await self.add_user(user_id)
        return await self.update_user(user_id, expiry_alert_sent=1 if sent else 0)

    @log_error
    async def add_extra_traffic(self, user_id: int, extra_gb: int) -> bool:
        if extra_gb <= 0:
            return False
        await self.add_user(user_id, force=True)
        user = await self.get_user(user_id)
        if not user:
            return False
        current_extra = to_int(user.get("extra_sub_gb"), 0)
        return await self.update_user(
            user_id, force=True, extra_sub_gb=current_extra + int(extra_gb)
        )

    @log_error
    async def get_user_language(self, user_id: int) -> str:
        if not self.conn:
            return ""
        try:
            cur = await self.conn.execute(
                "SELECT language FROM users WHERE user_id = ?", (user_id,)
            )
            row = await cur.fetchone()
            if not row:
                return ""
            return str(row[0] or "").strip().lower()
        except Exception as e:
            logger.error(f"get_user_language {user_id}: {e}")
            return ""

    @log_error
    async def set_user_language(self, user_id: int, language: str) -> bool:
        if is_admin_user(user_id):
            return False
        await self.add_user(user_id)
        return await self.update_user(user_id, language=language)

    @log_error
    async def set_ref_by(self, user_id: int, referrer_id: int) -> bool:
        if is_admin_user(user_id) or is_admin_user(referrer_id):
            return False
        if user_id <= 0 or referrer_id <= 0 or user_id == referrer_id:
            return False
        await self.add_user(user_id)
        user = await self.get_user(user_id)
        if not user or to_int(user.get("ref_by"), 0):
            return False
        return await self.update_user(user_id, ref_by=referrer_id)

    @log_error
    async def set_has_subscription(self, user_id: int) -> bool:
        if is_admin_user(user_id):
            return False
        await self.add_user(user_id)
        return await self.update_user(user_id, has_subscription=1)

    @log_error
    async def mark_trial_used(self, user_id: int) -> bool:
        if is_admin_user(user_id):
            return False
        await self.add_user(user_id)
        return await self.update_user(user_id, trial_used=1, has_subscription=1)

    @log_error
    async def mark_ref_rewarded(self, user_id: int) -> bool:
        if is_admin_user(user_id):
            return False
        return await self.update_user(user_id, ref_rewarded=1)

    @log_error
    async def count_referrals(self, user_id: int) -> int:
        if not self.conn:
            return 0
        try:
            cur = await self.conn.execute(
                "SELECT COUNT(*) FROM users WHERE ref_by = ?", (user_id,)
            )
            row = await cur.fetchone()
            return int(row[0]) if row else 0
        except Exception as e:
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
        except Exception as e:
            logger.error(f"count_referrals_paid {user_id}: {e}")
            return 0

    @log_error
    async def get_bonus_days_pending(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        return max(0, to_int(user.get("bonus_days_pending"), 0)) if user else 0

    @log_error
    async def add_bonus_days_pending(self, user_id: int, days: int) -> bool:
        if is_admin_user(user_id) or days <= 0:
            return False
        await self.add_user(user_id)
        current = await self.get_bonus_days_pending(user_id)
        return await self.update_user(
            user_id, bonus_days_pending=max(0, current + int(days))
        )

    @log_error
    async def clear_bonus_days_pending(self, user_id: int) -> bool:
        if is_admin_user(user_id):
            return False
        return await self.update_user(user_id, bonus_days_pending=0)

    @log_error
    async def get_trust_score(self, user_id: int) -> int:
        user = await self.get_user(user_id)
        if not user:
            return 0
        return to_int(user.get("trust_score"), 0)

    @log_error
    async def add_trust_score(self, user_id: int, points: int) -> bool:
        if is_admin_user(user_id):
            return False
        await self.add_user(user_id)
        current = await self.get_trust_score(user_id)
        new_score = max(TRUST_SCORE_MIN, min(TRUST_SCORE_MAX, current + points))
        return await self.update_user(user_id, trust_score=new_score)

    @log_error
    async def ensure_ref_code(self, user_id: int) -> Optional[str]:
        if is_admin_user(user_id):
            return None
        user = await self.get_user(user_id)
        if not user:
            await self.add_user(user_id)
            user = await self.get_user(user_id)
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

    @log_error
    async def reset_all_trials(self) -> Tuple[int, int]:
        if not self.conn:
            return 0, 1
        try:
            cur_count = await self.conn.execute("SELECT COUNT(*) FROM users")
            total = cur_count.fetchone()[0]

            cur = await self.conn.execute("UPDATE users SET trial_used = 0")
            await self.conn.commit()

            return total, 0
        except Exception as e:
            logger.error(f"reset_all_trials: {e}")
            return 0, 1


# === JSON Storage для платежей ===
class JSONStorage:
    def __init__(self, path: str):
        self.path: str = path
        self._lock: asyncio.Lock = asyncio.Lock()
        self._data: List[Dict[str, Any]] = []

    @log_error
    async def _load(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.path):
            try:
                async with aiofiles.open(self.path, "r", encoding="utf-8") as f:
                    content = await f.read()
                    if content:
                        parsed = json.loads(content)
                        if not isinstance(parsed, list):
                            logger.error(
                                f"Некорректный формат {self.path}: ожидался список"
                            )
                            self._data = []
                        else:
                            self._data = parsed
                        logger.info(f"Загружено {len(self._data)} записей платежей")
                    else:
                        self._data = []
            except Exception as e:
                logger.error(f"Ошибка загрузки {self.path}: {e}")
                self._data = []
        else:
            self._data = []
        return self._data

    @log_error
    async def _save(self) -> None:
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

    async def _ensure_file(self) -> None:
        if os.path.exists(self.path):
            return
        try:
            parent = os.path.dirname(self.path)
            if parent:
                os.makedirs(parent, exist_ok=True)
        except Exception:
            pass
        if not os.path.exists(self.path):
            try:
                async with aiofiles.open(self.path, "w", encoding="utf-8") as f:
                    await f.write("[]")
            except Exception:
                pass

    @log_error
    async def add_pending_for_user(self, user_id: int, payment: Dict[str, Any]) -> bool:
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
        except Exception as e:
            logger.error(f"Ошибка add_pending_for_user {user_id}: {e}")
            return False

    @log_error
    async def read_all(self) -> List[Dict[str, Any]]:
        try:
            async with self._lock:
                await self._load()
                return [dict(item) for item in self._data if isinstance(item, dict)]
        except Exception as e:
            logger.error(f"Ошибка read_all: {e}")
            return []

    @log_error
    async def find_by_id(self, payment_id: str) -> Optional[Dict[str, Any]]:
        try:
            async with self._lock:
                await self._load()
                for p in self._data:
                    if str(p.get("payment_id")) == str(payment_id):
                        return dict(p)
                return None
        except Exception as e:
            logger.error(f"Ошибка find_by_id {payment_id}: {e}")
            return None

    @log_error
    async def claim_pending_payment(
        self, payment_id: str, moderator_id: int, action: str
    ) -> Optional[Dict[str, Any]]:
        try:
            async with self._lock:
                await self._load()
                for p in self._data:
                    if str(p.get("payment_id")) == str(payment_id):
                        if p.get("status") != "pending":
                            return None
                        processing = p.get("processing_by")
                        if processing is not None and processing != moderator_id:
                            return None
                        p["status"] = "processing"
                        p["processing_by"] = moderator_id
                        p["processing_action"] = action
                        p["processing_at"] = datetime.now().isoformat()
                        await self._save()
                        return dict(p)
                return None
        except Exception as e:
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
        try:
            async with self._lock:
                await self._load()
                for p in self._data:
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
                        p["processed_at"] = datetime.now().isoformat()
                        p["processing_by"] = None
                        p["processing_at"] = None
                        await self._save()
                        return True
                return False
        except Exception as e:
            logger.error(f"Ошибка finalize_claimed_payment {payment_id}: {e}")
            return False

    @log_error
    async def rollback_claimed_payment(
        self,
        payment_id: str,
        moderator_id: int,
        action: str,
        error_message: str = "",
    ) -> None:
        try:
            async with self._lock:
                await self._load()
                for p in self._data:
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
                        await self._save()
                        return
        except Exception as e:
            logger.error(f"Ошибка rollback_claimed_payment {payment_id}: {e}")

    @log_error
    async def release_stale_processing_payments(self) -> int:
        try:
            async with self._lock:
                await self._load()
                released = 0
                now = datetime.now()
                for p in self._data:
                    if p.get("status") != "processing":
                        continue
                    processing_at = p.get("processing_at")
                    if not processing_at:
                        continue
                    try:
                        pt = datetime.fromisoformat(processing_at)
                        if (now - pt).total_seconds() > PAYMENT_PROCESSING_TIMEOUT_SEC:
                            p["status"] = "pending"
                            p["processing_by"] = None
                            p["processing_at"] = None
                            p["processing_action"] = None
                            p["last_error"] = "Timeout"
                            released += 1
                    except Exception:
                        continue
                if released > 0:
                    await self._save()
                return released
        except Exception as e:
            logger.error(f"Ошибка release_stale_processing_payments: {e}")
            return 0

    @log_error
    async def remove(self, predicate: Callable[[Dict[str, Any]], bool]) -> None:
        try:
            async with self._lock:
                await self._load()
                before = len(self._data)
                self._data = [p for p in self._data if not predicate(p)]
                after = len(self._data)
                if before != after:
                    await self._save()
        except Exception as e:
            logger.error(f"Ошибка remove: {e}")


# === Panel API 3X-UI ===
class PanelAPI:
    def __init__(self) -> None:
        self.apibase: str = Config.PANEL_BASE.rstrip("/")
        self.username: str = Config.PANEL_LOGIN
        self.password: str = Config.PANEL_PASSWORD
        self.verifyssl: bool = Config.VERIFY_SSL
        self.session: Optional[aiohttp.ClientSession] = None
        self.token: Optional[str] = Config.PANEL_TOKEN or None
        self.logged_in: bool = bool(self.token)
        self.lock: asyncio.Lock = asyncio.Lock()

    @log_error
    async def start(self) -> None:
        try:
            connector = aiohttp.TCPConnector(ssl=self.verifyssl)
            self.session = aiohttp.ClientSession(
                connector=connector,
                timeout=aiohttp.ClientTimeout(total=15),
                cookie_jar=aiohttp.CookieJar(unsafe=True),
            )
            if not self.token:
                await self.login()
            else:
                logger.info("Используется PANEL_TOKEN")
        except Exception as e:
            logger.critical(f"Ошибка запуска PanelAPI: {e}")
            raise

    @log_error
    async def close(self) -> None:
        if self.session:
            try:
                await self.session.close()
                logger.info("PanelAPI сессия закрыта")
            except Exception as e:
                logger.warning(f"Ошибка закрытия PanelAPI: {e}")
            finally:
                self.session = None

    @log_error
    async def _request_json(
        self, method: str, url: str, **kwargs: Any
    ) -> Tuple[int, Dict[str, Any], str]:
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
        except Exception as e:
            logger.error(f"Неожиданная ошибка {method} {url}: {type(e).__name__}: {e}")
            return 0, {}, ""

    @staticmethod
    def _needs_reauth(status: int, data: Dict[str, Any]) -> bool:
        if status in (401, 403):
            return True
        msg = str(data.get("msg", "")).lower()
        markers = (
            "login",
            "auth",
            "unauthorized",
            "session",
            "csrf",
            "автор",
            "сесс",
            "войд",
        )
        if status == 404 and any(m in msg for m in markers):
            return True
        if (
            status == 200
            and data.get("success") is False
            and any(m in msg for m in markers)
        ):
            return True
        if status >= 400 and any(m in msg for m in ("login", "auth")):
            return True
        return False

    @log_error
    async def _request_json_with_reauth(
        self, method: str, url: str, **kwargs: Any
    ) -> Tuple[int, Dict[str, Any], str]:
        status, data, text = await self._request_json(method, url, **kwargs)
        if self._needs_reauth(status, data):
            logger.warning("Требуется реавторизация")
            await self.login()
            status, data, text = await self._request_json(method, url, **kwargs)
        return status, data, text

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
                        logger.info("Авторизация в 3X-UI успешна")
                    else:
                        self.logged_in = False
                        logger.error(
                            f"Ошибка авторизации 3X-UI: status={resp.status}, msg={data.get('msg')}, body={raw_text[:500]}"
                        )
            except Exception as e:
                self.logged_in = False
                logger.error(f"Ошибка авторизации: {type(e).__name__}: {e}")

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _quote_path(value: Any) -> str:
        return quote(str(value or "").strip(), safe="")

    @log_error
    async def ensure_auth(self) -> None:
        if not self.logged_in:
            await self.login()

    @log_error
    async def get_inbounds(self) -> Optional[Dict[str, Any]]:
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
        except Exception as e:
            logger.error(f"Ошибка get_inbounds: {e}")
            return None

    def _filter_inbounds_for_servers(
        self, inbounds: Any, servers: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        rows = inbounds if isinstance(inbounds, list) else []
        enabled = [
            dict(inb)
            for inb in rows
            if isinstance(inb, dict) and bool(inb.get("enable", True))
        ]
        selected = normalize_servers(servers)
        if not selected:
            return enabled
        result: List[Dict[str, Any]] = []
        for inb in enabled:
            remark = str(inb.get("remark") or "").strip()
            tag = str(inb.get("tag") or "").strip()
            if not remark and not tag:
                continue
            for server in selected:
                loc = get_location_by_code(server)
                if not loc:
                    continue
                label = str(loc.get("label") or "").strip()
                if not label:
                    continue
                if remark.upper().startswith(label.upper()) or tag.upper().startswith(
                    label.upper()
                ):
                    result.append(inb)
                    break
        if not result:
            logger.warning(
                "Не найдены inbound'ы для серверов %s. Проверьте remark/tag в панели.",
                ", ".join(selected),
            )
        return result

    @log_error
    async def _check_inbound_matches_servers(
        self,
        inbound_id: int,
        servers: Optional[List[str]],
        inbounds_cache: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        selected = normalize_servers(servers)
        if not selected:
            return True
        if inbounds_cache is not None:
            matched = self._filter_inbounds_for_servers(inbounds_cache, selected)
        else:
            inbounds = await self.get_inbounds()
            if not inbounds or not inbounds.get("success"):
                return False
            matched = self._filter_inbounds_for_servers(
                inbounds.get("obj", []), selected
            )
        return any(to_int(inb.get("id"), 0) == to_int(inbound_id, 0) for inb in matched)

    async def get_matching_inbound_ids(
        self, servers: Optional[List[str]]
    ) -> Optional[List[int]]:
        inbounds = await self.get_inbounds()
        if not inbounds or not inbounds.get("success"):
            return None
        obj = inbounds.get("obj", [])
        if isinstance(obj, dict):
            obj = obj.get("items") or obj.get("data") or obj.get("inbounds") or []
        enabled = self._filter_inbounds_for_servers(obj, servers)
        return [
            to_int(inb.get("id"), 0) for inb in enabled if to_int(inb.get("id"), 0) > 0
        ]

    @log_error
    async def get_clients(self) -> Optional[Dict[str, Any]]:
        await self.ensure_auth()
        url = f"{self.apibase}/panel/api/clients/list"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "GET", url, headers=self._headers()
            )
            if status == 200 and data.get("success"):
                return data
            logger.error(f"Ошибка clients/list: {data.get('msg')}")
            return None
        except Exception as e:
            logger.error(f"Ошибка get_clients: {e}")
            return None

    @log_error
    async def get_client_by_email(self, email: str) -> Optional[Dict[str, Any]]:
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
                    client["inboundIds"] = obj.get("inboundIds") or client.get(
                        "inboundIds", []
                    )
                    return client
                return obj if isinstance(obj, dict) else None
            return None
        except Exception as e:
            logger.error(f"Ошибка get_client_by_email: {e}")
            return None

    @log_error
    async def create_client(
        self,
        email: str,
        limit_ip: int,
        total_gb: int,
        days: int = 30,
        servers: Optional[List[str]] = None,
        tg_id: int = 0,
        inbound_ids: Optional[List[int]] = None,
    ) -> Optional[Dict[str, Any]]:
        await self.ensure_auth()
        expiry_ms = int((time.time() + days * 86400) * 1000)
        total_bytes = int(total_gb * BYTES_IN_GB)
        sub_id = f"user_{uuid.uuid4().hex[:12]}"
        if inbound_ids is None:
            inbound_ids = await self.get_matching_inbound_ids(servers)
            if inbound_ids is None:
                return None
        else:
            inbound_ids = [to_int(i, 0) for i in inbound_ids if to_int(i, 0) > 0]
        if not inbound_ids:
            return None
        client: Dict[str, Any] = {
            "email": email,
            "enable": True,
            "flow": "",
            "limitIp": max(0, int(limit_ip)),
            "totalGB": total_bytes,
            "expiryTime": expiry_ms,
            "subId": sub_id,
            "tgId": max(0, int(tg_id or 0)),
        }
        payload: Dict[str, Any] = {"client": client, "inboundIds": inbound_ids}
        url = f"{self.apibase}/panel/api/clients/add"
        try:
            status, data, _ = await self._request_json_with_reauth(
                "POST", url, headers=self._headers(), json=payload
            )
            if status in (200, 201) and data.get("success"):
                client["inboundIds"] = inbound_ids
                return client
            logger.error(f"Ошибка clients/add: {data.get('msg')}")
            return None
        except Exception as e:
            logger.error(f"Ошибка create_client: {e}")
            return None

    @log_error
    async def create_client_in_inbound(
        self,
        inbound_id: int,
        email: str,
        limit_ip: int,
        total_gb: Union[int, float],
        expiry_ms: int,
        sub_id: str,
        tg_id: int = 0,
    ) -> bool:
        await self.ensure_auth()
        inbound = to_int(inbound_id, 0)
        if inbound <= 0 or not email:
            return False
        client: Dict[str, Any] = {
            "email": email,
            "enable": True,
            "flow": "",
            "limitIp": max(0, int(limit_ip)),
            "totalGB": int(float(total_gb) * BYTES_IN_GB),
            "expiryTime": max(0, int(expiry_ms)),
            "subId": normalize_sub_id(sub_id) or f"user_{uuid.uuid4().hex[:12]}",
            "tgId": max(0, int(tg_id or 0)),
        }
        payload: Dict[str, Any] = {"client": client, "inboundIds": [inbound]}
        url = f"{self.apibase}/panel/api/clients/add"
        status, data, _ = await self._request_json_with_reauth(
            "POST", url, headers=self._headers(), json=payload
        )
        if status in (200, 201) and data.get("success"):
            return True
        logger.error(
            f"Ошибка добавления клиента в inbound {inbound}: {data.get('msg')}"
        )
        return False

    @log_error
    async def delete_client(self, base_email: str) -> bool:
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
        seen: Set[str] = set()
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
            except Exception as e:
                logger.error(f"Ошибка delete_client: {e}")
                success = False
        return success

    async def attach_client_to_inbounds(
        self, email: str, inbound_ids: List[int]
    ) -> bool:
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
                logger.info(
                    f"attach_client: клиент {email} привязан к inbound'ам {clean_ids}"
                )
                return True
            logger.error(
                f"attach_client: ошибка для {email}: status={status}, "
                f"data={data}, msg={data.get('msg')}"
            )
            return False
        except Exception as e:
            logger.error(f"attach_client: ошибка для {email}: {e}", exc_info=True)
            return False

    async def detach_client_from_inbounds(
        self, email: str, inbound_ids: List[int]
    ) -> bool:
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
                logger.info(
                    f"detach_client: клиент {email} отвязан от inbound'ов {clean_ids}"
                )
                return True
            logger.error(
                f"detach_client: ошибка для {email}: status={status}, "
                f"data={data}, msg={data.get('msg')}"
            )
            return False
        except Exception as e:
            logger.error(f"detach_client: ошибка для {email}: {e}", exc_info=True)
            return False

    async def _collect_unique_client_emails(self, base_email: str) -> List[str]:
        ok, clients = await self.find_clients_full_by_email_safe(base_email)
        if not ok or not clients:
            return []
        emails: List[str] = []
        seen: Set[str] = set()
        for c in clients:
            email = str(c.get("email") or "")
            if email and email not in seen:
                seen.add(email)
                emails.append(email)
        return emails

    async def reset_client_traffic(self, base_email: str) -> bool:
        await self.ensure_auth()
        emails = await self._collect_unique_client_emails(base_email)
        if not emails:
            logger.warning(f"reset_client_traffic: клиенты не найдены для {base_email}")
            return False

        bulk_url = f"{self.apibase}/panel/api/clients/bulkResetTraffic"
        bulk_payload: Dict[str, Any] = {"emails": emails}
        status, data, _ = await self._request_json_with_reauth(
            "POST", bulk_url, headers=self._headers(), json=bulk_payload
        )
        if status in (200, 201) and data.get("success"):
            logger.info(
                f"reset_client_traffic: успешно сброшен трафик для {len(emails)} клиентов"
            )
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

    async def extend_client_expiry(self, base_email: str, add_days: int) -> bool:
        if add_days <= 0:
            logger.warning(
                f"extend_client_expiry: некорректное количество дней ({add_days})"
            )
            return False
        emails = await self._collect_unique_client_emails(base_email)
        if not emails:
            logger.warning(
                f"extend_client_expiry: нет email для продления {base_email}"
            )
            return False
        url = f"{self.apibase}/panel/api/clients/bulkAdjust"
        payload: Dict[str, Any] = {"emails": emails, "addDays": add_days}
        status, data, _ = await self._request_json_with_reauth(
            "POST", url, headers=self._headers(), json=payload
        )
        if status in (200, 201) and data.get("success"):
            adjusted = 0
            skipped: List[str] = []
            obj = data.get("obj") or {}
            if isinstance(obj, dict):
                adjusted = to_int(obj.get("adjusted", 0), 0)
                skipped = obj.get("skipped", [])
            logger.info(
                f"extend_client_expiry: успешно продлено {adjusted} клиентов "
                f"на {add_days} дней, пропущено {len(skipped)}: {skipped}"
            )
            return adjusted > 0
        else:
            logger.error(
                f"extend_client_expiry: ошибка bulkAdjust для {emails}: "
                f"status={status}, data={data.get('msg')}"
            )
            return False

    async def get_client_stats_safe(
        self, base_email: str
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        return await self.find_clients_by_base_email_safe(base_email)

    async def add_client_traffic(self, base_email: str, add_gb: int) -> bool:
        if add_gb <= 0:
            return False
        emails = await self._collect_unique_client_emails(base_email)
        if not emails:
            logger.warning(
                f"add_client_traffic: нет email для начисления трафика {base_email}"
            )
            return False
        add_bytes = int(add_gb * BYTES_IN_GB)
        url = f"{self.apibase}/panel/api/clients/bulkAdjust"
        payload: Dict[str, Any] = {"emails": emails, "addBytes": add_bytes}
        status, data, _ = await self._request_json_with_reauth(
            "POST", url, headers=self._headers(), json=payload
        )
        if status in (200, 201) and data.get("success"):
            obj = data.get("obj") or {}
            adjusted = to_int(obj.get("adjusted", 0), 0) if isinstance(obj, dict) else 0
            logger.info(
                f"add_client_traffic: начислено {add_gb} ГБ для {adjusted} клиентов"
            )
            return adjusted > 0 or data.get("success")
        logger.error(
            f"add_client_traffic: ошибка bulkAdjust для {emails}: "
            f"status={status}, msg={data.get('msg')}"
        )
        return False

    @staticmethod
    def _is_base_email(email: str, base_email: str) -> bool:
        if not email or not base_email:
            return False
        return email.endswith(base_email)

    @staticmethod
    def _client_rows_from_response(data: Dict[str, Any]) -> List[Dict[str, Any]]:
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

    @staticmethod
    def _normalize_client_row(row: Dict[str, Any]) -> Dict[str, Any]:
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
    def _client_payload_for_update(client: Dict[str, Any]) -> Dict[str, Any]:
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
        payload: Dict[str, Any] = {
            key: client[key]
            for key in passthrough
            if key in client and client.get(key) is not None
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
            payload["totalGB"] = max(
                0, to_int(client.get("total", client.get("totalGB", 0)), 0)
            )
        if "expiryTime" not in payload:
            payload["expiryTime"] = max(0, to_int(client.get("expiryTime"), 0))
        return payload

    async def find_clients_by_base_email_safe(
        self, base_email: str
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        clients_data = await self.get_clients()
        if not clients_data or not clients_data.get("success"):
            return False, []
        result: List[Dict[str, Any]] = []
        for row in self._client_rows_from_response(clients_data):
            email = str(row.get("email") or "")
            if self._is_base_email(email, base_email):
                result.append(self._normalize_client_row(row))
        return True, result

    async def find_clients_full_by_email_safe(
        self, base_email: str
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        ok, result = await self.find_clients_by_base_email_safe(base_email)
        if not ok:
            return False, []
        logger.info(f"Найдено {len(result)} клиентов по base_email='{base_email}'")
        return True, result

    async def find_clients_full_by_email(self, base_email: str) -> List[Dict[str, Any]]:
        ok, clients = await self.find_clients_full_by_email_safe(base_email)
        return clients if ok else []

    async def find_clients_by_sub_id_safe(
        self, sub_id: str
    ) -> Tuple[bool, List[Dict[str, Any]]]:
        if not sub_id:
            return False, []
        clients_data = await self.get_clients()
        if not clients_data or not clients_data.get("success"):
            return False, []
        result: List[Dict[str, Any]] = []
        for row in self._client_rows_from_response(clients_data):
            email = str(row.get("email") or "")
            client_sub_id = str(row.get("subId", "") or "")
            if client_sub_id == sub_id:
                result.append(self._normalize_client_row(row))
        return True, result

    @log_error
    async def disconnect_subscription(self, sub_id: str) -> bool:
        await self.ensure_auth()
        if not sub_id:
            return False
        clients_ok, clients = await self.find_clients_by_sub_id_safe(sub_id)
        if not clients_ok or not clients:
            logger.warning(f"Клиенты с subId {sub_id} не найдены")
            return False
        success = True
        seen: Set[str] = set()
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
        return success


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


# === Глобальные объекты ===
_bot_token: str = (
    Config.BOT_TOKEN if is_valid_bot_token_format(Config.BOT_TOKEN) else ""
)
if not _bot_token:
    logger.critical("BOT_TOKEN не настроен или некорректен. Бот не будет запущен.")
    sys.exit(1)

bot: Optional[Bot] = Bot(
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


# === Клавиатуры и вспомогательные функции ===
def support_keyboard(include_main: bool = True) -> InlineKeyboardMarkup:
    rows = []
    if Config.SUPPORT_URL:
        rows.append(
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.support"),
                    "url": Config.SUPPORT_URL,
                }
            ]
        )
    if include_main:
        rows.append(
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ]
        )
    if not rows:
        rows = [
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
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
                    "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
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
                    "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
                    "callback_data": "cancel",
                }
            ]
        ]
    )


def _build_social_links(language: str) -> List[Dict[str, str]]:
    social = []
    if Config.YOUTUBE_URL:
        social.append({"text": "YouTube", "url": Config.YOUTUBE_URL})
    if Config.TELEGRAM_URL:
        social.append({"text": "Telegram", "url": Config.TELEGRAM_URL})
    if Config.TIKTOK_URL:
        social.append({"text": "TikTok", "url": Config.TIKTOK_URL})
    return social if social else []


def _build_legal_links(language: str) -> List[Dict[str, str]]:
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


def _build_qna_tos_links(language: str) -> List[Dict[str, str]]:
    qna_tos = []
    if Config.QNA_URL:
        qna_tos.append(
            {"text": translate(language, "buttons.qna"), "url": Config.QNA_URL}
        )
    if Config.TERMS_OF_SERVICE_URL:
        qna_tos.append(
            {
                "text": translate(language, "buttons.terms_of_service"),
                "url": Config.TERMS_OF_SERVICE_URL,
            }
        )
    return qna_tos if qna_tos else []


def _build_admin_buttons(language: str) -> List[List[Dict[str, str]]]:
    return [
        [
            {
                "text": translate(language, "buttons.pending_payments"),
                "callback_data": "pay_await",
            }
        ],
        [
            {
                "text": translate(language, "buttons.broadcast"),
                "callback_data": "broadcast",
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
    is_admin: bool, has_active_subscription: bool, language: str = DEFAULT_LANGUAGE
) -> List[List[Dict[str, str]]]:
    rows = []

    if is_admin or not has_active_subscription:
        rows.append(
            [{"text": translate(language, "buttons.buy"), "callback_data": "buy"}]
        )

    rows.append(
        [
            {
                "text": translate(language, "buttons.my_subscription"),
                "callback_data": "mysub",
            }
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
        rows.append(
            [{"text": translate(language, "buttons.site"), "url": Config.SITE_URL}]
        )
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
                    "text": translate(DEFAULT_LANGUAGE, "buttons.my_subscription"),
                    "callback_data": "mysub",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ],
        ]
    )


def inactive_subscription_actions_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [{"text": translate(DEFAULT_LANGUAGE, "buttons.buy"), "callback_data": "buy"}]
    ]
    if Config.SUPPORT_URL:
        rows.append(
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.support"),
                    "url": Config.SUPPORT_URL,
                }
            ]
        )
    rows.append(
        [
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
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
                "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "start",
            }
        ]
    )
    return kb(rows)


def build_setup_keyboard(language: str = DEFAULT_LANGUAGE) -> InlineKeyboardMarkup:
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


def build_tariffs_text(
    plans: Optional[List[Dict[str, Any]]] = None, lang: str = DEFAULT_LANGUAGE
) -> str:
    plans = plans if plans is not None else get_all_active()
    if not plans:
        text = translate(lang, "texts.tariffs_unavailable")
        if custom_tariff_enabled():
            text += "\n\n" + build_custom_tariff_info_block(lang)
        return text
    text = translate(lang, "texts.tariffs_title")
    for idx, plan in enumerate(plans, 1):
        price = plan.get("price_rub", 0)
        duration = int(plan.get("duration_days", 30))
        if price == 0:
            price_line = translate(
                lang, "texts.price_free_for_days", days=format_duration(duration, lang)
            )
        elif duration == 30:
            price_line = translate(lang, "texts.price_monthly", price=price)
        else:
            price_line = translate(
                lang,
                "texts.price_fixed_days",
                price=price,
                duration=duration,
            )
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
    plans: Optional[List[Dict[str, Any]]] = None, lang: str = DEFAULT_LANGUAGE
) -> str:
    plans = plans if plans is not None else get_all_active()
    if not plans:
        return translate(lang, "texts.tariffs_unavailable")
    text = translate(lang, "texts.buy_fixed_title")
    for idx, plan in enumerate(plans, 1):
        price = plan.get("price_rub", 0)
        duration = int(plan.get("duration_days", 30))
        if price == 0:
            price_line = translate(
                lang, "texts.price_free_for_days", days=format_duration(duration, lang)
            )
        elif duration == 30:
            price_line = translate(lang, "texts.price_monthly", price=price)
        else:
            price_line = translate(
                lang,
                "texts.price_fixed_days",
                price=price,
                duration=duration,
            )
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
    plans: Optional[List[Dict[str, Any]]] = None,
    *,
    for_admin: bool = False,
    lang: str = DEFAULT_LANGUAGE,
) -> str:
    plans = plans if plans is not None else get_all_active()
    if not plans:
        text = translate(lang, "texts.buy_unavailable")
        if custom_tariff_enabled():
            text += translate(lang, "texts.buy_custom_button_hint")
        return text
    text = translate(lang, "texts.buy_title")
    for idx, plan in enumerate(plans, 1):
        price = plan.get("price_rub", 0)
        duration = int(plan.get("duration_days", 30))
        if price == 0:
            price_line = translate(
                lang, "texts.price_free_for_days", days=format_duration(duration, lang)
            )
        elif duration == 30:
            price_line = translate(lang, "texts.price_monthly", price=price)
        else:
            price_line = translate(
                lang,
                "texts.price_fixed_days",
                price=price,
                duration=duration,
            )
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


def build_pending_payment_text(payment: Dict[str, Any]) -> str:
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
                "name", translate(DEFAULT_LANGUAGE, "texts.custom_plan_short_name")
            )
            details = translate(
                DEFAULT_LANGUAGE,
                "texts.pending_payment_custom_details",
                traffic=format_traffic(plan.get("traffic_gb", 0)),
                ip_limit=plan.get("ip_limit", 0),
                duration=format_duration(int(plan.get("duration_days", 0))),
                servers=format_servers(plan.get("servers")),
            )
        else:
            plan_name = plan_name or translate(
                DEFAULT_LANGUAGE, "texts.custom_plan_short_name"
            )
    else:
        plan, _ = get_purchasable_catalog_plan(str(plan_id))
        if plan:
            plan_name = plan_name or plan.get("name", plan_id)
            details = translate(
                DEFAULT_LANGUAGE,
                "texts.pending_payment_catalog_locations",
                servers=format_servers(plan.get("servers")),
            )
        elif not plan_name:
            plan_name = str(plan_id)
    return translate(
        DEFAULT_LANGUAGE,
        "texts.pending_payment_text",
        payment_id=pid,
        user_id=uid,
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
                    "text": translate(DEFAULT_LANGUAGE, "buttons.confirm_payment"),
                    "callback_data": f"pay_await_accept:{payment_id}",
                },
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.reject_payment"),
                    "callback_data": f"pay_await_reject:{payment_id}",
                },
            ]
        ]
    )


def build_subscription_cleanup_message(
    reason: str,
    trust_before: Optional[int] = None,
    trust_after: Optional[int] = None,
    trust_delta: int = 0,
    lang: str = DEFAULT_LANGUAGE,
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
                        DEFAULT_LANGUAGE,
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
                "text": translate(DEFAULT_LANGUAGE, "buttons.done"),
                "callback_data": "custom:locations_done",
            }
        ]
    )
    rows.append(
        [
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
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
        else translate(DEFAULT_LANGUAGE, "texts.not_selected")
    )
    return translate(
        DEFAULT_LANGUAGE,
        "texts.custom_tariff_locations_text",
        selected_text=selected_text,
    )


# === Вспомогательные асинхронные функции ===
async def notify_admins(text: str, reply_markup: Optional[InlineKeyboardMarkup] = None):
    for admin_id in Config.ADMIN_USER_IDS:
        await safe_send_message(bot, admin_id, text, reply_markup)


async def notify_user(
    user_id: int, text: str, reply_markup: Optional[InlineKeyboardMarkup] = None
) -> bool:
    return await safe_send_message(bot, user_id, text, reply_markup)


def get_event_user_id(event: Any) -> Optional[int]:
    user = getattr(event, "from_user", None)
    return getattr(user, "id", None)


async def get_user_language(user_id: int) -> str:
    if is_admin_user(user_id):
        return DEFAULT_LANGUAGE
    user = await db.get_user(user_id)
    lang = str(user.get("language", "") if user else "").strip().lower()
    return lang if lang in LANGUAGES else DEFAULT_LANGUAGE


async def get_lang(event: Any) -> str:
    user_id = get_event_user_id(event)
    if not user_id:
        return DEFAULT_LANGUAGE
    return await get_user_language(user_id)


async def prompt_language_selection(event):
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.language_prompt"),
        reply_markup=build_language_keyboard(),
        delete_origin=True,
    )


async def deny_admin_only(event):
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.admin_only_command"),
        reply_markup=main_menu_keyboard(),
        delete_origin=True,
    )


async def ensure_admin_access(event: Any, *, silent: bool = False) -> bool:
    user_id = get_event_user_id(event) or 0
    if is_admin_user(user_id):
        return True
    if not silent:
        await deny_admin_only(event)
    return False


async def ensure_custom_tariff_access(
    event, state: Optional[FSMContext] = None
) -> bool:
    if custom_tariff_enabled():
        return True
    if state:
        await state.clear()
    if isinstance(event, CallbackQuery):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_unavailable"),
            show_alert=True,
        )
    elif isinstance(event, Message):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_unavailable"),
            reply_markup=main_menu_keyboard(),
        )
    return False


async def show_custom_locations_picker(event, state: FSMContext) -> None:
    data = await state.get_data()
    selected = normalize_servers(data.get("custom_servers"))
    text = build_custom_locations_text(selected)
    markup = custom_locations_keyboard(selected)
    if isinstance(event, CallbackQuery) and event.message:
        try:
            await event.message.edit_text(
                text, reply_markup=markup, parse_mode=ParseMode.HTML
            )
            await event.answer()
            return
        except Exception:
            pass
    await smart_answer(event, text, reply_markup=markup, delete_origin=True)


async def show_custom_summary(event, state: FSMContext) -> None:
    data = await state.get_data()
    traffic = to_int(data.get("custom_traffic_gb"), 0)
    ip = to_int(data.get("custom_ip_limit"), 0)
    days = to_int(data.get("custom_duration_days"), 0)
    servers = normalize_servers(data.get("custom_servers"))
    if not is_valid_custom_limits(traffic, ip, days) or not is_valid_custom_servers(
        servers
    ):
        await state.clear()
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_build_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    base_total = int(round(calculate_custom_tariff_total(traffic, ip, days, servers)))
    trust = await db.get_trust_score(get_event_user_id(event) or 0)
    final_price, disc = apply_trust_discount(float(base_total), trust)
    final_price_int = max(0, int(round(final_price)))
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
            DEFAULT_LANGUAGE,
            "texts.custom_tariff_summary_discount",
            discount_percent=disc,
            final_price=final_price_int,
        )
    else:
        price_line = translate(
            DEFAULT_LANGUAGE,
            "texts.custom_tariff_summary_total",
            final_price=final_price_int,
        )

    uid = get_event_user_id(event) or 0
    next_step = translate(DEFAULT_LANGUAGE, "texts.custom_tariff_user_payment_hint")
    markup = kb(
        [
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.continue"),
                    "callback_data": f"custom:show_offer:{uid}",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
                    "callback_data": "cancel",
                }
            ],
        ]
    )

    text = translate(
        DEFAULT_LANGUAGE,
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
    event: CallbackQuery, *, continue_callback_data: str, lang: str = DEFAULT_LANGUAGE
) -> None:
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
    target = continue_callback_data.replace(
        "show_payment:", "choose_payment_method:"
    ).replace("custom:show_payment:", "custom:choose_payment_method:")
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


async def get_subscription_state(user_id: int) -> Dict[str, Any]:
    user = await db.get_user(user_id)
    if not user:
        return {"status": "no_user", "panel_available": True}
    sub_id = normalize_sub_id(user.get("vpn_url"))
    if not sub_id:
        return {"status": "no_subscription", "panel_available": True}
    base_email = build_base_email(user_id)
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
            except Exception:
                pass

    if max_expiry <= 0:
        expiry_str = str(user.get("expiry_sub_datatime") or "").strip()
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
                max_expiry = int(expiry_dt.timestamp() * 1000)
            except Exception:
                pass

    used_bytes = sum(
        max(0, to_int(c.get("up"), 0)) + max(0, to_int(c.get("down"), 0))
        for c in clients
    )
    traffic_gb = max(0.0, to_float(user.get("traffic_gb"), 0.0))
    extra_gb = max(0, to_int(user.get("extra_sub_gb"), 0))
    total_traffic_gb = traffic_gb + extra_gb
    traffic_bytes = int(total_traffic_gb * BYTES_IN_GB)
    traffic_exhausted = traffic_bytes > 0 and used_bytes >= traffic_bytes
    expired = bool(max_expiry and max_expiry <= now_ms)
    status = (
        "expired"
        if expired
        else ("traffic_exhausted" if traffic_exhausted else "active")
    )
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
    lang: str = DEFAULT_LANGUAGE,
) -> Dict[str, Any]:
    result = {
        "success": False,
        "trust_before": None,
        "trust_after": None,
        "trust_delta": 0,
    }

    if not validate_user_id(user_id):
        logger.warning(f"cleanup_subscription: некорректный user_id {user_id}")
        return result

    trust_before: Optional[int] = None
    trust_after: Optional[int] = None
    trust_delta = 0

    if not is_admin_user(user_id) and reason == "traffic_exhausted":
        trust_before = await db.get_trust_score(user_id)
        changed, before, after, delta = await apply_trust_score_delta(
            user_id, -TRUST_SCORE_PENALTY_TRAFFIC_EXHAUSTED
        )
        trust_after = after
        trust_delta = delta

    base_email = build_base_email(user_id)
    try:
        deleted = await panel.delete_client(base_email)
        if deleted:
            logger.info(f"🗑 Клиент {user_id} удалён с панели (reason={reason})")
        else:
            logger.warning(
                f"⚠️ Не удалось удалить клиента {user_id} с панели (reason={reason})"
            )
    except Exception as e:
        logger.error(f"cleanup_subscription: ошибка удаления с панели {user_id}: {e}")

    await db.remove_subscription(user_id)
    logger.info(f"🗑 Подписка {user_id} очищена из БД (reason={reason})")

    if notify_user_about_cleanup and not is_admin_user(user_id):
        try:
            user_lang = await get_user_language(user_id)
            cleanup_text = build_subscription_cleanup_message(
                reason,
                trust_before=trust_before,
                trust_after=trust_after,
                trust_delta=trust_delta,
                lang=user_lang,
            )
            await notify_user(
                user_id, cleanup_text, reply_markup=support_keyboard(include_main=True)
            )
        except Exception as e:
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
    lang: str = DEFAULT_LANGUAGE,
) -> Dict[str, Any]:
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


async def cleanup_admin_test_subscriptions() -> Dict[str, int]:
    result = {"removed": 0, "errors": 0}
    cutoff_time = int(time.time() * 1000) - (24 * 60 * 60 * 1000)  # 24 часа назад в мс

    for admin_id in ADMIN_USER_ID_SET:
        try:
            user_data = await db.get_user(admin_id)
            if not user_data:
                continue

            plan_text = str(user_data.get("plan_text", "") or "")
            if not any(
                suffix in plan_text.lower() for suffix in [" (тест)", " (test)"]
            ):
                continue

            vpn_url = user_data.get("vpn_url", "")
            if not vpn_url:
                continue

            base_email = build_base_email(admin_id)
            clients = await panel.find_clients_full_by_email(base_email)

            if not clients:
                await db.remove_subscription(admin_id)
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
                        await db.remove_subscription(admin_id)
                        result["removed"] += 1
                        logger.info(
                            f"Удалена тестовая подписка админа {admin_id} (истекла 24ч)"
                        )
                    else:
                        result["errors"] += 1
                        logger.warning(
                            f"Не удалось удалить тестовую подписку админа {admin_id}"
                        )
                    break
        except Exception as e:
            result["errors"] += 1
            logger.error(f"Ошибка при очистке тестовой подписки админа {admin_id}: {e}")

    return result


async def create_subscription(
    user_id: int,
    plan: Dict[str, Any],
    *,
    extra_days: int = 0,
    days_override: Optional[int] = None,
    plan_suffix: Optional[str] = None,
    earn_trust: bool = True,
    paid_amount: Optional[float] = None,
) -> Optional[str]:
    if not plan:
        logger.error(f"create_subscription: план не указан для user {user_id}")
        return None
    if not validate_user_id(user_id):
        logger.error(f"create_subscription: некорректный user_id {user_id}")
        return None
    await db.add_user(user_id)

    pending = await db.get_bonus_days_pending(user_id)
    days = (
        (
            days_override
            if days_override is not None
            else int(plan.get("duration_days", 30))
        )
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

    base_email = build_base_email(user_id)
    await panel.delete_client(base_email)

    client = await panel.create_client(
        email=base_email,
        limit_ip=int(plan.get("ip_limit", 0)),
        total_gb=int(plan.get("traffic_gb", 0)),
        days=days,
        servers=plan_servers,
        tg_id=user_id,
        inbound_ids=inbound_ids,
    )

    if not client:
        logger.warning(
            f"create_subscription: повторная попытка для user {user_id} (Duplicate email?)"
        )
        direct = await panel.get_client_by_email(base_email)
        if direct:
            direct_email = direct.get("email") or base_email
            del_url = (
                f"{panel.apibase}/panel/api/clients/del/"
                f"{panel._quote_path(direct_email)}?keepTraffic=0"
            )
            try:
                await panel._request_json_with_reauth(
                    "POST", del_url, headers=panel._headers()
                )
                logger.info(f"create_subscription: принудительно удалён {direct_email}")
            except Exception as e:
                logger.error(
                    f"create_subscription: ошибка принудительного удаления: {e}"
                )
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

    if not client:
        logger.error(
            f"create_subscription: не удалось создать клиента для user {user_id}"
        )
        return None

    sub_id = (
        normalize_sub_id(client.get("subId", f"user_{user_id}")) or f"user_{user_id}"
    )
    plan_name = plan.get("name", plan.get("id", ""))
    if plan_suffix:
        plan_name = f"{plan_name}{plan_suffix}"
    plan_id_for_db = plan.get("id", "")
    expiry_dt = datetime.now() + timedelta(days=days)
    expiry_sub_datatime = expiry_dt.isoformat()

    await db.set_subscription(
        user_id,
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
    plan: Dict[str, Any],
    *,
    extra_days: int = 0,
    earn_trust: bool = True,
    paid_amount: Optional[float] = None,
) -> Optional[str]:
    if not plan:
        return None
    await db.add_user(user_id)
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
    user_data = await db.get_user(user_id)
    if not user_data:
        return None
    base_email = build_base_email(user_id)
    clients = await panel.find_clients_full_by_email(base_email)
    if not clients:
        return None

    emails: List[str] = []
    seen: Set[str] = set()
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
                logger.warning(
                    f"renew_subscription: bulkAdjust adjusted=0, skipped={skipped}"
                )
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
                f"renew_subscription: update limitIp ошибка для {email}: "
                f"{upd_data.get('msg')}"
            )
        existing = [
            to_int(i, 0) for i in (client.get("inboundIds") or []) if to_int(i, 0) > 0
        ]
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
        datetime.fromtimestamp(max_expiry / 1000) if max_expiry > 0 else datetime.now()
    )
    expiry_sub_datatime = (max_expiry_dt + timedelta(days=days)).isoformat()

    await db.set_subscription(
        user_id,
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


async def is_active_subscription(
    user_id: int, *, notify_user_about_cleanup: bool = False
) -> bool:
    state = await ensure_subscription_state(
        user_id, notify_user_about_cleanup=notify_user_about_cleanup
    )
    return state.get("status") == "active" or (
        state.get("status") == "panel_unavailable" and state.get("sub_id")
    )


async def notify_expiring_subscription(
    user_id: int, state: Dict[str, Any], days: Optional[int] = None
) -> bool:
    if days is None:
        days = Config.EXPIRY_ALERT_DAYS

    user_data = await db.get_user(user_id)
    if not user_data:
        return False
    max_expiry = to_int(state.get("max_expiry"), 0)
    if max_expiry <= 0:
        expiry_str = str(user_data.get("expiry_sub_datatime") or "").strip()
        if expiry_str:
            try:
                expiry_dt = datetime.fromisoformat(expiry_str)
                max_expiry = int(expiry_dt.timestamp() * 1000)
            except Exception:
                pass
    if max_expiry <= 0:
        return False

    if state.get("status") != "active" or not is_expiring_soon(
        {"max_expiry": max_expiry}, days
    ):
        return False

    if not await should_send_expiry_alert(user_id):
        return False

    lang = await get_user_language(user_id)
    days_left = max(
        1, math.ceil((max_expiry - int(time.time() * 1000)) / (86400 * 1000))
    )
    text = translate(
        lang,
        "texts.subscription_expiring_soon",
        plan_text=user_data.get(
            "plan_text", translate(lang, "texts.current_plan_fallback")
        ),
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
    except Exception as e:
        logger.error(f"notify_expiring {user_id}: {e}")
        return False


async def reward_referrer(referrer_id: int, bonus_days: int) -> None:
    lang = await get_user_language(referrer_id)
    ref_user = await db.get_user(referrer_id)
    if not ref_user:
        return
    pending = await db.get_bonus_days_pending(referrer_id)
    total = bonus_days + pending
    base_email = build_base_email(referrer_id)
    has_active = await is_active_subscription(referrer_id)
    if has_active:
        if await panel.extend_client_expiry(base_email, total):
            if pending > 0:
                await db.clear_bonus_days_pending(referrer_id)
            await notify_user(
                referrer_id,
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
                DEFAULT_LANGUAGE,
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
                DEFAULT_LANGUAGE,
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
            referrer_id,
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
                DEFAULT_LANGUAGE,
                "texts.referral_bonus_create_failed_admin",
                referrer_id=referrer_id,
            )
        )


async def claim_pending_payment_or_alert(
    event: CallbackQuery, payment_id: str, action: str
) -> Optional[Dict[str, Any]]:
    moderator_id = get_event_user_id(event) or 0
    payment = await json_db.claim_pending_payment(payment_id, moderator_id, action)
    if not payment:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.payment_claim_unavailable"),
            show_alert=True,
        )
        return None
    return payment


async def finalize_claimed_payment_or_alert(
    event: CallbackQuery, payment_id: str, action: str, final_status: str
) -> bool:
    moderator_id = get_event_user_id(event) or 0
    success = await json_db.finalize_claimed_payment(
        payment_id, moderator_id, action, final_status
    )
    if not success:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.payment_finalize_changed"),
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


async def append_payment_decision_label(
    message: Optional[Message], status_label: str
) -> None:
    if not message:
        return
    current = message.text or ""
    new_text = f"{current}\n\n{status_label}" if current else status_label
    try:
        await message.edit_text(new_text, parse_mode="HTML")
    except Exception:
        pass


async def show_active_subscription_guard(event) -> None:
    lang = await get_lang(event)
    await smart_answer(
        event,
        translate(lang, "texts.active_subscription_guard"),
        reply_markup=active_subscription_keyboard(),
        delete_origin=True,
    )


async def get_visible_plans(user_id: int, *, for_admin: bool) -> List[Dict[str, Any]]:
    plans = get_all_active()
    if for_admin:
        return [p for p in plans if not is_trial_plan(p)]
    user = await db.get_user(user_id)
    trial_used = bool(user.get("trial_used")) if user else False
    has_sub = bool(user.get("has_subscription")) if user else False
    visible = []
    for p in plans:
        if is_trial_plan(p) and (trial_used or has_sub):
            continue
        visible.append(p)
    return visible


async def ban_middleware(handler: Callable, event: Any, data: Dict[str, Any]) -> Any:
    user_id = get_event_user_id(event) or 0
    try:
        lang = data.get("language", DEFAULT_LANGUAGE)
        user = await db.get_user(user_id)
        if user and user.get("banned"):
            reason = user.get("ban_reason", translate(lang, "texts.not_specified"))
            text = translate(lang, "texts.account_banned_message", reason=reason)
            markup = support_keyboard(include_main=True)
            if isinstance(event, Message):
                await event.answer(text, reply_markup=markup)
            elif isinstance(event, CallbackQuery):
                if event.message:
                    await event.message.answer(text, reply_markup=markup)
                await event.answer(
                    translate(lang, "texts.account_banned_alert"),
                    show_alert=True,
                )
            return None
        return await handler(event, data)
    except Exception as e:
        logger.error(f"Ошибка в ban_middleware для {user_id}: {e}")
        return await handler(event, data)


async def language_middleware(
    handler: Callable, event: Any, data: Dict[str, Any]
) -> Any:
    user_id = get_event_user_id(event) or 0
    try:
        lang = await db.get_user_language(user_id)
        if lang and lang in LANGUAGES:
            data["language"] = lang
        else:
            data["language"] = DEFAULT_LANGUAGE
    except Exception as e:
        logger.error(f"Ошибка в language_middleware для {user_id}: {e}")
        data["language"] = DEFAULT_LANGUAGE
    return await handler(event, data)


async def rate_limit_middleware(
    handler: Callable, event: Any, data: Dict[str, Any]
) -> Any:
    user = getattr(event, "from_user", None)
    if not user:
        return await handler(event, data)

    user_id = user.id
    if is_admin_user(user_id):
        return await handler(event, data)

    now = time.time()
    last_request = _user_request_times.get(user_id, 0)
    elapsed = now - last_request

    if elapsed < _RATE_LIMIT_COOLDOWN:
        remaining = _RATE_LIMIT_COOLDOWN - elapsed
        lang = data.get("language", DEFAULT_LANGUAGE)
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
        except Exception:
            pass
        return None

    _user_request_times[user_id] = now
    if len(_user_request_times) > 10000:
        cutoff = now - 60
        _user_request_times.clear()
    return await handler(event, data)


async def tech_work_middleware(
    handler: Callable, event: Any, data: Dict[str, Any]
) -> Any:
    user_id = get_event_user_id(event) or 0

    if not is_tech_work_mode():
        return await handler(event, data)

    if is_admin_user(user_id):
        return await handler(event, data)

    lang = data.get("language", DEFAULT_LANGUAGE)
    text = translate(lang, "texts.tech_work_in_progress")
    markup = support_keyboard(include_main=False)

    try:
        if isinstance(event, Message):
            await event.answer(text, reply_markup=markup)
        elif isinstance(event, CallbackQuery):
            if event.message:
                await event.message.answer(text, reply_markup=markup)
            await event.answer(text, show_alert=True)
    except Exception as e:
        logger.error(f"Ошибка при tech work: {e}")

    return None


router.message.middleware(ban_middleware)
router.callback_query.middleware(ban_middleware)
router.message.middleware(language_middleware)
router.callback_query.middleware(language_middleware)
router.message.middleware(rate_limit_middleware)
router.callback_query.middleware(rate_limit_middleware)
router.message.middleware(tech_work_middleware)
router.callback_query.middleware(tech_work_middleware)


# === Универсальный обработчик ошибок ===
@router.errors()
async def error_handler(event: Any, *args: Any, **kwargs: Any) -> bool:
    error = kwargs.get("error")
    if not error and args:
        error = args[0]
    if not error:
        return False

    if isinstance(error, TelegramBadRequest):
        error_msg = str(error).lower()
        if "blocked" in error_msg or "bot was blocked" in error_msg:
            return True
        if (
            "message not modified" in error_msg
            or "message to edit not found" in error_msg
        ):
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

    logger.error(
        f"Необработанная ошибка: {type(error).__name__}: {error}", exc_info=True
    )
    return False


# === Обработчики команд ===
@router.message(Command("start"))
@router.callback_query(F.data == "start")
@log_error
async def cmd_start(
    event: Union[Message, CallbackQuery], state: FSMContext, **kwargs: Any
) -> None:
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
        if isinstance(event, Message) and event.text:
            parts = event.text.strip().split(maxsplit=1)
            if len(parts) > 1:
                ref_code = parts[1]

        if not is_admin_user(user_id):
            try:
                await db.add_user(user_id)
                await db.ensure_ref_code(user_id)

                if ref_code:
                    ref_user = await db.get_user_by_ref_code(ref_code)
                    if ref_user and ref_user.get("user_id") != user_id:
                        await db.set_ref_by(user_id, ref_user.get("user_id"))
                        logger.info(
                            f"Пользователь {user_id} приглашен рефералом {ref_user.get('user_id')}"
                        )

                lang = await db.get_user_language(user_id)
                if not lang:
                    await prompt_language_selection(event)
                    return
            except Exception as e:
                logger.error(f"Ошибка инициализации пользователя {user_id}: {e}")
                await event.answer(
                    "Произошла ошибка при инициализации. Попробуйте позже."
                )
                return
        else:
            lang = DEFAULT_LANGUAGE

        total = await db.get_total_users()
        banned = await db.get_banned_users_count()
        active = len(await db.get_subscribed_user_ids())
        has_sub = False
        if not is_admin_user(user_id):
            try:
                has_sub = await is_active_subscription(
                    user_id, notify_user_about_cleanup=True
                )
            except Exception as e:
                logger.error(f"Ошибка проверки подписки {user_id}: {e}")

        if is_admin_user(user_id):
            text = translate(
                DEFAULT_LANGUAGE,
                "texts.admin_welcome",
                total_users=total,
                active_vpns=active,
                banned_users=banned,
            )
            keyboard = build_main_keyboard(True, False, DEFAULT_LANGUAGE)
        else:
            text = translate(
                lang, "texts.welcome", total_users=total, active_vpns=active
            )
            keyboard = build_main_keyboard(False, has_sub, lang)

        await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)

    except Exception as e:
        logger.error(f"Ошибка в cmd_start: {type(e).__name__}: {e}", exc_info=True)
        try:
            await event.answer("Произошла непредвиденная ошибка. Попробуйте позже.")
        except Exception:
            pass


@router.callback_query(F.data == "cancel")
async def cmd_cancel(event: CallbackQuery, state: FSMContext, **kwargs):
    await state.clear()
    await cmd_start(event, state)


@router.callback_query(F.data == "change_language")
async def cmd_change_language(event: CallbackQuery, state: FSMContext, **kwargs):
    if is_admin_user(get_event_user_id(event) or 0):
        await smart_answer(
            event,
            translate("ru", "texts.language_decorative_notice"),
            reply_markup=build_language_keyboard(),
            delete_origin=True,
        )
        return
    await prompt_language_selection(event)


@router.callback_query(F.data.startswith("lang:"))
async def cmd_set_language(event: CallbackQuery, state: FSMContext, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = event.data.split(":", 1)[1]  # type: ignore[union-attr]
    if is_admin_user(user_id):
        await event.answer(
            translate("ru", "texts.admin_language_notice"), show_alert=True
        )
        await cmd_start(event, state)
        return
    if lang not in LANGUAGES:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.language_not_supported"), show_alert=True
        )
        return
    await db.add_user(user_id)
    await db.set_user_language(user_id, lang)
    await event.answer(
        translate(
            lang, "texts.language_selected", language=get_language_display_name(lang)
        ),
        show_alert=True,
    )
    await cmd_start(event, state)


@router.callback_query(F.data == "buy")
async def cmd_buy(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    is_admin = is_admin_user(user_id)
    if not is_admin:
        await db.add_user(user_id)
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
                        "text": translate(DEFAULT_LANGUAGE, "buttons.pay_await"),
                        "callback_data": "pay_await",
                    }
                ]
            )
            for p in plans:
                keyboard.append(
                    [
                        {
                            "text": translate(
                                DEFAULT_LANGUAGE,
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

    text = (
        translate(lang, "texts.buy_unavailable")
        + "\n\n"
        + translate(lang, "buttons.support")
    )
    keyboard = [
        [
            {
                "text": translate(lang, "buttons.support"),
                "url": Config.SUPPORT_URL,
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


@router.callback_query(F.data == "buy:choose_custom")
async def cmd_buy_choose_custom(event: CallbackQuery, **kwargs):
    await event.answer()
    await cmd_custom_start(event, **kwargs)


@router.callback_query(F.data == "buy:choose_fixed")
async def cmd_buy_choose_fixed(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    is_admin = is_admin_user(user_id)
    if not is_admin:
        await db.add_user(user_id)
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
                    "text": translate(DEFAULT_LANGUAGE, "buttons.pay_await"),
                    "callback_data": "pay_await",
                }
            ]
        )
        for p in plans:
            keyboard.append(
                [
                    {
                        "text": translate(
                            DEFAULT_LANGUAGE,
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
    is_admin = is_admin_user(user_id)

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
    if val.lower() in ("отмена", "cancel", "/cancel"):
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
    if val.lower() in ("отмена", "cancel", "/cancel"):
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
    if val.lower() in ("отмена", "cancel", "/cancel"):
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
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    await event.answer(
        translate(lang, "texts.custom_tariff_select_locations"),
        reply_markup=cancel_only_keyboard(),
    )


@router.callback_query(
    CustomTariffState.waiting_for_locations, F.data.startswith("custom:loc:")
)
async def cmd_custom_toggle_location(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    code = normalize_server_code(event.data.rsplit(":", 1)[-1])  # type: ignore[union-attr]
    if not get_location_by_code(code):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_location_unavailable"),
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


@router.callback_query(
    CustomTariffState.waiting_for_locations, F.data == "custom:locations_done"
)
async def cmd_custom_locations_done(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    data = await state.get_data()
    selected = normalize_servers(data.get("custom_servers"))
    if not selected:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_choose_location_count"),
            show_alert=True,
        )
        return
    await show_custom_summary(event, state)


@router.message(CustomTariffState.waiting_for_confirm)
async def process_custom_confirm_text(event: Message, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    await event.answer(
        translate(DEFAULT_LANGUAGE, "texts.custom_tariff_use_buttons_or_cancel"),
        reply_markup=cancel_only_keyboard(),
    )


@router.callback_query(
    CustomTariffState.waiting_for_confirm, F.data.startswith("custom:show_offer:")
)
async def cmd_custom_show_offer(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
        )
        return
    await show_offer_agreement(
        event, continue_callback_data=f"custom:choose_payment_method:{uid}"
    )


@router.callback_query(
    CustomTariffState.waiting_for_confirm,
    F.data.startswith("custom:choose_payment_method:"),
)
async def cmd_custom_choose_payment_method(
    event: CallbackQuery, state: FSMContext, **kwargs
):
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
        )
        return

    if is_admin_user(uid):
        keyboard = [
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.payment_method_test"),
                    "callback_data": f"custom:confirm_payment:test:{uid}",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
                    "callback_data": "cancel",
                }
            ],
        ]
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.choose_payment_method"),
            reply_markup=kb(keyboard),
            delete_origin=True,
        )
        return

    methods = []
    if Config.YOOMONEY_WALLET:
        methods.append(
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.payment_method_yoomoney"),
                "callback_data": f"custom:pay_yoomoney:{uid}",
            }
        )
    if Config.PAYMENT_CARD_NUMBER:
        methods.append(
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.payment_method_p2p"),
                "callback_data": f"custom:pay_p2p:{uid}",
            }
        )

    if not methods:
        await state.clear()
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.buy_unavailable"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return

    keyboard = [methods] + [
        [
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ]
    ]
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.choose_payment_method"),
        reply_markup=kb(keyboard),
        delete_origin=True,
    )


@router.callback_query(
    CustomTariffState.waiting_for_confirm, F.data.startswith("custom:pay_yoomoney:")
)
async def cmd_custom_show_yoomoney(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
        )
        return
    data = await state.get_data()
    amount = to_int(data.get("custom_final_amount"), -1)
    plan_name = str(data.get("custom_plan_name") or " ").strip()
    if amount < 0:
        await state.clear()
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    order_id = f"{uid}_{uuid.uuid4().hex[:8]}"
    params = {
        "receiver": Config.YOOMONEY_WALLET,
        "quickpay-form": "shop",
        "targets": f"VPN_bot_for_3X-UI Custom #{order_id}",
        "paymentType": "AC",
        "sum": amount,
        "label": order_id,
    }

    pay_url = "https://yoomoney.ru/quickpay/confirm?" + urlencode(params)
    text = translate(
        DEFAULT_LANGUAGE,
        "texts.yoomoney_payment_details",
        plan_name=plan_name,
        amount=amount,
    )
    keyboard = [
        [
            {
                "text": f"🔗 {translate(DEFAULT_LANGUAGE, 'buttons.payment_method_yoomoney')}",
                "url": pay_url,
            }
        ],
        [
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.confirm_payment"),
                "callback_data": f"custom:confirm_payment:yoomoney:{uid}",
            }
        ],
        [
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(F.data.startswith("custom:confirm_payment:test:"))
async def cmd_custom_confirm_test(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 4:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        user_id = int(parts[3])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if user_id != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
        )
        return
    if not is_admin_user(user_id):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.admin_only_feature"),
            show_alert=True,
        )
        return
    data = await state.get_data()
    traffic = to_int(data.get("custom_traffic_gb"), 0)
    ip = to_int(data.get("custom_ip_limit"), 0)
    days = to_int(data.get("custom_duration_days"), 0)
    servers = normalize_servers(data.get("custom_servers"))
    plan_name = str(data.get("custom_plan_name") or " ").strip()
    if not is_valid_custom_limits(traffic, ip, days) or not is_valid_custom_servers(
        servers
    ):
        await state.clear()
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    if not plan_name:
        plan_name = build_custom_plan_name(traffic, ip, days, servers)
    custom_plan = build_custom_plan(
        traffic, ip, days, servers=servers, plan_name=plan_name
    )
    vpn_url = await create_subscription(
        user_id,
        custom_plan,
        plan_suffix=translate(DEFAULT_LANGUAGE, "texts.test_plan_suffix"),
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
        text = translate(DEFAULT_LANGUAGE, "texts.test_subscription_failed")
        setup_keyboard = main_menu_keyboard()
    await smart_answer(event, text, reply_markup=setup_keyboard, delete_origin=True)


@router.callback_query(
    CustomTariffState.waiting_for_confirm, F.data.startswith("custom:confirm_payment:")
)
async def cmd_custom_confirm_payment(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 4:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    method = parts[2]
    try:
        uid = int(parts[3])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if not is_admin_user(uid):
        st = await ensure_subscription_state(uid, notify_user_about_cleanup=True)
        if st.get("status") == "active" and not is_expiring_soon(
            st, Config.EXPIRY_ALERT_DAYS
        ):
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
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    if not plan_name:
        plan_name = build_custom_plan_name(traffic, ip, days, servers)

    if is_admin_user(uid):
        custom_plan = build_custom_plan(
            traffic, ip, days, servers=servers, plan_name=plan_name
        )
        vpn_url = await create_subscription(
            uid,
            custom_plan,
            plan_suffix=translate(DEFAULT_LANGUAGE, "texts.test_plan_suffix"),
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
            text = translate(DEFAULT_LANGUAGE, "texts.test_subscription_failed")
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
        "timestamp": datetime.now().isoformat(),
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
            translate(DEFAULT_LANGUAGE, "texts.payment_request_already_exists"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.custom_payment_request_received"),
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
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    await event.answer(
        translate(DEFAULT_LANGUAGE, "texts.custom_tariff_unknown_command"),
        show_alert=True,
    )


@router.callback_query(F.data.startswith("buy:"))
async def cmd_buy_plan(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    lang = await get_user_language(user_id)
    if not is_admin_user(user_id):
        st = await ensure_subscription_state(user_id, notify_user_about_cleanup=True)
        if st.get("status") == "active" and not is_expiring_soon(
            st, Config.EXPIRY_ALERT_DAYS
        ):
            await show_active_subscription_guard(event)
            return
    plan_id = event.data.split(":", 1)[1]  # type: ignore[union-attr]
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
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
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
    final_price_int = int(round(final_price))
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
async def cmd_test_plan(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    if not is_admin_user(user_id):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.admin_only_feature"), show_alert=True
        )
        return
    plan_id = event.data.split(":", 1)[1]  # type: ignore[union-attr]
    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    vpn_url = await create_subscription(
        user_id,
        plan,
        plan_suffix=translate(DEFAULT_LANGUAGE, "texts.test_plan_suffix"),
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
        text = translate(DEFAULT_LANGUAGE, "texts.test_subscription_failed")
        user_lang = DEFAULT_LANGUAGE
    setup_keyboard = build_setup_keyboard(user_lang)
    await smart_answer(event, text, reply_markup=setup_keyboard, delete_origin=True)


@router.callback_query(F.data.startswith("trial:"))
async def cmd_trial_plan(event: CallbackQuery, **kwargs):
    user_id = get_event_user_id(event) or 0
    if is_admin_user(user_id):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.trial_admin_not_allowed"),
            show_alert=True,
        )
        return
    if await is_active_subscription(user_id, notify_user_about_cleanup=True):
        await show_active_subscription_guard(event)
        return
    plan_id = event.data.split(":", 1)[1] if ":" in event.data else "trial"
    plan = get_by_id(plan_id)
    if not plan or not plan.get("active", True) or not is_trial_plan(plan):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.trial_plan_not_found"), show_alert=True
        )
        return
    await db.add_user(user_id)
    user = await db.get_user(user_id)
    if user.get("trial_used") or user.get("has_subscription"):
        text = translate(DEFAULT_LANGUAGE, "texts.trial_used_or_has_subscription")
        keyboard = kb(
            [
                [
                    {
                        "text": translate(DEFAULT_LANGUAGE, "buttons.my_subscription"),
                        "callback_data": "mysub",
                    }
                ],
                [
                    {
                        "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
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
        plan_suffix=translate(DEFAULT_LANGUAGE, "texts.trial_plan_suffix"),
        earn_trust=False,
    )
    if vpn_url:
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
        text = translate(DEFAULT_LANGUAGE, "texts.trial_subscription_failed")
        user_lang = DEFAULT_LANGUAGE
    setup_keyboard = build_setup_keyboard(user_lang)
    await smart_answer(event, text, reply_markup=setup_keyboard, delete_origin=True)


@router.callback_query(F.data.startswith("choose_payment_method:"))
async def cmd_choose_payment_method(event: CallbackQuery, **kwargs):
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
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
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
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
    final_price_int = int(round(final_price))
    order_id = f"{uid}_{uuid.uuid4().hex[:8]}"
    params = {
        "receiver": Config.YOOMONEY_WALLET,
        "quickpay-form": "shop",
        "targets": f"VPN_bot_for_3X-UI #{order_id}",
        "paymentType": "AC",
        "sum": final_price_int,
        "label": order_id,
    }

    pay_url = "https://yoomoney.ru/quickpay/confirm?" + urlencode(params)
    text = translate(
        lang,
        "texts.yoomoney_payment_details",
        plan_name=plan.get("name", plan_id),
        amount=final_price_int,
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
                "callback_data": f"confirm_payment:yoomoney:{plan_id}:{uid}",
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


@router.callback_query(F.data.startswith("pay_p2p:"))
async def cmd_show_p2p_payment(event: CallbackQuery, **kwargs):
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    plan_id = parts[1]
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
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
    final_price_int = int(round(final_price))

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


@router.callback_query(
    CustomTariffState.waiting_for_confirm, F.data.startswith("custom:pay_p2p:")
)
async def cmd_custom_show_p2p(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_custom_tariff_access(event, state):
        return
    parts = event.data.split(":")  # type: ignore[union-attr]
    if len(parts) < 3:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.request_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(parts[2])
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_user_identifier"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.wrong_user_error"), show_alert=True
        )
        return

    data = await state.get_data()
    amount = to_int(data.get("custom_final_amount"), -1)
    plan_name = str(data.get("custom_plan_name") or " ").strip()
    if amount < 0:
        await state.clear()
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.custom_tariff_payment_prepare_failed"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    text = translate(
        DEFAULT_LANGUAGE,
        "texts.p2p_payment_details",
        plan_name=plan_name,
        amount=amount,
        payment_card=Config.PAYMENT_CARD_NUMBER,
    )
    keyboard = [
        [
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.confirm_payment"),
                "callback_data": f"custom:confirm_payment:p2p:{uid}",
            }
        ],
        [
            {
                "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
                "callback_data": "cancel",
            }
        ],
    ]
    await smart_answer(event, text, reply_markup=kb(keyboard), delete_origin=True)


@router.callback_query(F.data.startswith("confirm_payment:"))
async def cmd_confirm_payment(event: CallbackQuery, **kwargs):
    parts = event.data.split(":")  # type: ignore[union-attr]
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
            translate(DEFAULT_LANGUAGE, "texts.payment_processing_error"),
            show_alert=True,
        )
        return
    try:
        uid = int(raw_uid)
    except ValueError:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.payment_processing_error"),
            show_alert=True,
        )
        return
    if uid != (get_event_user_id(event) or 0):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.payment_processing_error"),
            show_alert=True,
        )
        return

    lang = await get_user_language(uid)

    plan, error = get_purchasable_catalog_plan(plan_id)
    if not plan:
        await event.answer(error, show_alert=True)
        return
    st = await ensure_subscription_state(uid, notify_user_about_cleanup=True)
    if st.get("status") == "active" and not is_expiring_soon(
        st, Config.EXPIRY_ALERT_DAYS
    ):
        await show_active_subscription_guard(event)
        return
    price = to_float(plan.get("price_rub", 0), 0.0)
    trust = await db.get_trust_score(uid)
    amount = max(0, int(round(apply_trust_discount(price, trust)[0])))
    payment_id = f"pay_{uid}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    payment_data = {
        "payment_id": payment_id,
        "user_id": uid,
        "plan_id": plan_id,
        "plan_type": "catalog",
        "plan_name": plan.get("name", plan_id),
        "amount": amount,
        "timestamp": datetime.now().isoformat(),
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
    if is_admin_user(user_id):
        admin_sub_url = build_subscription_url("Admin")
        admin_json_url = build_json_subscription_url("Admin")
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

    state = await ensure_subscription_state(user_id, notify_user_about_cleanup=False)
    status = state.get("status")
    user_data = await db.get_user(user_id)

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
    sub_url = build_subscription_url(user_data.get("vpn_url"))
    json_sub_url = build_json_subscription_url(user_data.get("vpn_url"))
    trust = to_int(user_data.get("trust_score"), 0)
    disc = calculate_discount_percent(trust)

    if status == "active":
        used_gb = to_float(state.get("used_gb"), 0.0)
        max_expiry = to_int(state.get("max_expiry"), 0)
        if max_expiry <= 0:
            expiry_str = str(user_data.get("expiry_sub_datatime") or "").strip()
            if expiry_str:
                try:
                    expiry_dt = datetime.fromisoformat(expiry_str)
                    max_expiry = int(expiry_dt.timestamp() * 1000)
                except Exception:
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
            datetime.fromtimestamp(max_expiry / 1000).strftime("%d.%m.%Y %H:%M")
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
            text += f"\n\n🔗 <b>JSON URL:</b>\n<code>{json_sub_url}</code>"
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
            text += f"\n\n🔗 <b>JSON URL:</b>\n<code>{json_sub_url}</code>"

    rows: List[List[Dict[str, str]]] = [
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
    if is_admin_user(user_id):
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
    total = await db.count_referrals(user_id)
    paid = await db.count_referrals_paid(user_id)
    link = get_ref_link(ref_code)
    text = translate(
        lang,
        "texts.referral_info",
        link=link,
        total_refs=total,
        paid_refs=paid,
        bonus_days=Config.REF_BONUS_DAYS,
    )
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


@router.callback_query(F.data == "pay_await")
async def cmd_pay_await(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    payments = await json_db.read_all()
    pending = [p for p in payments if p.get("status") == "pending"]
    if not pending:
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.pay_await_empty"),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return
    await smart_answer(
        event, translate(DEFAULT_LANGUAGE, "texts.pay_await_title"), delete_origin=True
    )
    for p in pending:
        pid = str(p.get("payment_id", ""))
        if not pid:
            continue
        text = build_pending_payment_text(p)
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
    uid = to_int(payment.get("user_id"), 0)
    if uid <= 0:
        await rollback_claimed_payment(
            event,
            payment_id,
            "accept",
            error_message=translate(
                DEFAULT_LANGUAGE, "texts.invalid_payment_user_error"
            ),
        )
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.invalid_payment_user_alert"),
            show_alert=True,
        )
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
            or translate(DEFAULT_LANGUAGE, "texts.plan_not_found_during_payment"),
        )
        await event.answer(
            translate(
                DEFAULT_LANGUAGE,
                "texts.plan_not_found_alert",
                error=error or translate(DEFAULT_LANGUAGE, "texts.plan_not_found"),
            ),
            show_alert=True,
        )
        return
    plan_name = str(payment.get("plan_name") or "").strip() or plan.get(
        "name", plan_id or "custom"
    )
    paid_amount = to_float(payment.get("amount"), 0.0)
    user_data = await db.get_user(uid)
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
        finalized = await finalize_claimed_payment_or_alert(
            event, payment_id, "accept", "accepted"
        )
        if not finalized:
            return
        if not await verify_payment_final_status(payment_id, "accepted"):
            logger.error(f"Платеж {payment_id} не в 'accepted' после финализации")
            await event.answer(
                translate(DEFAULT_LANGUAGE, "texts.payment_processed_warning"),
                show_alert=True,
            )
            return
        bonus_text = (
            translate(
                DEFAULT_LANGUAGE,
                "texts.payment_bonus_line",
                bonus_days=format_duration(bonus_for_user, DEFAULT_LANGUAGE),
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
        except Exception:
            pass
        if ref_by and not ref_rewarded:
            fresh = await db.get_user(uid)
            if not fresh.get("ref_rewarded"):
                await reward_referrer(ref_by, Config.REF_BONUS_DAYS)
                await db.mark_ref_rewarded(uid)
        await event.answer(
            translate(
                DEFAULT_LANGUAGE, "texts.payment_accept_alert", payment_id=payment_id
            ),
            show_alert=True,
        )
        await append_payment_decision_label(
            event.message,
            translate(DEFAULT_LANGUAGE, "texts.payment_decision_accepted"),
        )
    else:
        await rollback_claimed_payment(
            event,
            payment_id,
            "accept",
            error_message=translate(
                DEFAULT_LANGUAGE, "texts.vpn_subscription_create_failed"
            ),
        )
        await event.answer(
            translate(
                DEFAULT_LANGUAGE,
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
    uid = to_int(payment.get("user_id"), 0)
    finalized = await finalize_claimed_payment_or_alert(
        event, payment_id, "reject", "rejected"
    )
    if not finalized:
        return
    if not await verify_payment_final_status(payment_id, "rejected"):
        logger.error(f"Платеж {payment_id} не в 'rejected' после финализации")
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.payment_processed_warning"),
            show_alert=True,
        )
    if uid > 0:
        changed, before, after, delta = await apply_trust_score_delta(
            uid, -TRUST_SCORE_PENALTY_PAYMENT_REJECTED
        )
        if changed:
            trust_line = build_trust_change_line(delta, before, after)
        else:
            trust_line = translate(DEFAULT_LANGUAGE, "texts.trust_change_short_none")
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
        except Exception:
            pass
    await event.answer(
        translate(
            DEFAULT_LANGUAGE, "texts.payment_reject_alert", payment_id=payment_id
        ),
        show_alert=True,
    )
    await append_payment_decision_label(
        event.message, translate(DEFAULT_LANGUAGE, "texts.payment_decision_rejected")
    )


# === Админ-команды ===
@router.callback_query(F.data == "ban")
async def cmd_ban(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.ban_user_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(BanUserState.waiting_for_user_id)


@router.message(BanUserState.waiting_for_user_id)
async def process_ban_user_id(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return
    uid = int(val)
    if is_admin_user(uid):
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.cannot_ban_admin"))
        return
    await state.update_data(user_id_to_ban=uid)
    await state.set_state(BanUserState.waiting_for_ban_reason)
    await event.answer(
        translate(DEFAULT_LANGUAGE, "texts.ban_reason_prompt", user_id=uid),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(BanUserState.waiting_for_ban_reason)
async def process_ban_reason(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    data = await state.get_data()
    uid = data.get("user_id_to_ban")
    reason = val
    success = await db.ban_user(uid, reason)
    await state.clear()
    if success:
        await cleanup_subscription(
            uid, f"banned: {reason}", notify_user_about_cleanup=False
        )
        text = translate(
            DEFAULT_LANGUAGE, "texts.user_banned", user_id=uid, reason=reason
        )
        user_lang = await get_user_language(uid)
        try:
            await notify_user(
                uid,
                translate(user_lang, "texts.user_ban_notification", reason=reason),
                reply_markup=support_keyboard(include_main=True),
            )
        except Exception:
            pass
    else:
        text = translate(DEFAULT_LANGUAGE, "texts.user_ban_error", user_id=uid)
    keyboard = kb(
        [
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.unban_user"),
                    "callback_data": "unban",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
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
        translate(DEFAULT_LANGUAGE, "texts.unban_user_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(UnbanUserState.waiting_for_user_id)


@router.message(UnbanUserState.waiting_for_user_id)
async def process_unban_user_id(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return
    uid = int(val)
    await state.update_data(user_id_to_unban=uid)
    await state.set_state(UnbanUserState.waiting_for_unban_reason)
    await event.answer(
        translate(DEFAULT_LANGUAGE, "texts.unban_reason_prompt", user_id=uid),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(UnbanUserState.waiting_for_unban_reason)
async def process_unban_reason(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    data = await state.get_data()
    uid = data.get("user_id_to_unban")
    reason = val
    success = await db.unban_user(uid)
    await state.clear()
    if success:
        text = translate(
            DEFAULT_LANGUAGE, "texts.user_unbanned", user_id=uid, reason=reason
        )
        user_lang = await get_user_language(uid)
        try:
            await notify_user(
                uid,
                translate(user_lang, "texts.user_unban_notification", reason=reason),
            )
        except Exception:
            pass
    else:
        text = translate(DEFAULT_LANGUAGE, "texts.user_unban_error", user_id=uid)
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


@router.callback_query(F.data == "broadcast")
async def cmd_broadcast(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    text = translate(DEFAULT_LANGUAGE, "texts.broadcast_prompt")
    keyboard = kb(
        [
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.broadcast_all_users"),
                    "callback_data": "broadcast_all",
                }
            ],
            [
                {
                    "text": translate(
                        DEFAULT_LANGUAGE, "buttons.broadcast_active_subscribers"
                    ),
                    "callback_data": "broadcast_active",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.cancel"),
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
        translate(DEFAULT_LANGUAGE, "texts.broadcast_target_all")
        if broadcast_type == "broadcast_all"
        else translate(DEFAULT_LANGUAGE, "texts.broadcast_target_active")
    )
    text = translate(
        DEFAULT_LANGUAGE, "texts.broadcast_message_prompt", type_text=type_text
    )
    await smart_answer(
        event, text, reply_markup=cancel_only_keyboard(), delete_origin=True
    )
    await state.set_state(BroadcastState.waiting_for_message)


@router.message(BroadcastState.waiting_for_message)
async def process_broadcast_message(event: Message, state: FSMContext, **kwargs):
    if not event.text or not isinstance(event.text, str):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.broadcast_message_must_be_text")
        )
        return
    msg = event.text.strip()
    if not msg:
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.broadcast_text_required"))
        return
    if msg.lower() in ("отмена", "cancel", "/cancel"):
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
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.broadcast_invalid_type"))
        await state.clear()
        return
    await state.clear()
    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await notify_user(uid, msg)
            sent += 1
        except Exception:
            failed += 1
        if sent % 10 == 0:
            await asyncio.sleep(1.0)
    type_text = (
        translate(DEFAULT_LANGUAGE, "texts.broadcast_target_all")
        if broadcast_type == "broadcast_all"
        else translate(DEFAULT_LANGUAGE, "texts.broadcast_target_active")
    )
    text = translate(
        DEFAULT_LANGUAGE,
        "texts.broadcast_completed",
        type_text=type_text,
        sent_count=sent,
        failed_count=failed,
    )
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


@router.callback_query(F.data == "debug_menu")
async def cmd_debug_menu(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    text = translate(DEFAULT_LANGUAGE, "texts.debug_menu_prompt")

    tech_work_text = (
        translate(DEFAULT_LANGUAGE, "buttons.disable_tech_work")
        if is_tech_work_mode()
        else translate(DEFAULT_LANGUAGE, "buttons.enable_tech_work")
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
                    "text": translate(DEFAULT_LANGUAGE, "buttons.ban_user"),
                    "callback_data": "ban",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.unban_user"),
                    "callback_data": "unban",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.trust_add"),
                    "callback_data": "debug_trust_add",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.trust_remove"),
                    "callback_data": "debug_trust_remove",
                }
            ],
            [
                {
                    "text": translate(
                        DEFAULT_LANGUAGE, "buttons.normalize_subscriptions"
                    ),
                    "callback_data": "debug_normalize",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.reset_all_trials"),
                    "callback_data": "debug_reset_trials",
                }
            ],
            [
                {
                    "text": translate(
                        DEFAULT_LANGUAGE, "buttons.delete_user_subscription"
                    ),
                    "callback_data": "debug_delete_sub",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.add_traffic"),
                    "callback_data": "debug_add_traffic",
                }
            ],
            [
                {
                    "text": translate(DEFAULT_LANGUAGE, "buttons.main"),
                    "callback_data": "start",
                }
            ],
        ]
    )
    await smart_answer(event, text, reply_markup=keyboard, delete_origin=True)


# === Режим тех. работ ===
class TechWorkCompensateState(StatesGroup):
    waiting_for_days = State()


@router.callback_query(F.data == "tech_work_toggle")
async def cmd_tech_work_toggle(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return

    global _is_tech_work_mode

    if not is_tech_work_mode():
        await set_tech_work_mode(True)

        notify_text = translate(DEFAULT_LANGUAGE, "texts.tech_work_started")
        notify_result = await notify_all_users(notify_text)
        logger.info(f"Уведомления отправлены: {notify_result}")

        disconnect_result = await disconnect_all_subscriptions("tech_work")
        logger.info(f"Подписки отключены: {disconnect_result}")

        text = translate(
            DEFAULT_LANGUAGE,
            "texts.tech_work_enabled",
            notified=notify_result["sent"],
            disconnected=disconnect_result["success"],
        )
        markup = kb(
            [
                [
                    {
                        "text": translate(DEFAULT_LANGUAGE, "buttons.return_to_debug"),
                        "callback_data": "debug_menu",
                    }
                ]
            ]
        )
    else:
        await set_tech_work_mode(False)

        recovery_text = translate(DEFAULT_LANGUAGE, "texts.tech_work_ended")
        notify_result = await notify_all_users(recovery_text)
        logger.info(f"Уведомления отправлены: {notify_result}")

        norm_task = asyncio.create_task(
            _run_normalization_with_notification(notify_result["sent"])
        )

        await state.update_data(prev_notify_count=notify_result["sent"])
        await state.set_state(TechWorkCompensateState.waiting_for_days)

        text = translate(
            DEFAULT_LANGUAGE,
            "texts.tech_work_disabled_normalizing",
            notified=notify_result["sent"],
        )
        markup = kb(
            [
                [
                    {
                        "text": translate(
                            DEFAULT_LANGUAGE, "buttons.give_compensation"
                        ),
                        "callback_data": "tech_work_compensate",
                    }
                ],
                [
                    {
                        "text": translate(DEFAULT_LANGUAGE, "buttons.skip"),
                        "callback_data": "debug_menu",
                    }
                ],
            ]
        )

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
            DEFAULT_LANGUAGE,
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
            DEFAULT_LANGUAGE,
            "texts.tech_work_normalization_incomplete",
            iterations=report["iterations"],
            total_changes=total_changes,
            errors=report["errors"],
        )
    await notify_admins(f"🔧 <b>Нормализация завершена:</b>\n\n{text}")


@router.callback_query(F.data == "tech_work_compensate")
async def cmd_tech_work_compensate(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return

    await state.set_state(TechWorkCompensateState.waiting_for_days)
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.tech_work_compensate_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.message(TechWorkCompensateState.waiting_for_days)
async def process_tech_work_compensate(event: Message, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event, silent=True):
        return

    val = event.text.strip() if event.text else ""
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return

    if not val.isdigit():
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.invalid_days_number"))  # type: ignore[union-attr]
        return

    days = int(val)
    if days <= 0:
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.compensate_positive_days")
        )
        return

    await state.clear()

    result = await compensate_all_users(days)

    text = translate(
        DEFAULT_LANGUAGE,
        "texts.tech_work_compensate_complete",
        days=days,
        processed=result["processed"],
        errors=result["errors"],
    )
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


@router.callback_query(F.data == "debug_reset_trials")
async def cmd_debug_reset_trials(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event):
        return
    success, errors = await db.reset_all_trials()
    text = translate(
        DEFAULT_LANGUAGE,
        "texts.trials_reset_result",
        success_count=success,
        error_count=errors,
    )
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


@router.callback_query(F.data == "debug_trust_add")
async def cmd_debug_trust_add(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await state.set_state(TrustScoreState.waiting_for_user_id)
    await state.update_data(action="add")
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.trust_add_prompt"),
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
        translate(DEFAULT_LANGUAGE, "texts.trust_remove_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )


@router.message(TrustScoreState.waiting_for_user_id)
async def process_trust_user_id(event: Message, state: FSMContext, **kwargs):
    val = event.text.strip() if event.text else ""
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return
    uid = int(val)
    await state.update_data(user_id_to_adjust=uid)
    data = await state.get_data()
    action = data.get("action")
    action_text = translate(DEFAULT_LANGUAGE, f"texts.trust_action_{action}")
    await event.answer(
        translate(
            DEFAULT_LANGUAGE,
            "texts.trust_amount_prompt",
            action_text=action_text,
            user_id=uid,
        ),
        reply_markup=cancel_only_keyboard(),
    )
    await state.set_state(TrustScoreState.waiting_for_amount)


@router.message(TrustScoreState.waiting_for_amount)
async def process_trust_amount(event: Message, state: FSMContext, **kwargs):
    val = event.text.strip() if event.text else ""
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.trust_amount_invalid"))
        return
    amount = int(val)
    if amount <= 0:
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.trust_amount_positive"))
        return
    if amount > TRUST_SCORE_MAX:
        await event.answer(
            translate(
                DEFAULT_LANGUAGE,
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
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.state_error"))
        return
    current = await db.get_trust_score(uid)
    future = current + (amount if action == "add" else -amount)
    if future < TRUST_SCORE_MIN:
        await event.answer(
            translate(
                DEFAULT_LANGUAGE,
                "texts.trust_operation_negative_balance",
                current_score=current,
            )
        )
        return
    if future > TRUST_SCORE_MAX:
        await event.answer(
            translate(
                DEFAULT_LANGUAGE,
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
        action_text = translate(
            DEFAULT_LANGUAGE, f"texts.trust_action_success_{action}"
        )
        text = translate(
            DEFAULT_LANGUAGE,
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
        admin_action = translate(DEFAULT_LANGUAGE, f"texts.trust_admin_action_{action}")
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
        except Exception:
            pass
    else:
        text = translate(DEFAULT_LANGUAGE, "texts.trust_update_failed")
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


@router.callback_query(F.data == "debug_normalize")
async def cmd_debug_normalize(event: CallbackQuery, **kwargs):
    if not await ensure_admin_access(event, silent=True):
        return
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.normalize_subscriptions_running"),
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
            DEFAULT_LANGUAGE,
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
            DEFAULT_LANGUAGE,
            "texts.normalize_all_incomplete",
            iterations=report["iterations"],
            total_changes=total_changes,
            errors=report["errors"],
        )

    if total_changes > 0:
        text += f"\n\n📊 <b>Всего изменений:</b> {total_changes}"
    if report["errors"] > 0:
        text += f"\n⚠️ <b>Ошибок:</b> {report['errors']}"

    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


# === Функция удаления подписки (debug) ===
@router.callback_query(F.data == "debug_delete_sub")
async def cmd_delete_subscription_start(
    event: CallbackQuery, state: FSMContext, **kwargs
):
    if not await ensure_admin_access(event):
        return
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.delete_subscription_confirm_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(DeleteSubscriptionState.waiting_for_user_id)


@router.message(DeleteSubscriptionState.waiting_for_user_id)
async def process_delete_sub_user_id(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.delete_subscription_input_invalid")
        )
        return
    uid = int(val)
    if is_admin_user(uid):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.delete_subscription_admin")
        )
        return
    await state.update_data(del_user_id=uid)
    await state.set_state(DeleteSubscriptionState.waiting_for_confirm)
    await event.answer(
        translate(DEFAULT_LANGUAGE, "texts.delete_subscription_confirm", user_id=uid),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(DeleteSubscriptionState.waiting_for_confirm)
async def process_delete_sub_confirm(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if val.upper() != "ДА":
        await event.answer("Введите 'ДА' для подтверждения или 'отмена' для отмены.")
        return
    data = await state.get_data()
    uid = data.get("del_user_id")
    await state.clear()
    result = await cleanup_subscription(
        uid, "admin_deleted", notify_user_about_cleanup=True
    )
    if result["success"]:
        text = translate(
            DEFAULT_LANGUAGE, "texts.delete_subscription_success", user_id=uid
        )
    else:
        text = translate(
            DEFAULT_LANGUAGE, "texts.delete_subscription_fail", user_id=uid
        )
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


# === Функция начисления доп. трафика (debug) ===
@router.callback_query(F.data == "debug_add_traffic")
async def cmd_add_traffic_start(event: CallbackQuery, state: FSMContext, **kwargs):
    if not await ensure_admin_access(event):
        return
    await smart_answer(
        event,
        translate(DEFAULT_LANGUAGE, "texts.add_traffic_user_prompt"),
        reply_markup=cancel_only_keyboard(),
        delete_origin=True,
    )
    await state.set_state(AddTrafficState.waiting_for_user_id)


@router.message(AddTrafficState.waiting_for_user_id)
async def process_add_traffic_user_id(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.invalid_user_id_number"))
        return
    uid = int(val)
    if is_admin_user(uid):
        await event.answer(
            translate(DEFAULT_LANGUAGE, "texts.add_traffic_admin_not_allowed")
        )
        return
    user = await db.get_user(uid)
    if not user or not normalize_sub_id(user.get("vpn_url")):
        await event.answer(
            translate(
                DEFAULT_LANGUAGE, "texts.add_traffic_no_subscription", user_id=uid
            )
        )
        return
    await state.update_data(traffic_user_id=uid)
    await state.set_state(AddTrafficState.waiting_for_gb)
    await event.answer(
        translate(DEFAULT_LANGUAGE, "texts.add_traffic_gb_prompt", user_id=uid),
        reply_markup=cancel_only_keyboard(),
    )


@router.message(AddTrafficState.waiting_for_gb)
async def process_add_traffic_gb(event: Message, state: FSMContext, **kwargs):
    val = (event.text or "").strip()
    if val.lower() in ("отмена", "cancel", "/cancel"):
        await state.clear()
        await cmd_start(event, state)
        return
    if not val.isdigit():
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.add_traffic_gb_invalid"))
        return
    gb = int(val)
    if gb <= 0:
        await event.answer(translate(DEFAULT_LANGUAGE, "texts.add_traffic_gb_positive"))
        return
    data = await state.get_data()
    uid: int = int(data.get("traffic_user_id", 0))
    await state.clear()

    if uid <= 0:
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.add_traffic_fail", user_id=uid),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return

    db_ok = await db.add_extra_traffic(uid, gb)
    if not db_ok:
        await smart_answer(
            event,
            translate(DEFAULT_LANGUAGE, "texts.add_traffic_fail", user_id=uid),
            reply_markup=main_menu_keyboard(),
            delete_origin=True,
        )
        return

    base_email = build_base_email(uid)
    panel_ok = await panel.add_client_traffic(base_email, gb)
    user_lang = await get_user_language(uid)
    try:
        await notify_user(
            uid,
            translate(user_lang, "texts.add_traffic_notification", gb=gb),
        )
    except Exception:
        pass

    if panel_ok:
        text = translate(
            DEFAULT_LANGUAGE, "texts.add_traffic_success", user_id=uid, gb=gb
        )
    else:
        text = translate(
            DEFAULT_LANGUAGE, "texts.add_traffic_partial", user_id=uid, gb=gb
        )
    await smart_answer(
        event, text, reply_markup=main_menu_keyboard(), delete_origin=True
    )


# === Фоновая задача нормализации ===
async def normalize_all_subscriptions_with_retry(
    max_iterations: int = 5, delay_between_iterations: int = 2
) -> Dict[str, Any]:
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
        iter_admins_skipped = 0

        inbounds_data = await panel.get_inbounds()
        raw_inbounds: List[Dict[str, Any]] = []
        if inbounds_data and inbounds_data.get("success"):
            obj = inbounds_data.get("obj", [])
            if isinstance(obj, dict):
                raw_inbounds = (
                    obj.get("items") or obj.get("data") or obj.get("inbounds") or []
                )
            elif isinstance(obj, list):
                raw_inbounds = obj
            else:
                raw_inbounds = []

        db_subs = await db.get_subscribed_user_ids()
        logger.info(
            f"Итерация {iteration + 1}/{max_iterations}: обрабатывается {len(db_subs)} подписок"
        )

        for uid in db_subs:
            if is_admin_user(uid):
                iter_admins_skipped += 1
                continue

            try:
                user = await db.get_user(uid)
                if not user:
                    logger.warning(f"⚠️ Пользователь {uid} не найден в БД")
                    continue

                base_email = build_base_email(uid)

                # === Шаг 1: Ищем план по subscription_id из БД ===
                subscription_id = str(user.get("subscription_id") or "").strip()
                plan = get_by_id(subscription_id) if subscription_id else None

                # Fallback: если subscription_id не найден, ищем по plan_text
                if not plan:
                    plan_text = user.get("plan_text", "")
                    base_plan_name = plan_text.split(" (", 1)[0].strip()
                    plan = get_by_name(base_plan_name) if base_plan_name else None

                # === Шаг 2: Если план найден - обновляем данные в БД ===
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
                        update_fields["plan_servers"] = json.dumps(
                            plan_servers, ensure_ascii=False
                        )
                        needs_update = True

                    if stored_ip != plan_ip:
                        logger.info(f"  🔄 Обновление IP: {stored_ip} -> {plan_ip}")
                        update_fields["ip_limit"] = plan_ip
                        needs_update = True

                    if abs(stored_gb - plan_gb) > 0.1:
                        logger.info(
                            f"  🔄 Обновление трафика: {stored_gb} -> {plan_gb}"
                        )
                        update_fields["traffic_gb"] = plan_gb
                        needs_update = True

                    if needs_update:
                        await db.update_user(uid, **update_fields)
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
                            datetime.now() + timedelta(days=30)
                        ).isoformat()
                        logger.info(
                            f"  🕐 Нет expiry_sub_datatime для {uid}, устанавливаем default: {default_expiry}"
                        )
                        await db.update_user(uid, expiry_sub_datatime=default_expiry)
                        stored_expiry = default_expiry
                        iter_changes += 1

                    update_fields = {}
                    stored_servers_json = (
                        json.dumps(stored_servers, ensure_ascii=False)
                        if stored_servers
                        else ""
                    )
                    if (
                        stored_servers_json
                        and user.get("plan_servers") != stored_servers_json
                    ):
                        update_fields["plan_servers"] = stored_servers_json
                    if stored_ip != to_int(user.get("ip_limit"), 0):
                        update_fields["ip_limit"] = stored_ip
                    if stored_gb != to_float(user.get("traffic_gb"), 0.0):
                        update_fields["traffic_gb"] = stored_gb

                    if update_fields:
                        await db.update_user(uid, **update_fields)
                        report["subscriptions_updated"] += 1
                        iter_changes += 1
                        logger.info(
                            f"  🔄 Обновлены stored данные для {uid}: {update_fields}"
                        )

                    plan_servers = stored_servers

                # === Шаг 3: Нормализуем на сервере ===
                target_inbound_ids: List[int] = []
                if plan_servers:
                    matched_inbounds = _filter_inbounds_for_servers_list(
                        raw_inbounds, plan_servers
                    )
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

                clients = await panel.find_clients_full_by_email(base_email)
                if clients:
                    for c in clients:
                        email = str(c.get("email") or "")
                        if not email:
                            continue

                        client = (
                            await panel.get_client_by_email(email)
                            or c.get("clientObj")
                            or c
                        )
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
                                logger.error(
                                    f"  ❌ Не удалось включить {email}: {data.get('msg')}"
                                )
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
                                det_ok = await panel.detach_client_from_inbounds(
                                    email, to_detach
                                )
                                if det_ok:
                                    logger.info(
                                        f"  📤 Открепление от inbound'ов: {to_detach}"
                                    )
                                    normalized = True
                                else:
                                    report["panel_errors"] += 1
                                    logger.error(
                                        f"  ❌ Не удалось открепить от inbound'ов {to_detach} для {email}"
                                    )
                            if to_attach:
                                att_ok = await panel.attach_client_to_inbounds(
                                    email, to_attach
                                )
                                if att_ok:
                                    logger.info(
                                        f"  📤 Подкрепление к inbound'ам: {to_attach}"
                                    )
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
                            logger.info(
                                f"  ✅ Inbound уже нормализован: {current_inbounds_ints}"
                            )

                        curr_ip = to_int(user.get("ip_limit"), 0)
                        curr_gb = to_float(user.get("traffic_gb"), 0.0)

                        fresh_user = await db.get_user(uid)
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

                # === Шаг 4: Обновляем expiry_sub_datatime из данных панели ===
                clients = await panel.find_clients_full_by_email(base_email)
                if clients:
                    expiry_times = [to_int(c.get("expiryTime"), 0) for c in clients]
                    max_expiry = max((x for x in expiry_times if x > 0), default=0)
                    if max_expiry > 0:
                        expiry_iso = datetime.fromtimestamp(
                            max_expiry / 1000
                        ).isoformat()
                        stored_expiry = str(
                            user.get("expiry_sub_datatime") or ""
                        ).strip()
                        if stored_expiry != expiry_iso:
                            await db.update_user(uid, expiry_sub_datatime=expiry_iso)
                            logger.info(
                                f"  🕐 Обновлён expiry_sub_datatime для {uid}: "
                                f"{stored_expiry or 'пусто'} -> {expiry_iso}"
                            )

                state = await get_subscription_state(uid)
                status = state.get("status")

                if status == "expired":
                    logger.info(f"  🗑 Удаляем expired подписку: {uid}")
                    res = await cleanup_subscription(
                        uid, "expired", notify_user_about_cleanup=True
                    )
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
                            remaining = (expiry_dt - datetime.now()).days
                            if remaining > 0:
                                restore_days = remaining
                        except Exception:
                            pass

                    inbound_ids = await panel.get_matching_inbound_ids(plan_servers)
                    if inbound_ids:
                        client = await panel.create_client(
                            email=build_base_email(uid),
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
                            logger.warning(
                                f"Не удалось восстановить подписку для user {uid}"
                            )
                    else:
                        report["errors"] += 1
                        logger.warning(f"Нет inbound'ов для восстановления user {uid}")

            except Exception as e:
                logger.error(
                    f"Ошибка нормализации {uid}: {type(e).__name__}: {e}", exc_info=True
                )
                report["errors"] += 1

        logger.info(
            f"Итерация {iteration + 1} завершена: {iter_changes} изменений, {iter_admins_skipped} админов пропущено"
        )

        if iter_changes == 0:
            report["all_normalized"] = True
            logger.info("✅ Изменений не найдено, нормализация завершена")
            break

        if iteration < max_iterations - 1:
            await asyncio.sleep(delay_between_iterations)

    logger.info(f"🔧 === КОНЕЦ НОРМАЛИЗАЦИИ: {report} ===")

    # === Удаление подписок админов ===
    logger.info("🧹 === Удаление подписок админов ===")
    admins_removed = 0
    for admin_id in Config.ADMIN_USER_IDS:
        try:
            admin_user = await db.get_user(admin_id)
            if not admin_user:
                continue

            vpn_url = str(admin_user.get("vpn_url") or "").strip()
            if vpn_url:
                base_email = build_base_email(admin_id)
                deleted = await panel.delete_client(base_email)
                if deleted:
                    logger.info(f"🗑 Удалён клиент админа {admin_id} с панели")
                else:
                    logger.warning(
                        f"⚠️ Не удалось удалить клиента админа {admin_id} с панели"
                    )

            await db.remove_subscription(admin_id)
            admins_removed += 1
            logger.info(f"🗑 Удалена подписка админа {admin_id} из БД")
        except Exception as e:
            logger.error(
                f"Ошибка удаления подписки админа {admin_id}: {type(e).__name__}: {e}"
            )

    report["admins_removed"] = admins_removed
    if admins_removed > 0:
        logger.info(f"🧹 Удалено {admins_removed} подписок админов")

    return report


# === Фоновые задачи ===
@log_error
async def cleanup_stale_payments() -> int:
    try:
        released = await json_db.release_stale_processing_payments()
        if released:
            logger.info(f"Освобождено {released} зависших платежей")
        return released
    except Exception as e:
        logger.error(f"Ошибка очистки платежей: {e}")
        return 0


@log_error
async def check_expired_subscriptions() -> None:
    await asyncio.sleep(10)
    while True:
        try:
            subscribed = await db.get_subscribed_user_ids()
            logger.info(f"Проверка {len(subscribed)} подписок")

            processed = 0
            errors = 0
            for uid in subscribed:
                if is_admin_user(uid):
                    continue
                try:
                    state = await ensure_subscription_state(
                        uid, notify_user_about_cleanup=True
                    )
                    if state.get("status") == "active":
                        await notify_expiring_subscription(
                            uid, state, days=Config.EXPIRY_ALERT_DAYS
                        )
                    processed += 1
                except Exception as e:
                    errors += 1
                    logger.error(
                        f"Ошибка проверки подписки {uid}: {type(e).__name__}: {e}"
                    )

            if errors > 0:
                logger.warning(
                    f"Проверка подписок завершена: {processed} обработано, {errors} ошибок"
                )
            else:
                logger.info(f"✅ Проверка подписок завершена: {processed} обработано")

            await asyncio.sleep(3600)
        except Exception as e:
            logger.error(
                f"Ошибка в check_expired_subscriptions: {type(e).__name__}: {e}"
            )
            await asyncio.sleep(60)


@log_error
async def cleanup_old_payments() -> None:
    while True:
        try:
            cutoff = datetime.now() - timedelta(days=30)

            def should_remove(p: Dict[str, Any]) -> bool:
                if p.get("status") not in ("accepted", "rejected"):
                    return False
                processed = p.get("processed_at")
                if not processed:
                    return False
                try:
                    return datetime.fromisoformat(processed) < cutoff
                except Exception:
                    return False

            before = len(await json_db.read_all())
            await json_db.remove(should_remove)
            after = len(await json_db.read_all())
            removed = before - after
            if removed > 0:
                logger.info(f"Очищено {removed} старых записей о платежах")
            else:
                logger.info("✅ Старые платежи не найдены")

            await asyncio.sleep(259200)  # 3 дня
        except Exception as e:
            logger.error(f"Ошибка очистки старых платежей: {type(e).__name__}: {e}")
            await asyncio.sleep(3600)


class SSLUpdateTask:
    @staticmethod
    @log_error
    async def run() -> None:
        loop = asyncio.get_running_loop()

        def _run_ssh_update() -> bool:
            if not Config.SSH_HOST or not Config.SSH_USER:
                logger.warning("SSL задача пропущена: SSH_HOST/SSH_USER не настроены")
                return False

            ssh: Optional[paramiko.SSHClient] = None
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

                last_error: Optional[Exception] = None
                for attempt in range(3):
                    try:
                        ssh = _connect()
                        break
                    except Exception as exc:
                        last_error = exc
                        if attempt < 2:
                            time.sleep(1.0 * (2.0**attempt))
                        else:
                            raise
                if ssh is None:
                    if last_error is not None:
                        raise last_error
                    raise ConfigError("Не удалось подключиться по SSH")

                shell = ssh.invoke_shell()
                time.sleep(5)
                commands = [
                    "service nginx stop",
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
                    "service nginx start",
                ]
                for cmd in commands:
                    shell.send(cmd + "\n")
                    time.sleep(15)
                time.sleep(10)
                shell.close()
                shell = None
                ssh.close()
                ssh = None  # type: ignore[assignment]
                return True

            except Exception as e:
                logger.error(f"SSL SSH ошибка: {e}")
                raise
            finally:
                try:
                    if shell is not None:
                        shell.close()
                except Exception:
                    pass
                try:
                    if ssh is not None:
                        ssh.close()
                except Exception:
                    pass

        while True:
            try:
                await asyncio.sleep(432000)
                updated = await loop.run_in_executor(None, _run_ssh_update)
                if updated:
                    await notify_admins("🔄 <b>SSL-сертификат обновлён</b>")
                    logger.info("SSL-сертификат успешно обновлен")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"SSL задача: {e}")
                await notify_admins(f"❌ <b>Ошибка обновления SSL</b>\n\n{e}")
                await asyncio.sleep(3600)


@log_error
async def cleanup_admin_test_subscriptions_periodic() -> None:
    while True:
        try:
            await asyncio.sleep(3600)
            result = await cleanup_admin_test_subscriptions()
            if result["removed"] > 0:
                logger.info(f"🧹 Очищено {result['removed']} тестовых подписок админов")
            if result["errors"] > 0:
                logger.warning(f"⚠️ Ошибки при очистке тестовых: {result['errors']}")
            else:
                logger.info("✅ Тестовые подписки админов в порядке")
        except Exception as e:
            logger.error(
                f"Ошибка задачи очистки тестовых подписок: {type(e).__name__}: {e}"
            )
            await asyncio.sleep(3600)


# === Запуск ===
async def main() -> None:
    global BOT_USERNAME

    background_tasks: List[asyncio.Task] = []
    loop = asyncio.get_running_loop()
    shutdown_event = asyncio.Event()

    async def stop_polling_safely() -> None:
        try:
            await dp.stop_polling()
        except RuntimeError:
            pass
        except Exception as e:
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

        try:
            load_tariffs()
            logger.info("Тарифы загружены успешно")
        except Exception as e:
            logger.critical(f"Не удалось загрузить тарифы: {type(e).__name__}: {e}")
            sys.exit(1)

        if not is_valid_bot_token_format(Config.BOT_TOKEN):
            logger.critical("BOT_TOKEN не настроен или некорректен")
            sys.exit(1)

        logger.info("Формат BOT_TOKEN корректен")

        try:
            await db.connect()
            logger.info("База данных подключена")

            try:
                await panel.start()
                logger.info("PanelAPI запущен")
            except Exception as e:
                logger.warning(f"PanelAPI не удалось запустить: {e}")

            try:
                me = await bot.get_me()
                BOT_USERNAME = me.username or ""
                logger.info(f"Бот авторизован как @{BOT_USERNAME}")
            except Exception as e:
                logger.warning(f"Не удалось получить информацию о боте: {e}")
                BOT_USERNAME = ""

            for admin_id in Config.ADMIN_USER_IDS:
                try:
                    await safe_send_message(
                        bot, admin_id, translate(DEFAULT_LANGUAGE, "texts.bot_started")
                    )
                    logger.info(f"Уведомление администратора {admin_id} отправлено")
                except Exception:
                    pass

            try:
                background_tasks.append(
                    asyncio.create_task(check_expired_subscriptions())
                )
                background_tasks.append(asyncio.create_task(cleanup_old_payments()))
                background_tasks.append(asyncio.create_task(SSLUpdateTask.run()))
                background_tasks.append(
                    asyncio.create_task(cleanup_admin_test_subscriptions_periodic())
                )
                logger.info("Фоновые задачи запущены")
            except Exception as e:
                logger.warning(f"Не удалось запустить часть фоновых задач: {e}")

            logger.info("Запуск polling...")
            await dp.start_polling(bot)
            logger.info("Polling завершен")

        except Exception as e:
            logger.critical(f"Критическая ошибка при запуске: {type(e).__name__}: {e}")
            raise
        except (asyncio.CancelledError, KeyboardInterrupt):
            logger.info("Остановка бота")
        finally:
            logger.info("🛑 Запуск graceful shutdown...")

            if is_tech_work_mode():
                logger.info("Выключение режима тех. работ при shutdown")
                await set_tech_work_mode(False)

            logger.info("Остановка фоновых задач...")
            for task in background_tasks:
                if not task.done():
                    task.cancel()
            if background_tasks:
                await asyncio.gather(*background_tasks, return_exceptions=True)

            try:
                for admin_id in Config.ADMIN_USER_IDS:
                    try:
                        await safe_send_message(
                            bot,
                            admin_id,
                            translate(DEFAULT_LANGUAGE, "texts.bot_stopped"),
                        )
                    except Exception:
                        pass
            except Exception:
                pass

            await cleanup_stale_payments()

            await panel.close()
            await db.close()
            if bot.session:
                await bot.session.close()

            logger.info("✅ Бот остановлен")

    except ConfigError as e:
        logger.critical(f"Ошибка конфигурации: {e}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Неожиданная ошибка: {type(e).__name__}: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Принудительная остановка")
    except Exception as e:
        logger.critical(f"Фатальная ошибка: {e}", exc_info=True)
        sys.exit(1)
