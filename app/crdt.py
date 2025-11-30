"""
CRDT (Conflict-free Replicated Data Type) 实现
用于多人协作文档编辑的冲突自动解决

支持的操作：
- insert: 插入字符
- delete: 删除字符
- retain: 保持位置（用于增量同步）

基于 RGA (Replicated Growable Array) 算法
"""
import time
import uuid
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class OpType(Enum):
    INSERT = "insert"
    DELETE = "delete"
    RETAIN = "retain"


@dataclass
class Operation:
    """操作记录"""
    op_type: OpType
    position: int
    char: str = ""
    client_id: str = ""
    timestamp: float = 0
    op_id: str = ""
    
    def __post_init__(self):
        if not self.op_id:
            self.op_id = f"{self.client_id}:{self.timestamp}:{uuid.uuid4().hex[:8]}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.op_type.value,
            "position": self.position,
            "char": self.char,
            "client_id": self.client_id,
            "timestamp": self.timestamp,
            "op_id": self.op_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Operation":
        return cls(
            op_type=OpType(data["type"]),
            position=data["position"],
            char=data.get("char", ""),
            client_id=data.get("client_id", ""),
            timestamp=data.get("timestamp", 0),
            op_id=data.get("op_id", ""),
        )


@dataclass
class Element:
    """文档元素"""
    char: str
    op_id: str
    client_id: str
    timestamp: float
    deleted: bool = False
    
    def __lt__(self, other: "Element") -> bool:
        """排序规则：先按时间戳，再按客户端ID"""
        if self.timestamp != other.timestamp:
            return self.timestamp < other.timestamp
        return self.client_id < other.client_id


class CRDT:
    """
    增强版 CRDT 实现
    
    特点：
    - 基于唯一 ID 的元素标识
    - 支持并发操作的自动合并
    - 操作历史记录用于撤销/重做
    - 增量同步支持
    """
    
    def __init__(self, client_id: str = ""):
        self.client_id = client_id or str(uuid.uuid4())[:8]
        self.sequence: List[Element] = []
        self.operation_history: List[Operation] = []
        self.pending_ops: List[Operation] = []  # 待同步的本地操作
        self.applied_op_ids: set = set()  # 已应用的操作ID，防止重复
        self.version: int = 0  # 文档版本号
    
    def _get_visible_index(self, logical_index: int) -> int:
        """将可见位置转换为实际序列位置（跳过已删除元素）"""
        visible_count = 0
        for i, elem in enumerate(self.sequence):
            if not elem.deleted:
                if visible_count == logical_index:
                    return i
                visible_count += 1
        return len(self.sequence)
    
    def _get_logical_index(self, physical_index: int) -> int:
        """将实际序列位置转换为可见位置"""
        visible_count = 0
        for i in range(min(physical_index, len(self.sequence))):
            if not self.sequence[i].deleted:
                visible_count += 1
        return visible_count
    
    def insert(self, index: int, char: str) -> Operation:
        """在指定位置插入字符"""
        timestamp = time.time()
        op_id = f"{self.client_id}:{timestamp}:{uuid.uuid4().hex[:8]}"
        
        element = Element(
            char=char,
            op_id=op_id,
            client_id=self.client_id,
            timestamp=timestamp,
            deleted=False,
        )
        
        # 转换为实际位置
        physical_index = self._get_visible_index(index)
        
        # 插入元素
        if physical_index >= len(self.sequence):
            self.sequence.append(element)
        else:
            self.sequence.insert(physical_index, element)
        
        # 记录操作
        op = Operation(
            op_type=OpType.INSERT,
            position=index,
            char=char,
            client_id=self.client_id,
            timestamp=timestamp,
            op_id=op_id,
        )
        
        self.operation_history.append(op)
        self.pending_ops.append(op)
        self.applied_op_ids.add(op_id)
        self.version += 1
        
        return op
    
    def delete(self, index: int) -> Optional[Operation]:
        """删除指定位置的字符"""
        physical_index = self._get_visible_index(index)
        
        if physical_index >= len(self.sequence):
            return None
        
        element = self.sequence[physical_index]
        if element.deleted:
            return None
        
        element.deleted = True
        timestamp = time.time()
        
        op = Operation(
            op_type=OpType.DELETE,
            position=index,
            char=element.char,
            client_id=self.client_id,
            timestamp=timestamp,
            op_id=element.op_id,  # 使用原元素的ID
        )
        
        self.operation_history.append(op)
        self.pending_ops.append(op)
        self.version += 1
        
        return op
    
    def insert_text(self, index: int, text: str) -> List[Operation]:
        """插入多个字符"""
        ops = []
        for i, char in enumerate(text):
            op = self.insert(index + i, char)
            ops.append(op)
        return ops
    
    def delete_range(self, start: int, length: int) -> List[Operation]:
        """删除一段文本"""
        ops = []
        # 从后往前删除，避免索引偏移问题
        for _ in range(length):
            op = self.delete(start)
            if op:
                ops.append(op)
        return ops
    
    def apply(self, op: Operation) -> bool:
        """应用远程操作"""
        # 防止重复应用
        if op.op_id in self.applied_op_ids:
            return False
        
        if op.op_type == OpType.INSERT:
            return self._apply_insert(op)
        elif op.op_type == OpType.DELETE:
            return self._apply_delete(op)
        
        return False
    
    def _apply_insert(self, op: Operation) -> bool:
        """应用插入操作"""
        element = Element(
            char=op.char,
            op_id=op.op_id,
            client_id=op.client_id,
            timestamp=op.timestamp,
            deleted=False,
        )
        
        # 找到正确的插入位置
        # 使用时间戳和客户端ID来确定顺序
        target_pos = self._get_visible_index(op.position)
        
        # 在相同位置的并发插入，按时间戳排序
        while target_pos < len(self.sequence):
            existing = self.sequence[target_pos]
            if existing.timestamp > op.timestamp:
                break
            if existing.timestamp == op.timestamp and existing.client_id > op.client_id:
                break
            target_pos += 1
        
        self.sequence.insert(target_pos, element)
        self.applied_op_ids.add(op.op_id)
        self.operation_history.append(op)
        self.version += 1
        
        return True
    
    def _apply_delete(self, op: Operation) -> bool:
        """应用删除操作"""
        for element in self.sequence:
            if element.op_id == op.op_id:
                element.deleted = True
                self.applied_op_ids.add(f"del:{op.op_id}")
                self.operation_history.append(op)
                self.version += 1
                return True
        return False
    
    def merge(self, ops: List[Dict[str, Any]]) -> int:
        """合并多个操作"""
        applied_count = 0
        for op_dict in ops:
            op = Operation.from_dict(op_dict)
            if self.apply(op):
                applied_count += 1
        return applied_count
    
    def get_pending_ops(self) -> List[Dict[str, Any]]:
        """获取待同步的操作"""
        ops = [op.to_dict() for op in self.pending_ops]
        self.pending_ops.clear()
        return ops
    
    def to_text(self) -> str:
        """获取当前文档文本"""
        return "".join(elem.char for elem in self.sequence if not elem.deleted)
    
    def from_text(self, text: str) -> None:
        """从文本初始化（用于首次加载）"""
        self.sequence.clear()
        self.applied_op_ids.clear()
        
        timestamp = time.time()
        for i, char in enumerate(text):
            op_id = f"init:{i}:{timestamp}"
            element = Element(
                char=char,
                op_id=op_id,
                client_id="init",
                timestamp=timestamp,
                deleted=False,
            )
            self.sequence.append(element)
            self.applied_op_ids.add(op_id)
    
    def get_state(self) -> Dict[str, Any]:
        """获取当前状态（用于同步）"""
        return {
            "version": self.version,
            "text": self.to_text(),
            "client_id": self.client_id,
            "elements_count": len(self.sequence),
            "deleted_count": sum(1 for e in self.sequence if e.deleted),
        }
    
    def compact(self) -> int:
        """压缩序列，移除已删除元素（需要所有客户端同意）"""
        original_len = len(self.sequence)
        self.sequence = [e for e in self.sequence if not e.deleted]
        return original_len - len(self.sequence)


