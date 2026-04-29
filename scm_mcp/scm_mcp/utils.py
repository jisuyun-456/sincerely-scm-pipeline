import time
import requests
from .config import AIRTABLE_PAT, AIRTABLE_BASE_URL, AIRTABLE_CONTENT_URL


def _headers() -> dict:
    return {"Authorization": f"Bearer {AIRTABLE_PAT}"}


def paginated_get(base_id: str, table_id: str,
                  fields: list[str] | None = None,
                  formula: str | None = None,
                  max_records: int | None = None) -> list[dict]:
    url = f"{AIRTABLE_BASE_URL}/{base_id}/{table_id}"
    params: dict = {"pageSize": 100}
    if fields:
        params["fields[]"] = fields
    if formula:
        params["filterByFormula"] = formula
    if max_records:
        params["maxRecords"] = max_records

    records: list[dict] = []
    while True:
        resp = _request_with_retry("GET", url, params=params)
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
        time.sleep(0.2)
    return records


def patch_records(base_id: str, table_id: str, updates: list[dict]) -> list[dict]:
    url = f"{AIRTABLE_BASE_URL}/{base_id}/{table_id}"
    results: list[dict] = []
    for i in range(0, len(updates), 10):
        batch = updates[i:i + 10]
        resp = _request_with_retry("PATCH", url, json={"records": batch})
        results.extend(resp.json().get("records", []))
        time.sleep(0.2)
    return results


def upload_attachment(base_id: str, record_id: str, field_id: str,
                      filename: str, pdf_bytes: bytes) -> dict:
    url = f"{AIRTABLE_CONTENT_URL}/{base_id}/{record_id}/{field_id}/uploadAttachment"
    for attempt in range(3):
        resp = requests.post(
            url,
            headers={**_headers(), "Content-Type": "application/octet-stream",
                     "Content-Disposition": f'attachment; filename="{filename}"'},
            data=pdf_bytes,
            timeout=60,
        )
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 30))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    raise RuntimeError("upload_attachment failed after 3 retries")


def get_table_schema(base_id: str) -> dict:
    url = f"{AIRTABLE_BASE_URL}/meta/bases/{base_id}/tables"
    resp = _request_with_retry("GET", url)
    return resp.json()


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    for attempt in range(3):
        resp = requests.request(method, url, headers=_headers(),
                                timeout=30, **kwargs)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 30))
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"{method} {url} failed after 3 retries")
