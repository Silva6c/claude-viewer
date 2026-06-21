"""数据模型 —— 定义对话、消息、内容块的数据结构"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ContentBlock:
    """内容块 —— 表示消息中 content 数组里的一个元素
    支持 Claude 导出的全部 15 种内容块类型，每种类型有自己的字段
    """
    type: str = "unknown"

    # text 类型
    text: Optional[str] = None
    citations: list = field(default_factory=list)

    # thinking 类型
    thinking: Optional[str] = None

    # tool_use 类型
    tool_id: Optional[str] = None          # JSON 中的 "id" 字段
    tool_name: Optional[str] = None        # JSON 中的 "name" 字段
    tool_input: Optional[dict] = None      # JSON 中的 "input" 字段
    tool_message: Optional[str] = None     # 工具调用时的提示信息
    tool_icon: Optional[str] = None        # 工具图标名称

    # tool_result 类型
    tool_use_id: Optional[str] = None      # 关联的 tool_use id
    tool_result_content: list = field(default_factory=list)  # 嵌套的子内容块（原始 list）
    is_error: bool = False

    # code_block 类型
    language: Optional[str] = None
    code: Optional[str] = None

    # json_block 类型
    json_data: Optional[dict] = None

    # table 类型
    table_data: list = field(default_factory=list)

    # rich_content 类型
    rich_content_items: list = field(default_factory=list)

    # rich_link 类型
    link_url: Optional[str] = None
    link_title: Optional[str] = None
    link_description: Optional[str] = None
    link_image_url: Optional[str] = None

    # web_search_citation 类型
    citation_url: Optional[str] = None
    citation_title: Optional[str] = None
    citation_text: Optional[str] = None

    # webpage_metadata 类型（通常嵌套在 tool_result 中）
    site_domain: Optional[str] = None
    favicon_url: Optional[str] = None
    site_name: Optional[str] = None

    # knowledge 类型（通常嵌套在 tool_result 中）
    knowledge_title: Optional[str] = None
    knowledge_url: Optional[str] = None
    knowledge_text: Optional[str] = None
    is_missing: bool = False
    metadata: Optional[dict] = None        # 嵌套的 webpage_metadata

    # local_resource 类型
    file_path: Optional[str] = None
    file_name: Optional[str] = None
    mime_type: Optional[str] = None

    # flag 类型
    flag_text: Optional[str] = None
    flag_level: Optional[str] = None       # "info" | "warning" | "error"

    # 通用字段
    start_timestamp: Optional[str] = None
    stop_timestamp: Optional[str] = None
    flags: Optional[dict] = None           # 标记信息

    # 存放未被识别的原始字段（用于调试和降级显示）
    raw_data: Optional[dict] = None


@dataclass
class ChatMessage:
    """聊天消息 —— 对话中的一条消息"""
    uuid: str = ""
    sender: str = "unknown"                      # "human" | "assistant"
    text: str = ""                               # 纯文本（可能和 content 重复）
    content_blocks: list = field(default_factory=list)  # List[ContentBlock]
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    parent_message_uuid: Optional[str] = None
    attachments: list = field(default_factory=list)
    files: list = field(default_factory=list)


@dataclass
class Conversation:
    """对话 —— Claude 中的一次完整对话"""
    uuid: str = ""
    name: str = "未命名对话"
    summary: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    messages: list = field(default_factory=list)  # List[ChatMessage]
    account_uuid: Optional[str] = None

    @property
    def message_count(self) -> int:
        return len(self.messages)

    @property
    def human_message_count(self) -> int:
        return sum(1 for m in self.messages if m.sender == "human")

    @property
    def assistant_message_count(self) -> int:
        return sum(1 for m in self.messages if m.sender == "assistant")
