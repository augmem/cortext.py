from __future__ import annotations

import ctypes
import json
import os
from array import array
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Any, Iterable

from .assets import (
    PACKAGE_DIR as _PACKAGE_DIR,
    SUPPORTED_NATIVE_TARGETS as _SUPPORTED_NATIVE_TARGETS,
    assets_root as _assets_root,
    host_library_path as _host_library_path,
    package_assets_ready as _package_assets_ready,
    platform_tag as _platform_tag,
)
from .model import (
    clear_materialize_cache,
    materialize_model,
    resolve_aist_model,
)
from .release import DEFAULT_RELEASE_TAG

__all__ = [
    "Config",
    "Cortext",
    "CortextError",
    "DBProvider",
    "Media",
    "ObjectStoreProvider",
    "Retention",
    "DEFAULT_RELEASE_TAG",
    "clear_materialize_cache",
    "last_error",
    "load_library",
    "materialize_model",
    "package_assets_ready",
    "resolve_aist_model",
    "version",
]

package_assets_ready = _package_assets_ready


class CortextError(RuntimeError):
    pass


class Retention(IntEnum):
    """Ingress retention policy (matches cortext::Retention / C API).

    Natural (default when omitted): boundary and write algorithms decide.
    Durable: explicit turn commit.
    Boundary: explicit turn edge only.
    Ephemeral: never store; explicit retrieval turn edge.
    """

    NATURAL = 0
    DURABLE = 1
    BOUNDARY = 2
    EPHEMERAL = 3


@dataclass(slots=True)
class Config:
    focus: float = 0.5
    sensitivity: float = 0.5
    stability: float = 0.5
    affect_interrupt: bool = True
    affect_retrieval: bool = True
    reinforcement_enabled: bool = True
    procedural_enabled: bool = True
    sequential_edges_enabled: bool = True
    signal_filter_audio_enabled: bool = True
    signal_filter_image_enabled: bool = True
    signal_filter_text_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Media:
    data: bytes | bytearray | memoryview
    mimetype: str


class _NativeConfig(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_size_t),
        ("focus", ctypes.c_double),
        ("sensitivity", ctypes.c_double),
        ("stability", ctypes.c_double),
        ("affect_interrupt", ctypes.c_int),
        ("affect_retrieval", ctypes.c_int),
        ("reinforcement_enabled", ctypes.c_int),
        ("procedural_enabled", ctypes.c_int),
        ("sequential_edges_enabled", ctypes.c_int),
        ("signal_filter_audio_enabled", ctypes.c_int),
        ("signal_filter_image_enabled", ctypes.c_int),
        ("signal_filter_text_enabled", ctypes.c_int),
    ]


class _NativeMedia(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("size", ctypes.c_size_t),
        ("mimetype", ctypes.c_char_p),
    ]


class _NativeProcessJsonOptions(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_size_t),
        ("include_embedding", ctypes.c_int),
        ("retention", ctypes.c_int),
        ("reserved", ctypes.c_int),
    ]


CORTEXT_DB_VALUE_NULL = 0
CORTEXT_DB_VALUE_INT64 = 1
CORTEXT_DB_VALUE_DOUBLE = 2
CORTEXT_DB_VALUE_TEXT = 3
CORTEXT_DB_VALUE_BLOB = 4


class _DBValue(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("int64_value", ctypes.c_int64),
        ("double_value", ctypes.c_double),
        ("text_value", ctypes.c_char_p),
        ("blob_data", ctypes.POINTER(ctypes.c_uint8)),
        ("blob_size", ctypes.c_size_t),
    ]


class _DBCell(ctypes.Structure):
    pass


class _DBRow(ctypes.Structure):
    pass


class _DBResult(ctypes.Structure):
    pass


_DBCell._fields_ = [("column_name", ctypes.c_char_p), ("value", _DBValue)]
_DBRow._fields_ = [
    ("cells", ctypes.POINTER(_DBCell)),
    ("cell_count", ctypes.c_size_t),
]
_DBResult._fields_ = [
    ("rows", ctypes.POINTER(_DBRow)),
    ("row_count", ctypes.c_size_t),
]


_ExecuteCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_char_p,
    ctypes.POINTER(_DBValue),
    ctypes.c_size_t,
    ctypes.POINTER(_DBResult),
    ctypes.POINTER(ctypes.c_char_p),
)
_BeginCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_char_p),
)
_TransactionCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_char_p),
)
_ReleaseTransactionCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
)
_ReleaseResultCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.POINTER(_DBResult),
)
_ObjectBeginCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(ctypes.c_char_p),
)
_ObjectPutCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_char_p),
)
_ObjectGetCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.POINTER(ctypes.c_uint8)),
    ctypes.POINTER(ctypes.c_size_t),
    ctypes.POINTER(ctypes.c_char_p),
)
_ObjectExistsCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_char_p),
)
_ObjectDeleteCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
    ctypes.POINTER(ctypes.c_int),
    ctypes.POINTER(ctypes.c_char_p),
)
_ObjectTransactionCallback = ctypes.CFUNCTYPE(
    ctypes.c_int,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_char_p),
)
_ObjectReleaseTransactionCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.c_void_p,
)
_ObjectReleaseBlobCallback = ctypes.CFUNCTYPE(
    None,
    ctypes.c_void_p,
    ctypes.POINTER(ctypes.c_uint8),
    ctypes.c_size_t,
)


