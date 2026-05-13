from __future__ import annotations
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


class AuthError(Exception):
    def __init__(self, msg: str = "", billing: bool = False) -> None:
        super().__init__(msg)
        self.billing = billing


class HttpSession:
    def __init__(self, base_url: str, timeout: int = 30) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PATCH"],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def _url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _raise_for_status(self, resp: requests.Response) -> None:
        if resp.status_code == 401:
            body = resp.text.lower()
            billing = any(
                kw in body for kw in ("billing", "subscription", "payment")
            )
            raise AuthError(
                f"401 Unauthorized (billing_issue={billing}): {resp.text[:200]}",
                billing=billing,
            )
        resp.raise_for_status()

    def get(self, path: str, **kwargs: object) -> requests.Response:
        resp = self._session.get(self._url(path), timeout=self.timeout, **kwargs)
        self._raise_for_status(resp)
        return resp

    def post(self, path: str, **kwargs: object) -> requests.Response:
        resp = self._session.post(self._url(path), timeout=self.timeout, **kwargs)
        self._raise_for_status(resp)
        return resp

    def patch(self, path: str, **kwargs: object) -> requests.Response:
        resp = self._session.patch(self._url(path), timeout=self.timeout, **kwargs)
        self._raise_for_status(resp)
        return resp

    def close(self) -> None:
        self._session.close()
