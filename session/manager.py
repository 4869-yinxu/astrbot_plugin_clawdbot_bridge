"""
会话管理器

负责管理用户会话状态和会话隔离
"""

from typing import Dict, Optional
from dataclasses import dataclass
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .utils import extract_user_id


@dataclass
class Session:
    """会话数据"""
    mode: str  # "clawdbot" 或 "astrbot"
    session_key: str  # OpenClaw Gateway 的会话标识


class SessionManager:
    """会话管理器
    
    管理用户会话状态，确保会话隔离：
    - 每个用户在每个群组/私聊都有独立的会话
    - 管理员在群组 A 的操作不影响群组 B
    """
    
    MODE_CLAWDBOT = "clawdbot"
    MODE_ASTRBOT = "astrbot"
    
    def __init__(self):
        self._sessions: Dict[str, Session] = {}
    
    def get_session_id(self, event: AstrMessageEvent) -> str:
        """获取会话 ID
        
        格式: platform_user_id_group_id (群组) 或 platform_user_id_private (私聊)
        """
        platform = event.get_platform_name()
        group_id = event.get_group_id() or ""
        user_id = extract_user_id(event, group_id)
        
        if group_id:
            session_id = f"{platform}_{user_id}_{group_id}"
        else:
            session_id = f"{platform}_{user_id}_private"
        
        logger.debug(f"[SessionManager] 会话 ID: {session_id}")
        return session_id
    
    def get_gateway_session_key(self, event: AstrMessageEvent) -> str:
        """获取 OpenClaw Gateway 的会话标识"""
        platform = event.get_platform_name()
        group_id = event.get_group_id() or ""
        user_id = extract_user_id(event, group_id)
        
        if group_id:
            return f"astrbot_{platform}_{user_id}_{group_id}"
        else:
            return f"astrbot_{platform}_{user_id}_private"
    
    def is_in_clawdbot_mode(self, session_id: str) -> bool:
        """检查会话是否在 OpenClaw 模式"""
        session = self._sessions.get(session_id)
        return session is not None and session.mode == self.MODE_CLAWDBOT
    
    def enter_clawdbot_mode(self, session_id: str, session_key: str) -> None:
        """进入 OpenClaw 模式"""
        self._sessions[session_id] = Session(
            mode=self.MODE_CLAWDBOT,
            session_key=session_key
        )
        logger.info(f"[SessionManager] ✅ 进入 OpenClaw 模式: {session_id}")
    
    def exit_clawdbot_mode(self, session_id: str) -> bool:
        """退出 OpenClaw 模式
        
        Returns:
            是否成功退出（如果本来就不在 OpenClaw 模式则返回 False）
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            logger.info(f"[SessionManager] ✅ 退出 OpenClaw 模式: {session_id}")
            return True
        return False
    
    def get_session_key(self, session_id: str) -> Optional[str]:
        """获取会话的 Gateway session key"""
        session = self._sessions.get(session_id)
        return session.session_key if session else None
    
    def clear_all(self) -> int:
        """清理所有会话
        
        Returns:
            清理的会话数量
        """
        count = len(self._sessions)
        self._sessions.clear()
        logger.info(f"[SessionManager] 已清理 {count} 个会话")
        return count