class _DBCallbacks(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_size_t),
        ("execute", _ExecuteCallback),
        ("begin", _BeginCallback),
        ("commit", _TransactionCallback),
        ("rollback", _TransactionCallback),
        ("release_transaction", _ReleaseTransactionCallback),
        ("release_result", _ReleaseResultCallback),
    ]


class _ObjectCallbacks(ctypes.Structure):
    _fields_ = [
        ("struct_size", ctypes.c_size_t),
        ("begin", _ObjectBeginCallback),
        ("put", _ObjectPutCallback),
        ("get", _ObjectGetCallback),
        ("exists", _ObjectExistsCallback),
        ("delete_object", _ObjectDeleteCallback),
        ("commit", _ObjectTransactionCallback),
        ("rollback", _ObjectTransactionCallback),
        ("release_transaction", _ObjectReleaseTransactionCallback),
        ("release_blob", _ObjectReleaseBlobCallback),
    ]


class DBProvider:
    def execute(self, query: str, params: list[Any], transaction: Any | None) -> list[dict[str, Any]]:
        raise NotImplementedError

    def begin(self, parent_transaction: Any | None) -> Any:
        raise NotImplementedError

    def commit(self, transaction: Any) -> None:
        raise NotImplementedError

    def rollback(self, transaction: Any) -> None:
        raise NotImplementedError

    def release_transaction(self, transaction: Any) -> None:
        pass


class ObjectStoreProvider:
    def begin(self, parent_transaction: Any | None) -> Any:
        raise NotImplementedError

    def put(self, object_id: bytes, data: bytes, transaction: Any) -> None:
        raise NotImplementedError

    def get(self, object_id: bytes, transaction: Any) -> bytes | None:
        raise NotImplementedError

    def exists(self, object_id: bytes, transaction: Any) -> bool:
        raise NotImplementedError

    def delete(self, object_id: bytes, transaction: Any) -> bool:
        raise NotImplementedError

    def commit(self, transaction: Any) -> None:
        raise NotImplementedError

    def rollback(self, transaction: Any) -> None:
        raise NotImplementedError

    def release_transaction(self, transaction: Any) -> None:
        pass


_DLL_DIRECTORY_HANDLES: list[Any] = []


def _default_aist_model_path(db_path: str = ":memory:") -> str | None:
    """Resolve model from release assets only — never HF / sibling search."""
    return resolve_aist_model(db_path)


def _load_cdll(path: Path | str) -> ctypes.CDLL:
    library_path = Path(path) if not isinstance(path, str) else Path(path)
    if os.name == "nt" and library_path.parent and hasattr(os, "add_dll_directory"):
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(os.fspath(library_path.parent)))
    return ctypes.CDLL(os.fspath(path))


