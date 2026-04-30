from __future__ import annotations

import os
from datetime import date

import httpx


def main() -> None:
    api_base_url = os.environ["API_BASE_URL"].rstrip("/")
    token = os.environ["INVOICE_CRON_TOKEN"]
    response = httpx.post(
        f"{api_base_url}/system/invoices/generate",
        params={"as_of": date.today().isoformat()},
        headers={"x-system-token": token},
        timeout=30,
    )
    response.raise_for_status()
    print(response.text)


if __name__ == "__main__":
    main()
