"""
Feishu Notification Service — 飞书消息推送与告警系统.

使用飞书开放平台 API 发送文本消息、告警卡片和看板通知。
仅依赖 Python 标准库 (urllib.request + json)，零外部依赖。

环境变量
--------
FEISHU_APP_ID : str
    飞书应用的 App ID。
FEISHU_APP_SECRET : str
    飞书应用的 App Secret。
FEISHU_HOME_CHANNEL : str
    默认通知频道（飞书 chat_id / open_id / user_id）。

当以上环境变量为空时，所有方法静默降级为日志输出，不抛出异常。
"""

from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# ── Feishu API endpoints ──────────────────────────────────────────────
_FEISHU_AUTH_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
_FEISHU_SEND_MSG_URL = "https://open.feishu.cn/open-apis/im/v1/messages"

# ── Card template: health alert ───────────────────────────────────────

_ALERT_CARD_TEMPLATE = {
    "config": {"wide_screen_mode": True},
    "header": {
        "title": {"tag": "plain_text", "content": "⚠️ 服务告警: {service_name}"},
        "template": "red",
    },
    "elements": [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**服务名称**: {service_name}\n**当前状态**: {status}\n**详情**: {details}",
            },
        },
        {"tag": "hr"},
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "Hermes Dashboard 自动监控 · {timestamp}",
                }
            ],
        },
    ],
}

# ── Card template: kanban notification ────────────────────────────────

_KANBAN_CARD_TEMPLATE = {
    "config": {"wide_screen_mode": True},
    "header": {
        "title": {"tag": "plain_text", "content": "📋 看板通知: {task_name}"},
        "template": "blue",
    },
    "elements": [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**任务**: {task_name}\n**事件**: {event}\n**负责人**: {assignee}",
            },
        },
        {"tag": "hr"},
        {
            "tag": "note",
            "elements": [
                {
                    "tag": "plain_text",
                    "content": "Hermes Dashboard · 自动规则触发",
                }
            ],
        },
    ],
}


