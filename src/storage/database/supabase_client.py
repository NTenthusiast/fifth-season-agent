import logging
import os
import threading
import time
from typing import Optional

import httpx
from supabase import create_client, Client, ClientOptions

logger = logging.getLogger("fifth_season.supabase")

_env_loaded = False

# 服务端直连客户端缓存（见 get_supabase_client 的说明）
_service_client: Optional[Client] = None
_service_client_lock = threading.Lock()


class _RetryTransport(httpx.BaseTransport):
    """对临时性网关故障（503/PGRST002/网络瞬断）自动重试的 transport 包装。

    策略：
    - 任意方法的 502/503/504：网关明确未执行请求，重试安全（不会重复写入）
    - GET 的网络异常（连接重置/响应丢失）：幂等，可重试
    - POST/PATCH/DELETE 的网络异常：可能已实际写入，不重试，直接上抛
    """

    RETRYABLE_STATUS = {502, 503, 504}
    MAX_RETRIES = 2
    BACKOFF_BASE = 0.8

    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        is_read = request.method.upper() in ("GET", "HEAD")
        last_resp: Optional[httpx.Response] = None
        last_exc: Optional[Exception] = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                resp = self._inner.handle_request(request)
                is_last = attempt == self.MAX_RETRIES
                if resp.status_code not in self.RETRYABLE_STATUS or is_last:
                    return resp  # 成功或最后一次尝试：原样返回（流未关闭）
                # 网关明确拒绝（未执行），关闭后进入下一轮重试
                last_resp = resp
                resp.close()
            except (httpx.TransportError, httpx.HTTPError) as exc:
                if not is_read:
                    raise  # 写请求网络异常：可能已生效，禁止重试
                last_exc = exc
            if attempt < self.MAX_RETRIES:
                time.sleep(self.BACKOFF_BASE * (2 ** attempt))

        if last_resp is not None:
            # 不应到达此处（最后一次尝试会直接返回），防御性兜底
            raise last_exc or RuntimeError("retry exhausted with closed response")
        assert last_exc is not None
        raise last_exc


def _load_env() -> None:
    global _env_loaded

    if _env_loaded or (os.getenv("COZE_SUPABASE_URL") and os.getenv("COZE_SUPABASE_ANON_KEY")):
        return

    try:
        from dotenv import load_dotenv
        load_dotenv()
        if os.getenv("COZE_SUPABASE_URL") and os.getenv("COZE_SUPABASE_ANON_KEY"):
            _env_loaded = True
            return
    except ImportError:
        pass

    try:
        from coze_workload_identity import Client as WorkloadClient

        client = WorkloadClient()
        env_vars = client.get_project_env_vars()
        client.close()

        for env_var in env_vars:
            if not os.getenv(env_var.key):
                os.environ[env_var.key] = env_var.value

        _env_loaded = True
    except Exception:
        pass


def get_supabase_credentials() -> tuple[str, str]:
    _load_env()

    url = os.getenv("COZE_SUPABASE_URL")
    anon_key = os.getenv("COZE_SUPABASE_ANON_KEY")

    if not url:
        raise ValueError("COZE_SUPABASE_URL is not set")
    if not anon_key:
        raise ValueError("COZE_SUPABASE_ANON_KEY is not set")

    return url, anon_key


def get_supabase_service_role_key() -> Optional[str]:
    _load_env()
    return os.getenv("COZE_SUPABASE_SERVICE_ROLE_KEY")


def get_supabase_client(token: Optional[str] = None) -> Client:
    """获取 Supabase 客户端。

    token=None（服务端直连）的场景会缓存并复用同一个客户端：此前每次调用都新建
    httpx.Client 与连接池且从不关闭，而 tools/db_helpers._client() 每处都调它——
    单次 get_project_detail 就要走 4 次（项目/成员/动态/交接包），等于每次请求都
    重做 4 轮 TCP+TLS 握手并留下 4 个无人回收的连接池。这是响应慢的主要来源之一。
    带 token 的场景需按用户隔离，不做缓存。
    """
    if token is not None:
        return _build_client(token)

    global _service_client
    if _service_client is None:
        with _service_client_lock:
            if _service_client is None:
                _service_client = _build_client(None)
    return _service_client


def _build_client(token: Optional[str]) -> Client:
    url, anon_key = get_supabase_credentials()

    if token:
        key = anon_key
    else:
        service_role_key = get_supabase_service_role_key()
        key = service_role_key if service_role_key else anon_key

    # http2=True is set on HTTPTransport (not httpx.Client) because we provide
    # a custom transport for report instrumentation wrapping.
    transport: httpx.BaseTransport = httpx.HTTPTransport(http2=True)
    transport = _RetryTransport(transport)
    try:
        from coze_coding_dev_sdk.report import get_report_buffer, InstrumentedTransport

        buffer = get_report_buffer()
        logger.debug("[report] supabase-client: buffer = %s", bool(buffer))
        if buffer:
            transport = InstrumentedTransport(transport, buffer, source="supabase")
            logger.debug("[report] supabase-client: InstrumentedTransport injected")
    except Exception as e:  # noqa: BLE001
        logger.debug("[report] supabase-client: setup skipped: %s", e)

    http_client = httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(
            connect=20.0,
            read=60.0,
            write=60.0,
            pool=10.0,
        ),
        limits=httpx.Limits(
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=30.0,
        ),
        follow_redirects=True,
    )

    if token:
        options = ClientOptions(
            httpx_client=http_client,
            headers={"Authorization": f"Bearer {token}"},
            auto_refresh_token=False,
        )
    else:
        options = ClientOptions(
            httpx_client=http_client,
            auto_refresh_token=False,
        )

    return create_client(url, key, options=options)