def _configure_library(lib: ctypes.CDLL) -> ctypes.CDLL:
    lib.cortext_config_init.argtypes = [ctypes.POINTER(_NativeConfig)]
    lib.cortext_config_init.restype = None

    lib.cortext_create_with_config.argtypes = [
        ctypes.POINTER(_NativeConfig),
        ctypes.c_char_p,
    ]
    lib.cortext_create_with_config.restype = ctypes.c_void_p

    lib.cortext_create_with_store_callbacks.argtypes = [
        ctypes.POINTER(_NativeConfig),
        ctypes.POINTER(_DBCallbacks),
        ctypes.c_void_p,
    ]
    lib.cortext_create_with_store_callbacks.restype = ctypes.c_void_p

    lib.cortext_create_with_store_and_object_callbacks.argtypes = [
        ctypes.POINTER(_NativeConfig),
        ctypes.POINTER(_DBCallbacks),
        ctypes.c_void_p,
        ctypes.POINTER(_ObjectCallbacks),
        ctypes.c_void_p,
    ]
    lib.cortext_create_with_store_and_object_callbacks.restype = ctypes.c_void_p

    lib.cortext_create_with_config_and_object_callbacks.argtypes = [
        ctypes.POINTER(_NativeConfig),
        ctypes.c_char_p,
        ctypes.POINTER(_ObjectCallbacks),
        ctypes.c_void_p,
    ]
    lib.cortext_create_with_config_and_object_callbacks.restype = ctypes.c_void_p

    lib.cortext_free.argtypes = [ctypes.c_void_p]
    lib.cortext_free.restype = None

    lib.cortext_process_text_json.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    lib.cortext_process_text_json.restype = ctypes.c_void_p

    lib.cortext_process_text_json_with_options.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.POINTER(_NativeProcessJsonOptions),
    ]
    lib.cortext_process_text_json_with_options.restype = ctypes.c_void_p

    lib.cortext_process_audio_json.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.c_char_p,
    ]
    lib.cortext_process_audio_json.restype = ctypes.c_void_p

    lib.cortext_process_audio_json_with_options.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.POINTER(_NativeProcessJsonOptions),
    ]
    lib.cortext_process_audio_json_with_options.restype = ctypes.c_void_p

    text_media_json = getattr(lib, "cortext_process_text_with_media_json", None)
    text_media_json_with_options = getattr(
        lib, "cortext_process_text_with_media_json_with_options", None
    )
    lib._cortext_text_media_json_available = text_media_json_with_options is not None
    if text_media_json is not None:
        text_media_json.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(_NativeMedia),
        ]
        text_media_json.restype = ctypes.c_void_p

    if text_media_json_with_options is not None:
        text_media_json_with_options.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.POINTER(_NativeMedia),
            ctypes.POINTER(_NativeProcessJsonOptions),
        ]
        text_media_json_with_options.restype = ctypes.c_void_p

    lib.cortext_process_audio_with_media_json.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.POINTER(_NativeMedia),
    ]
    lib.cortext_process_audio_with_media_json.restype = ctypes.c_void_p

    lib.cortext_process_audio_with_media_json_with_options.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
        ctypes.c_char_p,
        ctypes.POINTER(_NativeMedia),
        ctypes.POINTER(_NativeProcessJsonOptions),
    ]
    lib.cortext_process_audio_with_media_json_with_options.restype = ctypes.c_void_p

    lib.cortext_process_image_json.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
    ]
    lib.cortext_process_image_json.restype = ctypes.c_void_p

    lib.cortext_process_image_json_with_options.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(_NativeProcessJsonOptions),
    ]
    lib.cortext_process_image_json_with_options.restype = ctypes.c_void_p

    lib.cortext_process_image_with_media_json.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(_NativeMedia),
    ]
    lib.cortext_process_image_with_media_json.restype = ctypes.c_void_p

    lib.cortext_process_image_with_media_json_with_options.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.POINTER(_NativeMedia),
        ctypes.POINTER(_NativeProcessJsonOptions),
    ]
    lib.cortext_process_image_with_media_json_with_options.restype = ctypes.c_void_p

    lib.cortext_embed_text_json.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
    ]
    lib.cortext_embed_text_json.restype = ctypes.c_void_p

    lib.cortext_embed_audio_json.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_size_t,
    ]
    lib.cortext_embed_audio_json.restype = ctypes.c_void_p

    lib.cortext_embed_image_json.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint8),
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
    ]
    lib.cortext_embed_image_json.restype = ctypes.c_void_p

    lib.cortext_consolidate_json.argtypes = [ctypes.c_void_p]
    lib.cortext_consolidate_json.restype = ctypes.c_void_p

    lib.cortext_flush.argtypes = [ctypes.c_void_p]
    lib.cortext_flush.restype = ctypes.c_int

    lib.cortext_reset.argtypes = [ctypes.c_void_p]
    lib.cortext_reset.restype = ctypes.c_int

    lib.cortext_version.argtypes = []
    lib.cortext_version.restype = ctypes.c_char_p

    lib.cortext_last_error.argtypes = []
    lib.cortext_last_error.restype = ctypes.c_char_p

    lib.cortext_string_free.argtypes = [ctypes.c_void_p]
    lib.cortext_string_free.restype = None
    return lib


def load_library(path: str | os.PathLike[str] | None = None) -> ctypes.CDLL:
    """Load the host Cortext shared library shipped with this package.

    1. Explicit ``path`` argument
    2. ``CORTEXT_LIBRARY_PATH``
    3. Host native under ``CORTEXT_ASSETS_DIR`` or the package ``native/`` tree

    Turnkey GitHub Release installs include all six platform natives + model
    chunks. The slim PyPI install includes all six thin natives and downloads
    the verified model only when an engine is first created.
    """
    if path is not None:
        lib_path = Path(path)
        if not lib_path.is_file():
            raise CortextError(f"CORTEXT library path does not exist: {lib_path}")
        return _configure_library(_load_cdll(lib_path))

    env_path = os.environ.get("CORTEXT_LIBRARY_PATH")
    if env_path:
        lib_path = Path(env_path).expanduser()
        if not lib_path.is_file():
            raise CortextError(f"CORTEXT_LIBRARY_PATH does not exist: {lib_path}")
        return _configure_library(_load_cdll(lib_path))

    try:
        root = _assets_root()
        lib_path = _host_library_path(root)
    except Exception as exc:
        supported = ", ".join(sorted(_SUPPORTED_NATIVE_TARGETS))
        raise CortextError(
            "Could not load shipped Cortext native library. "
            f"Platform {_platform_tag()}; shipped tags: {supported}. "
            f"Expected host library under {_PACKAGE_DIR / 'native'}. "
            "Reinstall the package with package data, run "
            f"`python scripts/vendor_release_assets.py --from-release {DEFAULT_RELEASE_TAG}`, "
            "or set CORTEXT_LIBRARY_PATH / CORTEXT_ASSETS_DIR. "
            f"Detail: {exc}"
        ) from exc

    if not lib_path.is_file():
        raise CortextError(
            f"shipped assets missing host library at {lib_path} "
            f"(platform {_platform_tag()})"
        )
    try:
        return _configure_library(_load_cdll(lib_path))
    except OSError as exc:
        raise CortextError(f"failed to load {lib_path}: {exc}") from exc