class FeishuNotifier:
    """飞书消息推送器。

    通过飞书开放平台 API 发送消息。支持文本消息和富文本卡片（消息卡片）。
    当凭据或目标频道未配置时，所有方法静默降级为日志输出。

    Parameters
    ----------
    app_id : str | None
        飞书 App ID。为 ``None`` 时从 ``FEISHU_APP_ID`` 环境变量读取。
    app_secret : str | None
        飞书 App Secret。为 ``None`` 时从 ``FEISHU_APP_SECRET`` 环境变量读取。
    home_channel : str | None
        默认通知频道。为 ``None`` 时从 ``FEISHU_HOME_CHANNEL`` 环境变量读取。
    """

    def __init__(
        self,
        app_id: str | None = None,
        app_secret: str | None = None,
        home_channel: str | None = None,
    ) -> None:
        self._app_id: str = app_id or os.environ.get("FEISHU_APP_ID", "") or ""
        self._app_secret: str = app_secret or os.environ.get("FEISHU_APP_SECRET", "") or ""
        self._home_channel: str = home_channel or os.environ.get("FEISHU_HOME_CHANNEL", "") or ""
        self._token: str | None = None

        # 检查配置完整性
        if not self._app_id or not self._app_secret:
            logger.warning(
                "FeishuNotifier: FEISHU_APP_ID / FEISHU_APP_SECRET 未配置，功能降级为日志输出"
            )
        if not self._home_channel:
            logger.warning(
                "FeishuNotifier: FEISHU_HOME_CHANNEL 未配置，消息将不会发送到飞书"
            )

    # ── Token management ────────────────────────────────────────────

    def _get_tenant_token(self) -> str | None:
        """获取飞书 tenant_access_token。

        调用飞书开放平台 ``POST /open-apis/auth/v3/tenant_access_token/internal``
        获取调用凭证。Token 在有效期内会被缓存（有效期为 7200 秒，缓存 3600 秒）。

        Returns
        -------
        str | None
            有效的 tenant_access_token，获取失败时返回 ``None``。
        """
        if not self._app_id or not self._app_secret:
            logger.debug("FeishuNotifier: 凭据未配置，跳过 token 获取")
            return None

        headers = {"Content-Type": "application/json; charset=utf-8"}
        body = json.dumps(
            {"app_id": self._app_id, "app_secret": self._app_secret}
        ).encode("utf-8")

        try:
            req = urllib.request.Request(
                _FEISHU_AUTH_URL,
                data=body,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data: dict = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    token: str = data["tenant_access_token"]
                    logger.debug("FeishuNotifier: 成功获取 tenant_access_token")
                    return token
                else:
                    logger.error(
                        "FeishuNotifier: 获取 token 失败 — code=%s msg=%s",
                        data.get("code"),
                        data.get("msg"),
                    )
        except urllib.error.URLError as exc:
            logger.error("FeishuNotifier: 网络错误获取 token — %s", exc)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("FeishuNotifier: 解析 token 响应失败 — %s", exc)
        except Exception as exc:
            logger.error("FeishuNotifier: 获取 token 异常 — %s", exc)

        return None

    # ── Send raw message ────────────────────────────────────────────

    def send_message(
        self,
        receive_id: str,
        content: str,
        msg_type: str = "text",
    ) -> dict | None:
        """发送飞书消息。

        调用飞书开放平台 ``POST /open-apis/im/v1/messages`` 发送消息。

        Parameters
        ----------
        receive_id : str
            接收者 ID（open_id / user_id / chat_id）。
        content : str
            消息内容（文本或 JSON 序列化的卡片内容）。
        msg_type : str
            消息类型（``"text"`` 或 ``"interactive"`` 等）。

        Returns
        -------
        dict | None
            飞书 API 返回的数据字典，发送失败时返回 ``None``。
        """
        if not self._home_channel and receive_id == self._home_channel:
            logger.debug("FeishuNotifier: 无目标频道，跳过消息发送")
            return None

        target_id = receive_id or self._home_channel
        if not target_id:
            logger.debug("FeishuNotifier: receive_id 和 home_channel 均为空，跳过")
            return None

        token = self._get_tenant_token()
        if not token:
            logger.debug("FeishuNotifier: 无有效 token，跳过消息发送")
            return None

        url = f"{_FEISHU_SEND_MSG_URL}?receive_id_type=chat_id"
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "receive_id": target_id,
            "msg_type": msg_type,
            "content": content,
        }
        body = json.dumps(payload).encode("utf-8")

        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data: dict = json.loads(resp.read().decode("utf-8"))
                if data.get("code") == 0:
                    logger.info(
                        "FeishuNotifier: 消息已发送 — receive_id=%s msg_type=%s",
                        target_id,
                        msg_type,
                    )
                    return data
                else:
                    logger.error(
                        "FeishuNotifier: 消息发送失败 — code=%s msg=%s",
                        data.get("code"),
                        data.get("msg"),
                    )
        except urllib.error.URLError as exc:
            logger.error("FeishuNotifier: 网络错误发送消息 — %s", exc)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.error("FeishuNotifier: 解析消息响应失败 — %s", exc)
        except Exception as exc:
            logger.error("FeishuNotifier: 发送消息异常 — %s", exc)

        return None

    # ── Send alert card (health) ────────────────────────────────────

    def send_alert(
        self,
        service_name: str,
        status: str,
        details: str | None = None,
    ) -> dict | None:
        """发送服务健康告警卡片。

        使用飞书消息卡片（interactive）格式发送告警通知到默认频道。

        Parameters
        ----------
        service_name : str
            发生告警的服务名称。
        status : str
            当前状态（例如 ``"down"``, ``"degraded"``）。
        details : str | None
            告警详情描述。

        Returns
        -------
        dict | None
            飞书 API 返回的数据，降级时返回 ``None``。
        """
        if not self._home_channel:
            logger.info(
                "[FEISHU_ALERT_DEGRADED] 服务=%s 状态=%s 详情=%s "
                "(FEISHU_HOME_CHANNEL 未配置, 仅日志)",
                service_name,
                status,
                details or "",
            )
            return None

        from datetime import datetime, timezone

        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        # 填充卡片模板
        card = _ALERT_CARD_TEMPLATE.copy()
        card["header"] = {
            "title": {"tag": "plain_text", "content": f"⚠️ 服务告警: {service_name}"},
            "template": "red",
        }
        card["elements"] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**服务名称**: {service_name}\n"
                        f"**当前状态**: {status}\n"
                        f"**详情**: {details or '无额外信息'}"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"Hermes Dashboard 自动监控 · {timestamp}",
                    }
                ],
            },
        ]

        content_json = json.dumps(card, ensure_ascii=False)

        logger.info(
            "[FEISHU_ALERT] 服务=%s 状态=%s 详情=%s",
            service_name,
            status,
            details or "",
        )

        return self.send_message(
            receive_id=self._home_channel,
            content=content_json,
            msg_type="interactive",
        )

    # ── Send kanban notification ────────────────────────────────────

    def send_kanban_notification(
        self,
        task_name: str,
        event: str,
        assignee: str = "",
    ) -> dict | None:
        """发送看板状态变更通知卡片。

        使用飞书消息卡片（interactive）格式发送看板通知到默认频道。

        Parameters
        ----------
        task_name : str
            发生变更的任务/项目名称。
        event : str
            触发事件（例如 ``"task_moved"``, ``"task_blocked"``）。
        assignee : str
            负责人名称。

        Returns
        -------
        dict | None
            飞书 API 返回的数据，降级时返回 ``None``。
        """
        if not self._home_channel:
            logger.info(
                "[FEISHU_KANBAN_DEGRADED] 任务=%s 事件=%s 负责人=%s "
                "(FEISHU_HOME_CHANNEL 未配置, 仅日志)",
                task_name,
                event,
                assignee or "未指定",
            )
            return None

        event_labels = {
            "task_created": "任务创建",
            "task_moved": "任务移动",
            "task_blocked": "任务阻塞",
            "deadline_approaching": "截止日期临近",
        }
        event_label = event_labels.get(event, event)

        card = _KANBAN_CARD_TEMPLATE.copy()
        card["header"] = {
            "title": {"tag": "plain_text", "content": f"📋 看板通知: {task_name}"},
            "template": "blue",
        }
        card["elements"] = [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**任务**: {task_name}\n"
                        f"**事件**: {event_label}\n"
                        f"**负责人**: {assignee or '未指定'}"
                    ),
                },
            },
            {"tag": "hr"},
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": "Hermes Dashboard · 自动规则触发",
                    }
                ],
            },
        ]

        content_json = json.dumps(card, ensure_ascii=False)

        logger.info(
            "[FEISHU_KANBAN] 任务=%s 事件=%s 负责人=%s",
            task_name,
            event,
            assignee or "未指定",
        )

        return self.send_message(
            receive_id=self._home_channel,
            content=content_json,
            msg_type="interactive",
        )


# ── Module-level singleton ──────────────────────────────────────────
notifier: FeishuNotifier = FeishuNotifier()
"""预初始化的飞书通知器单例。直接在 ``notifier.send_alert(...)`` 中使用。"""
