import requests
from app.config import KHMER_TOPUP_API_KEY, KHMER_TOPUP_BASE_URL

class SupplierError(Exception):
    pass

class KhmerTopUp:
    def __init__(self):
        self.base = KHMER_TOPUP_BASE_URL
        self.headers = {
            "Authorization": f"Bearer {KHMER_TOPUP_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method, path, **kwargs):
        try:
            response = requests.request(method, self.base + path, headers=self.headers, timeout=25, **kwargs)
            data = response.json()
        except requests.RequestException as exc:
            raise SupplierError(f"Network error: {exc}") from exc
        except ValueError as exc:
            raise SupplierError("Supplier returned a non-JSON response") from exc
        if not response.ok:
            raise SupplierError(f"HTTP {response.status_code}: {data.get('error', data)}")
        return data

    def me(self):
        return self._request("GET", "/me")

    def games(self):
        data = self._request("GET", "/games")
        return data.get("games", [])

    def check(self, slug, player_id, server_id=None):
        params = {"slug": slug, "player_id": player_id}
        if server_id:
            params["server_id"] = server_id
        return self._request("GET", "/check", params=params)

    def create_order(self, package_id, player_id, server_id, reference):
        body = {"package_id": int(package_id), "player_id": str(player_id), "reference": reference}
        if server_id:
            body["server_id"] = str(server_id)
        return self._request("POST", "/orders", json=body)

    def order_status(self, order_code):
        return self._request("GET", f"/orders/{order_code}")