_LIB: ctypes.CDLL | None = None


def _lib() -> ctypes.CDLL:
    global _LIB
    if _LIB is None:
        _LIB = load_library()
    return _LIB


def last_error() -> str:
    raw = _lib().cortext_last_error()
    return raw.decode("utf-8") if raw else ""


def version() -> str:
    raw = _lib().cortext_version()
    return raw.decode("utf-8") if raw else ""


def _raise_last_error(prefix: str) -> None:
    detail = last_error()
    raise CortextError(f"{prefix}: {detail}" if detail else prefix)


def _native_media(
    media: Media | bytes | bytearray | memoryview | None,
    mimetype: str | None,
) -> tuple[_NativeMedia, Any, bytes | None]:
    if media is None:
        return _NativeMedia(None, 0, None), None, None
    if isinstance(media, Media):
        if mimetype is None:
            mimetype = media.mimetype
        media = media.data
    blob = bytes(media)
    if not blob:
        return _NativeMedia(None, 0, None), None, None
    if not mimetype:
        raise ValueError("media_mimetype is required when media bytes are provided")
    raw = (ctypes.c_uint8 * len(blob)).from_buffer_copy(blob)
    mimetype_bytes = mimetype.encode("utf-8")
    return _NativeMedia(raw, len(blob), mimetype_bytes), raw, mimetype_bytes


def _coerce_retention(retention: Retention | int | None) -> int:
    if retention is None:
        return int(Retention.NATURAL)
    try:
        value = int(retention)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid retention: {retention!r}") from exc
    if value not in {int(member) for member in Retention}:
        raise ValueError(f"invalid retention: {retention!r}")
    return value


def _validate_image_buffer(
    data: bytes, width: int, height: int, channels: int
) -> None:
    if width <= 0 or height <= 0 or channels <= 0:
        raise ValueError("width, height, and channels must be positive")
    if width > 2_147_483_647 or height > 2_147_483_647 or channels > 2_147_483_647:
        raise ValueError("image dimensions exceed the native int range")
    expected = width * height * channels
    if len(data) < expected:
        raise ValueError("image buffer is smaller than width * height * channels")


def _native_process_json_options(
    include_embedding: bool,
    retention: Retention | int | None = None,
) -> _NativeProcessJsonOptions:
    return _NativeProcessJsonOptions(
        ctypes.sizeof(_NativeProcessJsonOptions),
        1 if include_embedding else 0,
        _coerce_retention(retention),
        0,
    )


def _bool_to_int(value: bool) -> int:
    return 1 if value else 0


def _encode_optional_string(value: str | None) -> ctypes.Array[ctypes.c_char] | None:
    if value is None:
        return None
    return ctypes.create_string_buffer(value.encode("utf-8"))


