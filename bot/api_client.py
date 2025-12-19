from typing import Any, Dict, List, Optional

import httpx

from .config import API_BASE_URL


class ApiClient:
    """
    Простой клиент для общения бота с backend API.
    Работает через httpx.AsyncClient.
    """

    def __init__(self) -> None:
        self.base_url = API_BASE_URL.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    # ---------- Аутентификация ----------
    async def register_user(
        self,
        nickname: str,
        email: str,
        password: str,
    ) -> Dict[str, Any]:
        payload = {"nickname": nickname, "email": email, "password": password}
        resp = await self._client.post("/auth/register", json=payload)
        resp.raise_for_status()
        return resp.json()

    async def login(
        self,
        email: str,
        password: str,
    ) -> str:
        """
        Логин через /auth/login, возвращает access_token.
        В backend используется OAuth2PasswordRequestForm, поэтому отправляем form-data.
        """
        data = {"username": email, "password": password}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        resp = await self._client.post("/auth/login", data=data, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        return body["access_token"]

    async def change_password(
        self,
        token: str,
        old_password: str,
        new_password: str,
    ) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        params = {"old_password": old_password, "new_password": new_password}
        resp = await self._client.patch("/auth/change-password", params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def get_me(self, token: str) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._client.get("/auth/me", headers=headers)
        resp.raise_for_status()
        return resp.json()

    # ---------- Задачи ----------
    async def list_tasks(self, token: str) -> List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._client.get("/tasks", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def create_task(
        self,
        token: str,
        title: str,
        description: Optional[str],
        is_important: bool,
        deadline_at_iso: Optional[str],
    ) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        payload: Dict[str, Any] = {
            "title": title,
            "description": description,
            "is_important": is_important,
            "deadline_at": deadline_at_iso,
        }
        resp = await self._client.post("/tasks/", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def update_task(
        self,
        token: str,
        task_id: int,
        *,
        title: Optional[str] = None,
        description: Optional[str] = None,
        is_important: Optional[bool] = None,
        deadline_at_iso: Optional[str] = None,
    ) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        payload: Dict[str, Any] = {}
        if title is not None:
            payload["title"] = title
        if description is not None:
            payload["description"] = description
        if is_important is not None:
            payload["is_important"] = is_important
        if deadline_at_iso is not None:
            payload["deadline_at"] = deadline_at_iso

        resp = await self._client.put(f"/tasks/{task_id}", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def complete_task(self, token: str, task_id: int) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._client.patch(f"/tasks/{task_id}/complete", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def delete_task(self, token: str, task_id: int) -> Dict[str, Any]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._client.delete(f"/tasks/{task_id}", headers=headers)
        resp.raise_for_status()
        return resp.json()

    async def tasks_today(self, token: str) -> List[Dict[str, Any]]:
        """
        Возвращает задачи на сегодня.
        Если backend отвечает 404 (нет задач), возвращает пустой список.
        """
        headers = {"Authorization": f"Bearer {token}"}
        try:
            resp = await self._client.get("/tasks/today", headers=headers)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return []
            raise
        return resp.json()

    async def search_tasks(self, token: str, query: str) -> List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._client.get("/tasks/search", params={"q": query}, headers=headers)
        resp.raise_for_status()
        return resp.json()

    # ---------- Статистика / дедлайны ----------
    async def get_deadlines(self, token: str) -> List[Dict[str, Any]]:
        headers = {"Authorization": f"Bearer {token}"}
        resp = await self._client.get("/stats/deadlines", headers=headers)
        resp.raise_for_status()
        return resp.json()


