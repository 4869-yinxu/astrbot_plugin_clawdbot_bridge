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
from astrbot.api.message_components import Plain

from .gateway import OpenClawClient
from .session import SessionManager
from .commands import CommandHandler

# 默认配置
DEFAULT_GATEWAY_URL = "http://host.docker.internal:18789"
DEFAULT_AGENT_ID = "clawdbotbot"
DEFAULT_TIMEOUT = 300
DEFAULT_SWITCH_COMMANDS = ["/clawd", "/管理", "/clawdbot"]
DEFAULT_EXIT_COMMANDS = ["/exit", "/退出", "/返回"]
DEFAULT_SESSION = "main"


@register(
    "clawdbot_bridge",
    "a4869",
    "AstrBot 与 OpenClaw 桥接插件，允许管理员通过 QQ 与 OpenClaw AI Agent 交互",
    "1.4.0",
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
        self.default_session = self._get_config("default_session", DEFAULT_SESSION)
        self.share_with_webui = self._get_config("share_with_webui", False)
        self.agent_id = agent_id
        self.study_groups = self._get_config("study_groups", [])
        self.admin_qq_id = self._get_config("admin_qq_id", "")
        
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
            f"[clawdbot_bridge] 插件初始化完成 - Gateway: {gateway_url}, Agent: {agent_id}, "
            f"默认会话: {self.default_session}, 共享WebUI: {self.share_with_webui}, "
            f"学习群: {self.study_groups}, 管理员: {self.admin_qq_id}"
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
        is_admin = sender_id in admins or "astrbot" in admins
        logger.debug(f"[clawdbot_bridge] 管理员检查: sender_id={sender_id}, admins={admins}, is_admin={is_admin}")
        return is_admin
    
    def _is_study_group(self, event: AstrMessageEvent) -> bool:
        """检查是否为学习群"""
        if event.message_type != EventMessageType.GROUP_MESSAGE:
            return False
        group_id = str(event.group_id) if hasattr(event, 'group_id') else ""
        is_study = group_id in self.study_groups
        logger.debug(f"[clawdbot_bridge] 学习群检查: group_id={group_id}, is_study={is_study}")
        return is_study

    def _stop_event(self, event: AstrMessageEvent) -> None:
        """停止事件传播并禁止 LLM 调用"""
        event.stop_event()
        event.should_call_llm(True)
        event.call_llm = True
        event.set_extra("skip_llm_hooks", True)
        event._has_send_oper = True
    
    async def _send_response(self, event: AstrMessageEvent, response_text: str, is_study_group: bool):
        """发送响应：如果在学习群则私信管理员，否则正常回复"""
        if is_study_group and self.admin_qq_id:
            logger.info(f"[clawdbot_bridge] 学习群响应，私信管理员 {self.admin_qq_id}")
            group_id = str(event.group_id) if hasattr(event, 'group_id') else '未知'
            sender_id = event.get_sender_id()
            message = event.message_str.strip()
            
            admin_message = f"[学习群 OpenClaw]\n群号: {group_id}\n发送者: {sender_id}\n原消息: {message[:100]}\n\n{response_text}"
            try:
                await self.context.send_message(
                    target_id=self.admin_qq_id,
                    message=[Plain(admin_message)],
                    message_type=EventMessageType.FRIEND_MESSAGE
                )
            except Exception as e:
                logger.error(f"[clawdbot_bridge] 发送私信失败: {e}")
        else:
            # 正常回复
            result = event.plain_result(response_text)
            event.set_result(result)
            yield result

    @filter.event_message_type(EventMessageType.ALL, priority=sys.maxsize)
    async def handle_message(self, event: AstrMessageEvent, *args, **kwargs):
        """处理所有消息"""
        raw_message = event.message_str.strip()
        logger.info(f"[clawdbot_bridge] 收到消息: '{raw_message[:100]}' from sender_id={event.get_sender_id()}")
        
        # 检查管理员权限
        if not self._is_admin(event):
            return
        
        message = raw_message
        session_id = self.session_manager.get_session_id(event)
        is_in_clawdbot = self.session_manager.is_in_clawdbot_mode(session_id)
        
        logger.debug(f"[clawdbot_bridge] 消息长度: {len(message)}, 模式: {'OpenClaw' if is_in_clawdbot else 'AstrBot'}")
        
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
        
        # 检查是否在学习群
        is_study_group = self._is_study_group(event)
        
        logger.info(f"[clawdbot_bridge] 处理消息: {message[:50]} (命令: {cmd_type}, 模式: {'OpenClaw' if is_in_clawdbot else 'AstrBot'}, 学习群: {is_study_group})")
        
        # 处理帮助命令
        if cmd_type == "help":
            async for resp in self._send_response(event, CommandHandler.get_help_text(), is_study_group):
                yield resp
            return
        
        # 处理退出命令
        if cmd_type == "exit":
            self.session_manager.exit_clawdbot_mode(session_id)
            async for resp in self._send_response(event, "✅ 已退出 OpenClaw 模式，返回 AstrBot 正常对话。", is_study_group):
                yield resp
            return
        
        # 处理切换命令
        if cmd_type == "switch":
            # 根据配置选择 session key 格式
            if self.share_with_webui:
                session_key = self.session_manager.get_shared_session_key(self.agent_id, self.default_session)
            else:
                session_key = self.session_manager.get_gateway_session_key(event, self.default_session)
            
            self.session_manager.enter_clawdbot_mode(session_id, session_key, self.default_session)
            
            # 如果没有附带消息，只切换模式
            if not extracted_msg:
                mode_hint = "（与 WebUI 共享）" if self.share_with_webui else ""
                response_text = f"💡 已切换到 OpenClaw 模式{mode_hint}（会话: {self.default_session}）。发送消息即可与 OpenClaw 对话，使用 /退出 返回。"
                async for resp in self._send_response(event, response_text, is_study_group):
                    yield resp
                return
            
            # 发送消息到 OpenClaw
            if not is_study_group:
                yield event.plain_result("🔄 正在连接 OpenClaw...")
            
            response = await self.client.send_message(extracted_msg, session_key)
            async for resp in self._send_response(event, response or "✅ OpenClaw 已处理，但未返回消息。", is_study_group):
                yield resp
            return
        
        # 处理会话切换命令
        if cmd_type == "session":
            # 如果没有指定会话名称，显示当前会话
            if not extracted_msg:
                current_session = self.session_manager.get_session_name(session_id)
                response_text = f"📌 当前会话: {current_session or 'default'}"
                async for resp in self._send_response(event, response_text, is_study_group):
                    yield resp
                return
            
            # 切换到指定会话
            if is_in_clawdbot:
                # 已在 OpenClaw 模式，直接切换会话
                success = self.session_manager.set_session_name(
                    session_id, 
                    extracted_msg, 
                    event,
                    self.agent_id,
                    self.share_with_webui
                )
                response_text = f"✅ 已切换到会话: {extracted_msg}" if success else "❌ 切换会话失败"
                async for resp in self._send_response(event, response_text, is_study_group):
                    yield resp
            else:
                # 未在 OpenClaw 模式，进入模式并设置会话
                if self.share_with_webui:
                    session_key = self.session_manager.get_shared_session_key(self.agent_id, extracted_msg)
                else:
                    session_key = self.session_manager.get_gateway_session_key(event, extracted_msg)
                
                self.session_manager.enter_clawdbot_mode(session_id, session_key, extracted_msg)
                response_text = f"✅ 已进入 OpenClaw 模式，会话: {extracted_msg}"
                async for resp in self._send_response(event, response_text, is_study_group):
                    yield resp
            return
        
        # 在 OpenClaw 模式下转发消息
        if is_in_clawdbot:
            session_key = self.session_manager.get_session_key(session_id)
            if session_key:
                # 验证消息不为空
                if not message or not message.strip():
                    logger.warning(f"[clawdbot_bridge] 收到空消息，跳过处理")
                    async for resp in self._send_response(event, "❌ 消息不能为空", is_study_group):
                        yield resp
                    return
                
                response = await self.client.send_message(message, session_key)
                async for resp in self._send_response(event, response or "✅ OpenClaw 已处理，但未返回消息。", is_study_group):
                    yield resp
                return

    async def terminate(self):
        """插件终止时清理资源"""
        count = self.session_manager.clear_all()
        logger.info(f"[clawdbot_bridge] 插件已终止，已清理 {count} 个会话")
