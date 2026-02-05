#!/usr/bin/env python3
"""
AstrBot ↔ OpenClaw 桥接插件

允许管理员通过 QQ 消息与 OpenClaw AI Agent 交互
"""

import sys
from typing import Optional

from astrbot.api import logger
from astrbot.api.all import *
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from .gateway import OpenClawClient
from .session import SessionManager
from .commands import CommandHandler

# 默认配置
DEFAULT_GATEWAY_URL = "http://host.docker.internal:18789"
DEFAULT_AGENT_ID = "clawdbotbot"
DEFAULT_TIMEOUT = 300
DEFAULT_SWITCH_COMMANDS = ["/clawd", "/管理", "/clawdbot"]
DEFAULT_EXIT_COMMANDS = ["/exit", "/退出", "/返回"]


@register(
    "clawdbot_bridge",
    "a4869",
    "AstrBot 与 OpenClaw 桥接插件，允许管理员通过 QQ 与 OpenClaw AI Agent 交互",
    "1.1.0",
)
class ClawdbotBridge(Star):
    """AstrBot ↔ OpenClaw 桥接插件"""

    def __init__(self, context: Context, config: dict = None):
        super().__init__(context, config)
        self.config = config or {}
        
        # 读取配置
        gateway_url = self._get_config("clawdbot_gateway_url", DEFAULT_GATEWAY_URL)
        agent_id = self._get_config("clawdbot_agent_id", DEFAULT_AGENT_ID)
        auth_token = self._get_config("gateway_auth_token", "")
        timeout = self._get_config("timeout", DEFAULT_TIMEOUT)
        switch_commands = self._get_config("switch_commands", DEFAULT_SWITCH_COMMANDS)
        exit_commands = self._get_config("exit_commands", DEFAULT_EXIT_COMMANDS)
        
        # 初始化组件
        self.client = OpenClawClient(
            gateway_url=gateway_url,
            agent_id=agent_id,
            auth_token=auth_token,
            timeout=timeout,
        )
        self.session_manager = SessionManager()
        self.command_handler = CommandHandler(
            switch_commands=switch_commands,
            exit_commands=exit_commands,
        )
        
        logger.info(
            f"[clawdbot_bridge] 插件初始化完成 - Gateway: {gateway_url}, Agent: {agent_id}"
        )
    
    def _get_config(self, key: str, default):
        """获取配置值"""
        if isinstance(self.config, dict):
            return self.config.get(key, default)
        return getattr(self.config, key, default)
    
    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """检查用户是否为管理员"""
        sender_id = str(event.get_sender_id())
        admins = self.context.get_config().get("admins_id", [])
        return sender_id in admins or "astrbot" in admins

    def _stop_event(self, event: AstrMessageEvent) -> None:
        """停止事件传播并禁止 LLM 调用"""
        event.stop_event()
        event.should_call_llm(True)
        event.call_llm = True
        event.set_extra("skip_llm_hooks", True)
        event._has_send_oper = True

    @filter.event_message_type(EventMessageType.ALL, priority=sys.maxsize)
    async def handle_message(self, event: AstrMessageEvent, *args, **kwargs):
        """处理所有消息"""
        # 检查管理员权限
        if not self._is_admin(event):
            return
        
        message = event.message_str.strip()
        session_id = self.session_manager.get_session_id(event)
        is_in_clawdbot = self.session_manager.is_in_clawdbot_mode(session_id)
        
        # 解析命令
        cmd_type, extracted_msg = self.command_handler.parse_command(message)
        
        # 判断是否需要拦截
        should_intercept = (
            cmd_type != "none" or 
            is_in_clawdbot or 
            self.command_handler.is_help_command(message)
        )
        
        if not should_intercept:
            return
        
        # 停止事件传播
        self._stop_event(event)
        
        logger.info(f"[clawdbot_bridge] 处理消息: {message[:50]} (命令: {cmd_type}, 模式: {'OpenClaw' if is_in_clawdbot else 'AstrBot'})")
        
        # 处理帮助命令
        if cmd_type == "help":
            result = event.plain_result(CommandHandler.get_help_text())
            event.set_result(result)
            yield result
            return
        
        # 处理退出命令
        if cmd_type == "exit":
            self.session_manager.exit_clawdbot_mode(session_id)
            result = event.plain_result("✅ 已退出 OpenClaw 模式，返回 AstrBot 正常对话。")
            event.set_result(result)
            yield result
            return
        
        # 处理切换命令
        if cmd_type == "switch":
            session_key = self.session_manager.get_gateway_session_key(event)
            self.session_manager.enter_clawdbot_mode(session_id, session_key)
            
            # 如果没有附带消息，只切换模式
            if not extracted_msg:
                result = event.plain_result(
                    "💡 已切换到 OpenClaw 模式。发送消息即可与 OpenClaw 对话，使用 /退出 返回。"
                )
                event.set_result(result)
                yield result
                return
            
            # 发送消息到 OpenClaw
            yield event.plain_result("🔄 正在连接 OpenClaw...")
            response = await self.client.send_message(extracted_msg, session_key)
            result = event.plain_result(response or "✅ OpenClaw 已处理，但未返回消息。")
            event.set_result(result)
            yield result
            return
        
        # 在 OpenClaw 模式下转发消息
        if is_in_clawdbot:
            session_key = self.session_manager.get_session_key(session_id)
            if session_key:
                response = await self.client.send_message(message, session_key)
                result = event.plain_result(response or "✅ OpenClaw 已处理，但未返回消息。")
                event.set_result(result)
                yield result
                return

    async def terminate(self):
        """插件终止时清理资源"""
        count = self.session_manager.clear_all()
        logger.info(f"[clawdbot_bridge] 插件已终止，已清理 {count} 个会话")