class _ProviderBridge:
    def __init__(self, provider: DBProvider) -> None:
        self.provider = provider
        self._transactions: dict[int, Any] = {}
        self._next_transaction = 1
        self._results: dict[int, Any] = {}
        self._errors: list[ctypes.Array[ctypes.c_char]] = []

        self.execute_cb = _ExecuteCallback(self._execute)
        self.begin_cb = _BeginCallback(self._begin)
        self.commit_cb = _TransactionCallback(self._commit)
        self.rollback_cb = _TransactionCallback(self._rollback)
        self.release_transaction_cb = _ReleaseTransactionCallback(
            self._release_transaction
        )
        self.release_result_cb = _ReleaseResultCallback(self._release_result)
        self.callbacks = _DBCallbacks(
            ctypes.sizeof(_DBCallbacks),
            self.execute_cb,
            self.begin_cb,
            self.commit_cb,
            self.rollback_cb,
            self.release_transaction_cb,
            self.release_result_cb,
        )

    def _set_error(self, out_error: Any, message: str) -> int:
        encoded = ctypes.create_string_buffer(message.encode("utf-8"))
        self._errors.append(encoded)
        if out_error:
            out_error[0] = ctypes.cast(encoded, ctypes.c_char_p)
        return 1

    def _transaction(self, handle: int) -> Any | None:
        return self._transactions.get(handle) if handle else None

    def _value_from_c(self, value: _DBValue) -> Any:
        if value.type == CORTEXT_DB_VALUE_INT64:
            return int(value.int64_value)
        if value.type == CORTEXT_DB_VALUE_DOUBLE:
            return float(value.double_value)
        if value.type == CORTEXT_DB_VALUE_TEXT:
            return value.text_value.decode("utf-8") if value.text_value else ""
        if value.type == CORTEXT_DB_VALUE_BLOB:
            if not value.blob_data or value.blob_size == 0:
                return b""
            return bytes(value.blob_data[: value.blob_size])
        return None

    def _db_value(self, value: Any, keepalive: list[Any]) -> _DBValue:
        out = _DBValue()
        if value is None:
            out.type = CORTEXT_DB_VALUE_NULL
        elif isinstance(value, bool):
            out.type = CORTEXT_DB_VALUE_INT64
            out.int64_value = int(value)
        elif isinstance(value, int):
            out.type = CORTEXT_DB_VALUE_INT64
            out.int64_value = value
        elif isinstance(value, float):
            out.type = CORTEXT_DB_VALUE_DOUBLE
            out.double_value = value
        elif isinstance(value, str):
            raw = ctypes.create_string_buffer(value.encode("utf-8"))
            keepalive.append(raw)
            out.type = CORTEXT_DB_VALUE_TEXT
            out.text_value = ctypes.cast(raw, ctypes.c_char_p)
        else:
            raw_bytes = bytes(value)
            out.type = CORTEXT_DB_VALUE_BLOB
            out.blob_size = len(raw_bytes)
            if raw_bytes:
                array_type = ctypes.c_uint8 * len(raw_bytes)
                raw = array_type.from_buffer_copy(raw_bytes)
                keepalive.append(raw)
                out.blob_data = ctypes.cast(raw, ctypes.POINTER(ctypes.c_uint8))
        return out

    def _execute(
        self,
        _user_data: int,
        transaction: int,
        query: bytes,
        params: Any,
        param_count: int,
        out_result: Any,
        out_error: Any,
    ) -> int:
        try:
            py_params = [
                self._value_from_c(params[index]) for index in range(param_count)
            ]
            rows = self.provider.execute(
                query.decode("utf-8"), py_params, self._transaction(transaction)
            )

            keepalive: list[Any] = []
            row_array = (_DBRow * len(rows))()
            for row_index, row in enumerate(rows):
                items = list(row.items())
                cell_array = (_DBCell * len(items))()
                keepalive.append(cell_array)
                for cell_index, (name, value) in enumerate(items):
                    name_raw = ctypes.create_string_buffer(name.encode("utf-8"))
                    keepalive.append(name_raw)
                    cell_array[cell_index].column_name = ctypes.cast(
                        name_raw, ctypes.c_char_p
                    )
                    cell_array[cell_index].value = self._db_value(value, keepalive)
                row_array[row_index].cells = cell_array
                row_array[row_index].cell_count = len(items)

            keepalive.append(row_array)
            out_result[0].rows = row_array
            out_result[0].row_count = len(rows)
            self._results[ctypes.addressof(out_result.contents)] = keepalive
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _begin(
        self,
        _user_data: int,
        parent_transaction: int,
        out_transaction: Any,
        out_error: Any,
    ) -> int:
        try:
            tx = self.provider.begin(self._transaction(parent_transaction))
            handle = self._next_transaction
            self._next_transaction += 1
            self._transactions[handle] = tx
            out_transaction[0] = handle
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _commit(self, _user_data: int, transaction: int, out_error: Any) -> int:
        try:
            self.provider.commit(self._transactions[transaction])
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _rollback(self, _user_data: int, transaction: int, out_error: Any) -> int:
        try:
            self.provider.rollback(self._transactions[transaction])
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _release_transaction(self, _user_data: int, transaction: int) -> None:
        tx = self._transactions.pop(transaction, None)
        if tx is not None:
            self.provider.release_transaction(tx)

    def _release_result(self, _user_data: int, result: Any) -> None:
        self._results.pop(ctypes.addressof(result.contents), None)


