"""ローカル起動した FastAPI サーバーに POST して SSE を表示する."""
import sys

import httpx

sys.stdout.reconfigure(encoding="utf-8")


REQUEST_BODY = {
    "companyName": "株式会社サンプル製作所",
    "industry": "製造業",
    "scale": "中小企業",
    "knownInfo": "DX 推進したいが何から手を付けるか不明。"
    "ベテラン技術者の高齢化で技能継承も気がかり。",
    "salesperson": "山田",
}


def main() -> None:
    url = "http://127.0.0.1:8000/api/first-meeting/generate"
    print(f"[POST] {url}")
    with httpx.stream("POST", url, json=REQUEST_BODY, timeout=180.0) as response:
        print(f"[status] {response.status_code}")
        print(f"[content-type] {response.headers.get('content-type')}")
        print("---")
        for line in response.iter_lines():
            if line:
                print(line)


if __name__ == "__main__":
    main()
