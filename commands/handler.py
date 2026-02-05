"""
命令处理器

负责识别和处理用户命令
"""

from typing import List, Optional, Tuple


class CommandHandler:
    """命令处理器"""
    
    def __init__(
        self,
        switch_commands: List[str],
        exit_commands: List[str],
    ):
        """初始化命令处理器
        
        Args:
            switch_commands: 切换到 OpenClaw 模式的命令列表
            exit_commands: 退出 OpenClaw 模式的命令列表
        """
        self.switch_commands = switch_commands
        self.exit_commands = exit_commands
    
    def is_switch_command(self, message: str) -> bool:
        """检查是否为切换命令"""
        message = message.strip()
        for cmd in self.switch_commands:
            if message.startswith(cmd) or message.startswith(cmd.lstrip("/")):
                return True
        return False
    
    def is_exit_command(self, message: str) -> bool:
        """检查是否为退出命令"""
        message = message.strip()
        for cmd in self.exit_commands:
            if message == cmd or message.startswith(cmd + " "):
                return True
        return False
    
    def is_help_command(self, message: str) -> bool:
        """检查是否为帮助命令"""
        help_patterns = ["help", "帮助"]
        message_lower = message.strip().lower()
        
        for cmd in self.switch_commands:
            cmd_base = cmd.lstrip("/")
            for pattern in help_patterns:
                if message_lower in [f"{cmd} {pattern}", f"{cmd_base} {pattern}"]:
                    return True
        return False
    
    def extract_message(self, message: str) -> str:
        """从消息中提取实际内容（去除命令前缀）"""
        message = message.strip()
        for cmd in self.switch_commands:
            if message.startswith(cmd):
                return message[len(cmd):].strip()
            cmd_no_slash = cmd.lstrip("/")
            if message.startswith(cmd_no_slash):
                return message[len(cmd_no_slash):].strip()
        return message
    
    def parse_command(self, message: str) -> Tuple[str, Optional[str]]:
        """解析命令
        
        Returns:
            (command_type, extracted_message)
            command_type: "switch", "exit", "help", "none"
            extracted_message: 提取的消息内容（仅对 switch 命令有效）
        """
        if self.is_help_command(message):
            return ("help", None)
        
        if self.is_exit_command(message):
            return ("exit", None)
        
        if self.is_switch_command(message):
            extracted = self.extract_message(message)
            return ("switch", extracted if extracted else None)
        
        return ("none", None)
    
    @staticmethod
    def get_help_text() -> str:
        """获取帮助文本"""
        return """🤖 OpenClaw 桥接插件使用说明

📋 切换指令：
  /clawd <消息>  - 切换到 OpenClaw 模式并发送消息
  /管理 <消息>   - 同上（别名）
  
📋 退出指令：
  /退出 或 /返回 - 退出 OpenClaw 模式，返回 AstrBot

💡 使用示例：
  /clawd 帮我检查系统状态
  /clawd 生成一份系统报告
  /退出

⚠️ 注意：
  - 仅管理员可使用此功能
  - 确保 OpenClaw Gateway 正在运行
  - 长时间任务可能需要等待"""