class _ObjectProviderBridge:
    def __init__(self, provider: ObjectStoreProvider) -> None:
        self.provider = provider
        self._transactions: dict[int, Any] = {}
        self._next_transaction = 1
        self._errors: list[ctypes.Array[ctypes.c_char]] = []
        self._blobs: dict[int, Any] = {}

        self.begin_cb = _ObjectBeginCallback(self._begin)
        self.put_cb = _ObjectPutCallback(self._put)
        self.get_cb = _ObjectGetCallback(self._get)
        self.exists_cb = _ObjectExistsCallback(self._exists)
        self.delete_cb = _ObjectDeleteCallback(self._delete)
        self.commit_cb = _ObjectTransactionCallback(self._commit)
        self.rollback_cb = _ObjectTransactionCallback(self._rollback)
        self.release_transaction_cb = _ObjectReleaseTransactionCallback(
            self._release_transaction
        )
        self.release_blob_cb = _ObjectReleaseBlobCallback(self._release_blob)
        self.callbacks = _ObjectCallbacks(
            ctypes.sizeof(_ObjectCallbacks),
            self.begin_cb,
            self.put_cb,
            self.get_cb,
            self.exists_cb,
            self.delete_cb,
            self.commit_cb,
            self.rollback_cb,
            self.release_transaction_cb,
            self.release_blob_cb,
        )

    def _set_error(self, out_error: Any, message: str) -> int:
        encoded = ctypes.create_string_buffer(message.encode("utf-8"))
        self._errors.append(encoded)
        if out_error:
            out_error[0] = ctypes.cast(encoded, ctypes.c_char_p)
        return 1

    def _transaction(self, handle: int) -> Any | None:
        return self._transactions.get(handle) if handle else None

    def _bytes_from_c(self, data: Any, size: int) -> bytes:
        if not data or size == 0:
            return b""
        return bytes(data[:size])

    def _begin(
        self,
        _user_data: int,
        parent_transaction: int,
        out_transaction: Any,
        out_error: Any,
    ) -> int:
        try:
            tx = self.provider.begin(self._transaction(parent_transaction))
            handle = self._next_transaction
            self._next_transaction += 1
            self._transactions[handle] = tx
            out_transaction[0] = handle
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _put(
        self,
        _user_data: int,
        transaction: int,
        object_id: Any,
        object_id_size: int,
        data: Any,
        data_size: int,
        out_error: Any,
    ) -> int:
        try:
            self.provider.put(
                self._bytes_from_c(object_id, object_id_size),
                self._bytes_from_c(data, data_size),
                self._transactions[transaction],
            )
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _get(
        self,
        _user_data: int,
        transaction: int,
        object_id: Any,
        object_id_size: int,
        out_data: Any,
        out_data_size: Any,
        out_error: Any,
    ) -> int:
        try:
            data = self.provider.get(
                self._bytes_from_c(object_id, object_id_size),
                self._transactions[transaction],
            )
            if data is None:
                out_data[0] = ctypes.cast(None, ctypes.POINTER(ctypes.c_uint8))
                out_data_size[0] = 0
                return 0
            raw_bytes = bytes(data)
            array_type = ctypes.c_uint8 * len(raw_bytes)
            raw = array_type.from_buffer_copy(raw_bytes)
            ptr = ctypes.cast(raw, ctypes.POINTER(ctypes.c_uint8))
            self._blobs[ctypes.addressof(raw)] = raw
            out_data[0] = ptr
            out_data_size[0] = len(raw_bytes)
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _exists(
        self,
        _user_data: int,
        transaction: int,
        object_id: Any,
        object_id_size: int,
        out_exists: Any,
        out_error: Any,
    ) -> int:
        try:
            out_exists[0] = int(
                self.provider.exists(
                    self._bytes_from_c(object_id, object_id_size),
                    self._transactions[transaction],
                )
            )
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _delete(
        self,
        _user_data: int,
        transaction: int,
        object_id: Any,
        object_id_size: int,
        out_deleted: Any,
        out_error: Any,
    ) -> int:
        try:
            out_deleted[0] = int(
                self.provider.delete(
                    self._bytes_from_c(object_id, object_id_size),
                    self._transactions[transaction],
                )
            )
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _commit(self, _user_data: int, transaction: int, out_error: Any) -> int:
        try:
            self.provider.commit(self._transactions[transaction])
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _rollback(self, _user_data: int, transaction: int, out_error: Any) -> int:
        try:
            self.provider.rollback(self._transactions[transaction])
            return 0
        except Exception as exc:
            return self._set_error(out_error, str(exc))

    def _release_transaction(self, _user_data: int, transaction: int) -> None:
        tx = self._transactions.pop(transaction, None)
        if tx is not None:
            self.provider.release_transaction(tx)

    def _release_blob(self, _user_data: int, data: Any, _data_size: int) -> None:
        if data:
            self._blobs.pop(ctypes.addressof(data.contents), None)