class DocumentCRDT:
    """
    文档级 CRDT 管理器
    管理多个客户端的文档同步
    """
    
    def __init__(self, document_id: int):
        self.document_id = document_id
        self.clients: Dict[str, CRDT] = {}
        self.master_crdt = CRDT(client_id="master")
        self.operation_log: List[Dict[str, Any]] = []
    
    def get_client(self, client_id: str) -> CRDT:
        """获取或创建客户端 CRDT"""
        if client_id not in self.clients:
            crdt = CRDT(client_id=client_id)
            crdt.from_text(self.master_crdt.to_text())
            self.clients[client_id] = crdt
        return self.clients[client_id]
    
    def apply_client_ops(self, client_id: str, ops: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        应用客户端操作并广播给其他客户端
        
        Returns:
            需要广播给其他客户端的操作
        """
        # 应用到主 CRDT
        applied = self.master_crdt.merge(ops)
        
        # 记录操作日志
        for op in ops:
            op["applied_at"] = time.time()
            self.operation_log.append(op)
        
        # 应用到其他客户端
        broadcast_ops = []
        for cid, crdt in self.clients.items():
            if cid != client_id:
                crdt.merge(ops)
                broadcast_ops.extend(ops)
        
        return {
            "applied": applied,
            "broadcast": ops,
            "version": self.master_crdt.version,
            "text": self.master_crdt.to_text(),
        }
    
    def get_document_state(self) -> Dict[str, Any]:
        """获取文档状态"""
        return {
            "document_id": self.document_id,
            "text": self.master_crdt.to_text(),
            "version": self.master_crdt.version,
            "clients": list(self.clients.keys()),
            "operations_count": len(self.operation_log),
        }
    
    def remove_client(self, client_id: str) -> None:
        """移除客户端"""
        self.clients.pop(client_id, None)


# 全局文档 CRDT 管理器
_document_crdts: Dict[int, DocumentCRDT] = {}


def get_document_crdt(document_id: int) -> DocumentCRDT:
    """获取文档的 CRDT 管理器"""
    if document_id not in _document_crdts:
        _document_crdts[document_id] = DocumentCRDT(document_id)
    return _document_crdts[document_id]


def remove_document_crdt(document_id: int) -> None:
    """移除文档的 CRDT 管理器"""
    _document_crdts.pop(document_id, None)
