import time

class CRDT:
    def __init__(self):
        self.sequence = []  # 每个元素: {"id": (client, ts), "char": "A", "deleted": False}

    def insert(self, index, char, client_id):
        op_id = (client_id, time.time())
        element = {"id": op_id, "char": char, "deleted": False}

        if index >= len(self.sequence):
            self.sequence.append(element)
        else:
            self.sequence.insert(index, element)

        return {"type": "insert", "id": op_id, "index": index, "char": char}

    def delete(self, index):
        if 0 <= index < len(self.sequence):
            self.sequence[index]["deleted"] = True
            return {"type": "delete", "id": self.sequence[index]["id"]}
        return None

    def apply(self, op):
        if op["type"] == "insert":
            # 根据 id 排序插入（简单版）
            element = {
                "id": tuple(op["id"]),
                "char": op["char"],
                "deleted": False
            }
            self.sequence.insert(op["index"], element)

        elif op["type"] == "delete":
            for item in self.sequence:
                if tuple(item["id"]) == tuple(op["id"]):
                    item["deleted"] = True
                    break

    def merge(self, ops):
        for op in ops:
            self.apply(op)

    def to_text(self):
        return "".join([x["char"] for x in self.sequence if not x["deleted"]])