class Cortext:
    def __init__(
        self,
        db_path: str = ":memory:",
        *,
        store: DBProvider | None = None,
        object_store: ObjectStoreProvider | None = None,
        config: Config | None = None,
        library_path: str | os.PathLike[str] | None = None,
    ) -> None:
        if store is not None and db_path != ":memory:":
            raise ValueError("db_path and store are mutually exclusive")
        self._lib = _lib() if library_path is None else load_library(library_path)
        native_cfg = _NativeConfig()
        self._lib.cortext_config_init(ctypes.byref(native_cfg))

        if config is not None:
            native_cfg.focus = config.focus
            native_cfg.sensitivity = config.sensitivity
            native_cfg.stability = config.stability
            native_cfg.affect_interrupt = _bool_to_int(config.affect_interrupt)
            native_cfg.affect_retrieval = _bool_to_int(config.affect_retrieval)
            native_cfg.reinforcement_enabled = _bool_to_int(config.reinforcement_enabled)
            native_cfg.procedural_enabled = _bool_to_int(config.procedural_enabled)
            native_cfg.sequential_edges_enabled = _bool_to_int(config.sequential_edges_enabled)
            native_cfg.signal_filter_audio_enabled = _bool_to_int(
                config.signal_filter_audio_enabled
            )
            native_cfg.signal_filter_image_enabled = _bool_to_int(
                config.signal_filter_image_enabled
            )
            native_cfg.signal_filter_text_enabled = _bool_to_int(
                config.signal_filter_text_enabled
            )

        self._provider_bridge = _ProviderBridge(store) if store is not None else None
        self._object_provider_bridge = (
            _ObjectProviderBridge(object_store) if object_store is not None else None
        )
        had_model_env = "CORTEXT_AIST_MODEL_PATH" in os.environ
        previous_model_env = os.environ.get("CORTEXT_AIST_MODEL_PATH")
        # Stale/missing override: re-resolve from release assets.
        if had_model_env and previous_model_env:
            if not Path(previous_model_env).expanduser().is_file():
                had_model_env = False
        default_model_path = None if had_model_env else _default_aist_model_path(db_path)
        if not had_model_env and default_model_path is not None:
            os.environ["CORTEXT_AIST_MODEL_PATH"] = default_model_path
        try:
            if self._provider_bridge is not None and self._object_provider_bridge is not None:
                self._handle = self._lib.cortext_create_with_store_and_object_callbacks(
                    ctypes.byref(native_cfg),
                    ctypes.byref(self._provider_bridge.callbacks),
                    None,
                    ctypes.byref(self._object_provider_bridge.callbacks),
                    None,
                )
            elif self._provider_bridge is not None:
                self._handle = self._lib.cortext_create_with_store_callbacks(
                    ctypes.byref(native_cfg),
                    ctypes.byref(self._provider_bridge.callbacks),
                    None,
                )
            elif self._object_provider_bridge is not None:
                db_path_raw = db_path.encode("utf-8")
                self._handle = self._lib.cortext_create_with_config_and_object_callbacks(
                    ctypes.byref(native_cfg),
                    db_path_raw,
                    ctypes.byref(self._object_provider_bridge.callbacks),
                    None,
                )
            else:
                db_path_raw = db_path.encode("utf-8")
                self._handle = self._lib.cortext_create_with_config(
                    ctypes.byref(native_cfg),
                    db_path_raw,
                )
        finally:
            if not had_model_env:
                os.environ.pop("CORTEXT_AIST_MODEL_PATH", None)
            elif previous_model_env is not None:
                os.environ["CORTEXT_AIST_MODEL_PATH"] = previous_model_env
        if not self._handle:
            _raise_last_error("cortext create failed")

    def close(self) -> None:
        if getattr(self, "_handle", None):
            self._lib.cortext_free(self._handle)
            self._handle = None

    def __enter__(self) -> "Cortext":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def flush(self) -> None:
        status = self._lib.cortext_flush(self._handle)
        if status != 0:
            _raise_last_error("cortext_flush failed")

    def reset(self) -> None:
        status = self._lib.cortext_reset(self._handle)
        if status != 0:
            _raise_last_error("cortext_reset failed")

    def process_text_json(
        self,
        text: str,
        source_id: str,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> str:
        options = _native_process_json_options(include_embedding, retention)
        return self._call_json(
            self._lib.cortext_process_text_json_with_options,
            text.encode("utf-8"),
            source_id.encode("utf-8"),
            ctypes.byref(options),
        )

    def process_text(
        self,
        text: str,
        source_id: str,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> dict[str, Any]:
        return json.loads(
            self.process_text_json(
                text, source_id, include_embedding, retention
            )
        )

    def process_text_with_media_json(
        self,
        text: str,
        source_id: str,
        media: Media | bytes | bytearray | memoryview | None = None,
        media_mimetype: str | None = None,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> str:
        if not getattr(self._lib, "_cortext_text_media_json_available", False):
            raise RuntimeError(
                "loaded native library does not support text media processing"
            )
        native_media, media_buffer, mimetype_buffer = _native_media(
            media, media_mimetype
        )
        options = _native_process_json_options(include_embedding, retention)
        _ = (media_buffer, mimetype_buffer)
        return self._call_json(
            self._lib.cortext_process_text_with_media_json_with_options,
            text.encode("utf-8"),
            source_id.encode("utf-8"),
            ctypes.byref(native_media),
            ctypes.byref(options),
        )

    def process_text_with_media(
        self,
        text: str,
        source_id: str,
        media: Media | bytes | bytearray | memoryview | None = None,
        media_mimetype: str | None = None,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> dict[str, Any]:
        return json.loads(
            self.process_text_with_media_json(
                text,
                source_id,
                media,
                media_mimetype,
                include_embedding,
                retention,
            )
        )

    def embed_text_json(self, text: str) -> str:
        return self._call_json(
            self._lib.cortext_embed_text_json,
            text.encode("utf-8"),
        )

    def embed_text(self, text: str) -> list[float]:
        return list(json.loads(self.embed_text_json(text))["embedding"])

    def process_audio_json(
        self,
        pcm: Iterable[float],
        source_id: str,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> str:
        samples = array("f", pcm)
        raw = (ctypes.c_float * len(samples)).from_buffer(samples)
        options = _native_process_json_options(include_embedding, retention)
        return self._call_json(
            self._lib.cortext_process_audio_json_with_options,
            raw,
            len(samples),
            source_id.encode("utf-8"),
            ctypes.byref(options),
        )

    def process_audio_with_media_json(
        self,
        pcm: Iterable[float],
        source_id: str,
        media: Media | bytes | bytearray | memoryview | None = None,
        media_mimetype: str | None = None,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> str:
        samples = array("f", pcm)
        raw = (ctypes.c_float * len(samples)).from_buffer(samples)
        native_media, media_buffer, mimetype_buffer = _native_media(
            media, media_mimetype
        )
        options = _native_process_json_options(include_embedding, retention)
        _ = (media_buffer, mimetype_buffer)
        return self._call_json(
            self._lib.cortext_process_audio_with_media_json_with_options,
            raw,
            len(samples),
            source_id.encode("utf-8"),
            ctypes.byref(native_media),
            ctypes.byref(options),
        )

    def process_audio(
        self,
        pcm: Iterable[float],
        source_id: str,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> dict[str, Any]:
        return json.loads(
            self.process_audio_json(
                pcm, source_id, include_embedding, retention
            )
        )

    def process_audio_with_media(
        self,
        pcm: Iterable[float],
        source_id: str,
        media: Media | bytes | bytearray | memoryview | None = None,
        media_mimetype: str | None = None,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> dict[str, Any]:
        return json.loads(
            self.process_audio_with_media_json(
                pcm,
                source_id,
                media,
                media_mimetype,
                include_embedding,
                retention,
            )
        )

    def embed_audio_json(self, pcm: Iterable[float]) -> str:
        samples = array("f", pcm)
        raw = (ctypes.c_float * len(samples)).from_buffer(samples)
        return self._call_json(
            self._lib.cortext_embed_audio_json,
            raw,
            len(samples),
        )

    def embed_audio(self, pcm: Iterable[float]) -> list[float]:
        return list(json.loads(self.embed_audio_json(pcm))["embedding"])

    def process_image_json(
        self,
        data: bytes | bytearray | memoryview,
        width: int,
        height: int,
        channels: int,
        source_id: str,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> str:
        blob = bytes(data)
        _validate_image_buffer(blob, width, height, channels)
        raw = (ctypes.c_uint8 * len(blob)).from_buffer_copy(blob)
        options = _native_process_json_options(include_embedding, retention)
        return self._call_json(
            self._lib.cortext_process_image_json_with_options,
            raw,
            width,
            height,
            channels,
            source_id.encode("utf-8"),
            ctypes.byref(options),
        )

    def process_image_with_media_json(
        self,
        data: bytes | bytearray | memoryview,
        width: int,
        height: int,
        channels: int,
        source_id: str,
        media: Media | bytes | bytearray | memoryview | None = None,
        media_mimetype: str | None = None,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> str:
        blob = bytes(data)
        _validate_image_buffer(blob, width, height, channels)
        raw = (ctypes.c_uint8 * len(blob)).from_buffer_copy(blob)
        native_media, media_buffer, mimetype_buffer = _native_media(
            media, media_mimetype
        )
        options = _native_process_json_options(include_embedding, retention)
        _ = (media_buffer, mimetype_buffer)
        return self._call_json(
            self._lib.cortext_process_image_with_media_json_with_options,
            raw,
            width,
            height,
            channels,
            source_id.encode("utf-8"),
            ctypes.byref(native_media),
            ctypes.byref(options),
        )

    def process_image(
        self,
        data: bytes | bytearray | memoryview,
        width: int,
        height: int,
        channels: int,
        source_id: str,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> dict[str, Any]:
        return json.loads(
            self.process_image_json(
                data,
                width,
                height,
                channels,
                source_id,
                include_embedding,
                retention,
            )
        )

    def process_image_with_media(
        self,
        data: bytes | bytearray | memoryview,
        width: int,
        height: int,
        channels: int,
        source_id: str,
        media: Media | bytes | bytearray | memoryview | None = None,
        media_mimetype: str | None = None,
        include_embedding: bool = True,
        retention: Retention | int | None = None,
    ) -> dict[str, Any]:
        return json.loads(
            self.process_image_with_media_json(
                data,
                width,
                height,
                channels,
                source_id,
                media,
                media_mimetype,
                include_embedding,
                retention,
            )
        )

    def embed_image_json(
        self,
        data: bytes | bytearray | memoryview,
        width: int,
        height: int,
        channels: int,
    ) -> str:
        blob = bytes(data)
        _validate_image_buffer(blob, width, height, channels)
        raw = (ctypes.c_uint8 * len(blob)).from_buffer_copy(blob)
        return self._call_json(
            self._lib.cortext_embed_image_json,
            raw,
            width,
            height,
            channels,
        )

    def embed_image(
        self,
        data: bytes | bytearray | memoryview,
        width: int,
        height: int,
        channels: int,
    ) -> list[float]:
        payload = self.embed_image_json(data, width, height, channels)
        return list(json.loads(payload)["embedding"])

    def consolidate_json(self) -> str:
        return self._call_json(self._lib.cortext_consolidate_json)

    def consolidate(self) -> dict[str, Any]:
        return json.loads(self.consolidate_json())

    def _call_json(self, fn: Any, *args: Any) -> str:
        result = fn(self._handle, *args)
        if not result:
            _raise_last_error(f"{fn.__name__} failed")
        try:
            return ctypes.string_at(result).decode("utf-8")
        finally:
            self._lib.cortext_string_free(result)
